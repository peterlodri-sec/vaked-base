#!/usr/bin/env python3
"""INTENTIONALLY VULNERABLE CTF lab target — path traversal. LAB ONLY. LOOPBACK ONLY.

A deliberately-vulnerable practice target for the vaked CTF range (authorized educational
use). `GET /file?name=<path>` joins `name` onto the served `www/` dir WITHOUT sanitizing it —
the intended CTF solution is `name=../flag.txt`, traversing out of `www/` to the planted flag.

CONTAINMENT (responsible lab design): reads are realpath-confined to `lab_root` — the traversal
escapes `www/` into the lab (capturing the flag) but CANNOT escape to the host filesystem
(`../../../../etc/passwd` → 403). Binds 127.0.0.1 only. Do NOT expose on a real network.
"""
from __future__ import annotations

import http.server
import os
import urllib.parse


def make_handler(lab_root: str):
    www = os.path.join(lab_root, "www")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/":
                self._send(200, b"vuln-box: path-traversal. GET /file?name=index.html")
                return
            if u.path == "/file" and "name" in q:
                # DELIBERATE VULN: no sanitization of `name` before the join.
                target = os.path.realpath(os.path.join(www, q["name"][0]))
                # CONTAINMENT: stay within the lab root (cannot read the host fs at large).
                if not (target == lab_root or target.startswith(lab_root + os.sep)):
                    self._send(403, b"forbidden (outside lab root)")
                    return
                try:
                    with open(target, "rb") as f:
                        self._send(200, f.read())
                except OSError:
                    self._send(404, b"not found")
                return
            self._send(404, b"not found")

        def _send(self, code, body):
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def plant(lab_root: str, flag: str) -> None:
    """Set up the lab: a www/ dir (the served root) + a flag one level up (the traversal target)."""
    os.makedirs(os.path.join(lab_root, "www"), exist_ok=True)
    with open(os.path.join(lab_root, "www", "index.html"), "w") as f:
        f.write("<h1>notes app</h1>")
    with open(os.path.join(lab_root, "flag.txt"), "w") as f:
        f.write(flag)


def make_server(lab_root: str, host: str = "127.0.0.1", port: int = 0):
    return http.server.HTTPServer((host, port), make_handler(os.path.realpath(lab_root)))


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vulnbox-traversal"
    plant(root, "FLAG{tr4v3rs4l_b3y0nd_www}")
    srv = make_server(root, port=int(sys.argv[2]) if len(sys.argv) > 2 else 8071)
    print("traversal vuln-box (LAB ONLY) on http://%s:%d  root=%s"
          % (srv.server_address[0], srv.server_address[1], root))
    srv.serve_forever()
