"""Tests for the live CTF arena. Stdlib only; no pytest/unittest.

Covers: handle hygiene, constant-time flag check, puzzle artifacts actually decode to the
flag (solvable), the replay-stable scoreboard fold (first-blood + dedup + ranking), Arena
submission + hash-chained ledger, the live HTTP flow, the tailnet bind guard, ledger
persistence/replay, and a full real-box integration loop (launch vulnbox → solve → submit →
scored). Convention matches test_ctf.py — module-level test_* + plain assert + a runner."""
from __future__ import annotations

import base64
import codecs
import contextlib
import json
import tempfile
import threading
import urllib.parse
import urllib.request

import live_challenges as LC
import live_scoreboard as LS
import live_server as SRV


# ---- handle hygiene ----
def test_clean_handle():
    assert SRV.clean_handle("  alice ") == "alice"
    assert SRV.clean_handle("a!b@c#") == "abc"
    assert SRV.clean_handle("") is None
    assert SRV.clean_handle("!!!") is None
    assert len(SRV.clean_handle("x" * 50)) == 24


# ---- flag check ----
def test_check_flag_constant_time_and_trims():
    assert LC.check_flag("crypto-caesar", "FLAG{caesar_rot_thirteen}")
    assert LC.check_flag("crypto-caesar", "  FLAG{caesar_rot_thirteen}  ")   # trims
    assert not LC.check_flag("crypto-caesar", "FLAG{wrong}")
    assert not LC.check_flag("no-such", "x")
    assert not LC.check_flag("crypto-caesar", None)


# ---- puzzles are actually solvable from their artifacts ----
def test_artifacts_decode_to_flag():
    caesar = next(c for c in LC.CHALLENGES if c["id"] == "crypto-caesar")
    assert codecs.decode(caesar["artifact"], "rot13") == caesar["flag"]
    b64 = next(c for c in LC.CHALLENGES if c["id"] == "misc-base64")
    assert base64.b64decode(b64["artifact"]).decode() == b64["flag"]
    xor = next(c for c in LC.CHALLENGES if c["id"] == "rev-xor")
    raw = bytes.fromhex(xor["artifact"])
    assert bytes(b ^ 0x42 for b in raw).decode() == xor["flag"]


# ---- scoreboard fold ----
def _solve(handle, cid):
    return {"payload": {"kind": "solve", "handle": handle, "challenge": cid}}


def test_fold_first_blood_dedup_and_ranking():
    entries = [_solve("alice", "misc-base64"),      # alice first → +bonus
               _solve("bob", "misc-base64"),        # bob second → no bonus
               _solve("alice", "misc-base64"),      # dup → ignored
               _solve("bob", "crypto-caesar")]      # bob first on caesar → +bonus
    b = LS.fold(entries, LC.by_id(), 50)
    by = {r["handle"]: r for r in b["scoreboard"]}
    assert by["alice"]["points"] == 75 + 50 and by["alice"]["first_bloods"] == 1
    assert by["alice"]["solves"] == 1                                  # dup didn't count
    assert by["bob"]["points"] == 75 + (100 + 50) and by["bob"]["first_bloods"] == 1
    assert b["ranking"][0] == "bob"                                    # 225 > 125


def test_fold_replay_stable():
    entries = [_solve("a", "misc-base64"), _solve("b", "rev-xor")]
    assert LS.fold(entries, LC.by_id()) == LS.fold(entries, LC.by_id())


def test_already_solved():
    entries = [_solve("a", "rev-xor")]
    assert LS.already_solved(entries, "a", "rev-xor")
    assert not LS.already_solved(entries, "a", "misc-base64")


# ---- Arena submission + ledger ----
def test_submit_correct_appends_and_chain_verifies():
    a = SRV.Arena()
    r = a.submit("alice", "misc-base64", "FLAG{base_sixty_four_unwrap}")
    assert r["ok"] and r["first_blood"]
    assert a.ledger.verify() and len(a.ledger.entries()) == 1
    assert a.board()["ranking"] == ["alice"]


