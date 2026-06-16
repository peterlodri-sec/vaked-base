"""Tests for the vulnbox CTF lab range. Stdlib only; no pytest/unittest.

Each box is started in-process on an ephemeral loopback port (port 0 → OS picks), the
intended solution runs against it, and we assert the flag is captured. The traversal box
also gets a CONTAINMENT test: a host-fs escape (`../../../../etc/passwd`) must be refused.
Convention matches tools/ctf/test_ctf.py — module-level test_* + plain assert + a
globals()-based runner.
"""
from __future__ import annotations

import contextlib
import os
import tempfile
import threading

import box_idor
import box_traversal
import solve


@contextlib.contextmanager
def _serving(server):
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        host, port = server.server_address
        yield "http://%s:%d" % (host, port)
    finally:
        server.shutdown()
        server.server_close()


def test_traversal_captures_flag():
    with tempfile.TemporaryDirectory() as root:
        box_traversal.plant(root, "FLAG{tr4v3rs4l_b3y0nd_www}")
        with _serving(box_traversal.make_server(root)) as base:
            assert solve.capture_traversal(base) == "FLAG{tr4v3rs4l_b3y0nd_www}"


def test_traversal_serves_www_file():
    with tempfile.TemporaryDirectory() as root:
        box_traversal.plant(root, "FLAG{x}")
        with _serving(box_traversal.make_server(root)) as base:
            import urllib.request
            body = urllib.request.urlopen(base + "/file?name=index.html", timeout=5).read()
            assert b"notes app" in body


def test_traversal_contained_cannot_escape_host_fs():
    # CONTAINMENT: the deliberate traversal vuln must NOT reach the real host filesystem.
    with tempfile.TemporaryDirectory() as root:
        box_traversal.plant(root, "FLAG{x}")
        with _serving(box_traversal.make_server(root)) as base:
            import urllib.error
            import urllib.request
            code = None
            try:
                urllib.request.urlopen(base + "/file?name=../../../../../../etc/passwd", timeout=5)
            except urllib.error.HTTPError as e:
                code = e.code
            assert code == 403, "host-fs escape should be forbidden, got %r" % code


def test_traversal_escape_really_would_reach_passwd():
    # Sanity: prove the path the box refuses resolves to the REAL /etc/passwd (so 403 means
    # contained, not just a missing file). `..` clamps at root, so plenty of `../` reaches it
    # regardless of www depth; compare via realpath so macOS's /etc→/private/etc symlink matches.
    if not os.path.exists("/etc/passwd"):
        return
    with tempfile.TemporaryDirectory() as root:
        www = os.path.join(root, "www")
        os.makedirs(www, exist_ok=True)
        joined = os.path.realpath(os.path.join(www, "../" * 40 + "etc/passwd"))
        assert joined == os.path.realpath("/etc/passwd")


def test_idor_captures_admin_flag():
    with _serving(box_idor.make_server("FLAG{1d0r_4dm1n_n0t3_1337}")) as base:
        assert solve.capture_idor(base) == "FLAG{1d0r_4dm1n_n0t3_1337}"


def test_idor_listing_hides_admin_id():
    import json
    import urllib.request
    with _serving(box_idor.make_server("FLAG{x}")) as base:
        listed = json.loads(urllib.request.urlopen(base + "/notes", timeout=5).read())
        assert box_idor.ADMIN_ID not in listed
        assert 1 in listed


def test_idor_admin_note_readable_directly():
    # The vuln itself: the hidden admin id is still readable with no authz.
    import urllib.request
    with _serving(box_idor.make_server("FLAG{readable}")) as base:
        body = urllib.request.urlopen(base + "/note?id=%d" % box_idor.ADMIN_ID, timeout=5).read()
        assert body == b"FLAG{readable}"


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
