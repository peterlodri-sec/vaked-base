"""Tests for the CTF web UI. Stdlib only; no pytest/unittest.

Security-critical: the bind-host guard must accept loopback + tailnet (100.64.0.0/10) and
REFUSE 0.0.0.0 / public / LAN. Plus render checks and a live loopback request. Convention
matches test_ctf.py — module-level test_* + plain assert + a globals()-based runner.
"""
from __future__ import annotations

import contextlib
import threading
import urllib.request

import web


# ---- security: bind-host guard ----
def test_bind_guard_accepts_loopback_and_tailnet():
    for ok in ("127.0.0.1", "::1", "localhost", "100.64.0.1", "100.105.72.88", "100.127.255.254"):
        assert web.validate_bind_host(ok) == (ok or "127.0.0.1")
    assert web.validate_bind_host("") == "127.0.0.1"      # empty → safe loopback default


def test_bind_guard_refuses_public_and_wildcard():
    for bad in ("0.0.0.0", "::", "8.8.8.8", "192.168.1.10", "10.0.0.5",
                "100.63.255.255", "100.128.0.0", "not-an-ip"):
        try:
            web.validate_bind_host(bad)
            assert False, "should refuse %r" % bad
        except ValueError:
            pass


def test_cgnat_boundary_is_exact():
    # 100.64.0.0/10 = 100.64.0.0 .. 100.127.255.255 inclusive.
    assert web.validate_bind_host("100.64.0.0") == "100.64.0.0"
    assert web.validate_bind_host("100.127.255.255") == "100.127.255.255"
    for outside in ("100.63.255.255", "100.128.0.0"):
        try:
            web.validate_bind_host(outside)
            assert False, "edge %r must be outside CGNAT" % outside
        except ValueError:
            pass


# ---- params + run ----
def test_parse_params_clamps_and_defaults():
    p = web._parse_params("teams=9&mode=bogus&seed=42")
    assert p["teams"] == 4 and p["mode"] == "jeopardy" and p["seed"] == 42
    p2 = web._parse_params("teams=1")
    assert p2["teams"] == 2                                # clamp to >=2


def test_run_for_params_deterministic():
    p = web._parse_params("teams=4&seed=1337&mode=jeopardy")
    r1 = web.run_for_params(p)
    r2 = web.run_for_params(p)
    assert r1["chain_hash"] == r2["chain_hash"] and r1["chain_ok"]


# ---- render ----
def test_render_jeopardy_has_scoreboard_and_trophy():
    p = web._parse_params("")
    html = web.render_page(web.run_for_params(p), p)
    assert "<table" in html and "Scoreboard" in html
    assert "team-1" in html and "🏆" in html
    assert "first" in html.lower()                         # jeopardy columns
    assert "tailnet-only" in html


def test_render_koth_has_captures_column():
    p = web._parse_params("mode=koth")
    html = web.render_page(web.run_for_params(p), p)
    assert "koth" in html and "captures" in html


def test_render_vuln_board():
    p = web._parse_params("board=vuln")
    res = web.run_for_params(p)
    html = web.render_page(res, p)
    assert "<table" in html and res["chain_ok"]


# ---- live loopback request ----
@contextlib.contextmanager
def _serving():
    srv = web.make_server("127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        host, port = srv.server_address
        yield "http://%s:%d" % (host, port)
    finally:
        srv.shutdown()
        srv.server_close()


def test_live_root_renders_and_healthz():
    with _serving() as base:
        body = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert "<table" in body and "Vaked CTF" in body
        assert urllib.request.urlopen(base + "/healthz", timeout=5).read() == b"ok"


def test_live_koth_query_renders():
    with _serving() as base:
        body = urllib.request.urlopen(base + "/?mode=koth&teams=3", timeout=5).read().decode()
        assert "koth" in body and "captures" in body


def test_make_server_refuses_public_bind():
    try:
        web.make_server("0.0.0.0", 0)
        assert False, "make_server must refuse 0.0.0.0"
    except ValueError:
        pass


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
