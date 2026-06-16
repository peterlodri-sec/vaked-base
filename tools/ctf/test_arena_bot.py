"""Tests for the autonomous arena bot. Stdlib only; no pytest/unittest."""
from __future__ import annotations

import contextlib
import json
import threading
import urllib.request

import arena_bot
import live_challenges as LC
import live_server as SRV


def test_solve_each_puzzle_category():
    for cid in ("crypto-caesar", "misc-base64", "rev-xor"):
        c = LC.BY_ID[cid]
        assert arena_bot.solve_artifact(c["category"], c["artifact"]) == c["flag"]


def test_solve_skips_box_and_garbage():
    assert arena_bot.solve_artifact("web", None) is None           # box-backed, no artifact
    assert arena_bot.solve_artifact("misc", "!!!notb64!!!") is None
    assert arena_bot.solve_artifact("rev", "00ff") is None         # no printable FLAG


@contextlib.contextmanager
def _serving():
    srv, ar = SRV.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        host, port = srv.server_address
        yield "http://%s:%d" % (host, port), ar
    finally:
        srv.shutdown(); srv.server_close()


def test_challenges_json_is_flag_free():
    with _serving() as (base, _):
        pub = json.loads(urllib.request.urlopen(base + "/challenges.json", timeout=5).read())
        assert len(pub) == len(LC.CHALLENGES)
        for c in pub:
            assert "flag" not in c and "id" in c and "category" in c


def test_bot_plays_and_scores_three_puzzles():
    with _serving() as (base, _):
        solved = arena_bot.play(base, "autobot")
        assert set(solved) == {"crypto-caesar", "misc-base64", "rev-xor"}
        board = json.loads(urllib.request.urlopen(base + "/scoreboard.json", timeout=5).read())
        assert board["ranking"] == ["autobot"]
        row = board["scoreboard"][0]
        assert row["solves"] == 3 and row["points"] == (100 + 75 + 125) + 3 * 50


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