def test_submit_wrong_does_not_append():
    a = SRV.Arena()
    r = a.submit("alice", "misc-base64", "FLAG{nope}")
    assert not r["ok"] and len(a.ledger.entries()) == 0


def test_submit_dedup_no_double_points():
    a = SRV.Arena()
    a.submit("alice", "misc-base64", "FLAG{base_sixty_four_unwrap}")
    r2 = a.submit("alice", "misc-base64", "FLAG{base_sixty_four_unwrap}")
    assert r2.get("dup") and len(a.ledger.entries()) == 1
    assert a.board()["scoreboard"][0]["points"] == 75 + 50


def test_submit_bad_handle_rejected():
    a = SRV.Arena()
    assert not a.submit("!!!", "misc-base64", "FLAG{base_sixty_four_unwrap}")["ok"]


# ---- ledger persistence + replay ----
def test_ledger_persist_and_replay():
    p = tempfile.mktemp(suffix=".jsonl")
    a1 = SRV.Arena(p)
    a1.submit("alice", "misc-base64", "FLAG{base_sixty_four_unwrap}")
    a1.submit("bob", "rev-xor", "FLAG{x0r_single_byte_key}")
    a2 = SRV.Arena(p)                                                  # fresh arena, same ledger file
    assert a2.ledger.verify()
    assert a2.board() == a1.board()                                   # replay-stable


# ---- live HTTP flow ----
@contextlib.contextmanager
def _serving(arena=None):
    srv, ar = SRV.make_server("127.0.0.1", 0, arena)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        host, port = srv.server_address
        yield "http://%s:%d" % (host, port), ar
    finally:
        srv.shutdown(); srv.server_close()


def test_live_get_root_and_healthz():
    with _serving() as (base, _):
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert "live arena" in page and "misc-base64" in page and "Scoreboard" in page
        assert urllib.request.urlopen(base + "/healthz", timeout=5).read() == b"ok"


def test_live_submit_scores_and_shows_on_board():
    with _serving() as (base, _):
        data = urllib.parse.urlencode({"handle": "zoe", "challenge": "misc-base64",
                                       "flag": "FLAG{base_sixty_four_unwrap}"}).encode()
        urllib.request.urlopen(base + "/submit", data=data, timeout=5).read()   # 303 → /
        board = json.loads(urllib.request.urlopen(base + "/scoreboard.json", timeout=5).read())
        assert board["ranking"] == ["zoe"] and board["scoreboard"][0]["points"] == 125


def test_make_server_refuses_public_bind():
    try:
        SRV.make_server("0.0.0.0", 0)
        assert False, "must refuse 0.0.0.0"
    except ValueError:
        pass


# ---- full real-box integration loop ----
def test_integration_launch_solve_submit():
    from vulnbox import solve
    urls, servers = SRV.launch_boxes()
    try:
        assert set(urls) == {"web-traversal", "web-idor"}
        trav_flag = solve.capture_traversal(urls["web-traversal"])    # solve the REAL box
        idor_flag = solve.capture_idor(urls["web-idor"])
        a = SRV.Arena(box_urls=urls)
        assert a.submit("solver", "web-traversal", trav_flag)["ok"]   # submit captured flags
        assert a.submit("solver", "web-idor", idor_flag)["ok"]
        b = a.board()["scoreboard"][0]
        assert b["handle"] == "solver" and b["solves"] == 2
        assert b["points"] == (200 + 50) + (150 + 50)                 # both first-blood
    finally:
        for s in servers:
            s.shutdown(); s.server_close()


def _run():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print("FAIL %s: %r" % (name, e))
        else:
            passed += 1
            print("ok   %s" % name)
    print("\n%d/%d passed" % (passed, len(tests)))
    return passed == len(tests)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run() else 1)
