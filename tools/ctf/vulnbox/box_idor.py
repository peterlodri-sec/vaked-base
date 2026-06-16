#!/usr/bin/env python3
"""INTENTIONALLY VULNERABLE CTF lab target — IDOR / broken access control. LAB ONLY. LOOPBACK ONLY.

A deliberately-vulnerable practice target for the vaked CTF range (authorized educational use).
`GET /note?id=<n>` returns note `n` with NO authorization check (IDOR). `GET /notes` lists only
the *public* note ids; the admin note (id 1337) is hidden from the listing but still readable
directly — the intended CTF solution is to request the un-listed admin id to capture the flag.
Self-contained (an in-memory dict; no filesystem). Binds 127.0.0.1 only.
"""
from __future__ import annotations

import http.server
import json
import urllib.parse

ADMIN_ID = 1337


def make_handler(flag: str):
    notes = {1: "welcome to the range", 2: "todo: rotate creds", ADMIN_ID: flag}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/notes":
                # public listing hides the admin id (but it's still readable — the IDOR)
                self._send(200, json.dumps(sorted(i for i in notes if i != ADMIN_ID)).encode())
                return
            if u.path == "/note" and "id" in q:
                try:
                    nid = int(q["id"][0])
                except ValueError:
                    self._send(400, b"bad id")
                    return
                if nid in notes:                       # DELIBERATE VULN: no authz on the admin note
                    self._send(200, notes[nid].encode())
                else:
                    self._send(404, b"no such note")
                return
            self._send(404, b"not found")

        def _send(self, code, body):
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(flag: str, host: str = "127.0.0.1", port: int = 0):
    return http.server.HTTPServer((host, port), make_handler(flag))


if __name__ == "__main__":
    import sys
    srv = make_server("FLAG{1d0r_4dm1n_n0t3_1337}", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8072)
    print("idor vuln-box (LAB ONLY) on http://%s:%d" % (srv.server_address[0], srv.server_address[1]))
    srv.serve_forever()
