#!/usr/bin/env python3
"""Live, playable CTF arena. TAILNET-ONLY — never public-facing.

A human or agent on the tailnet picks a handle, solves the challenges (two are REAL vulnbox
targets launched on loopback; three are self-contained puzzles), and submits flags. Correct
flags are scored (first-blood bonus, deduped) and appended to a hash-chained submission
ledger; the live scoreboard is a deterministic fold over that ledger.

Routes: GET / (challenges + submit form + scoreboard) · POST /submit · GET /scoreboard.json
· GET /healthz. Stdlib only. The bind host is gated by web.validate_bind_host (loopback or
tailnet 100.64.0.0/10 only)."""
from __future__ import annotations

import argparse
import html
import http.server
import json
import tempfile
import threading
import urllib.parse

import live_challenges as LC
import live_scoreboard as LS
import web
from ledger import Ledger

_HANDLE_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def clean_handle(raw: str) -> str | None:
    """A safe player handle: 1..24 chars from [A-Za-z0-9_-]; else None."""
    if not raw:
        return None
    h = "".join(ch for ch in raw.strip() if ch in _HANDLE_OK)[:24]
    return h or None


class Arena:
    """Arena state: the submission ledger + (optional) launched box URLs."""

    def __init__(self, ledger_path: str | None = None, box_urls: dict | None = None):
        self.ledger = Ledger(ledger_path)
        self.box_urls = box_urls or {}
        self._lock = threading.Lock()

    def board(self) -> dict:
        return LS.fold(self.ledger.entries(), LC.by_id(), LC.FIRST_BLOOD_BONUS)

    def submit(self, handle_raw: str, cid: str, flag: str) -> dict:
        handle = clean_handle(handle_raw)
        if not handle:
            return {"ok": False, "msg": "pick a handle (letters/digits/_/-)"}
        if cid not in LC.BY_ID:
            return {"ok": False, "msg": "unknown challenge %r" % cid}
        if not LC.check_flag(cid, flag):
            return {"ok": False, "msg": "nope — wrong flag for %s" % cid}
        with self._lock:
            if LS.already_solved(self.ledger.entries(), handle, cid):
                return {"ok": True, "msg": "%s already solved %s (no double points)" % (handle, cid),
                        "dup": True}
            first = not any(e.get("payload", e).get("kind") == "solve"
                            and e.get("payload", e).get("challenge") == cid
                            for e in self.ledger.entries())
            self.ledger.append({"kind": "solve", "handle": handle, "challenge": cid,
                                "points": LC.BY_ID[cid]["points"], "first_blood": first})
        bonus = " + FIRST BLOOD!" if first else ""
        return {"ok": True, "msg": "%s solved %s (+%d%s)" % (handle, cid, LC.BY_ID[cid]["points"], bonus),
                "first_blood": first}


def launch_boxes() -> tuple[dict, list]:
    """Start the real vulnbox targets on loopback (ephemeral ports). Returns ({cid: url}, servers)."""
    from vulnbox import box_idor, box_traversal
    servers, urls = [], {}
    trav_root = tempfile.mkdtemp(prefix="ctf-live-trav-")
    box_traversal.plant(trav_root, LC.BY_ID["web-traversal"]["flag"])
    trav = box_traversal.make_server(trav_root)
    idor = box_idor.make_server(LC.BY_ID["web-idor"]["flag"])
    for cid, srv in (("web-traversal", trav), ("web-idor", idor)):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        host, port = srv.server_address
        urls[cid] = "http://%s:%d" % (host, port)
        servers.append(srv)
    return urls, servers


# ---- rendering ----
def _esc(x) -> str:
    return html.escape(str(x))


_CSS = """
body{font:15px/1.5 system-ui,sans-serif;max-width:920px;margin:1.6rem auto;padding:0 1rem;color:#1a1a1a}
h1{font-size:1.4rem} h2{font-size:1.05rem;margin-top:1.4rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}
.card{border:1px solid #e2e2e2;border-radius:8px;padding:.7rem .9rem;margin:.5rem 0;background:#fcfcfc}
.card h3{margin:.1rem 0;font-size:.98rem} .meta{font-size:.78rem;color:#777}
.hint{font-size:.86rem;color:#444;margin:.3rem 0} code{background:#f0f0f0;padding:.05rem .3rem;border-radius:3px;word-break:break-all}
table{border-collapse:collapse;width:100%;margin:.4rem 0} th,td{border:1px solid #ddd;padding:.35rem .6rem;text-align:left} th{background:#f4f4f4}
form.submit{background:#f6f8fa;border:1px solid #e0e0e0;padding:.7rem;border-radius:8px;display:flex;flex-wrap:wrap;gap:.5rem;align-items:end}
label{display:flex;flex-direction:column;font-size:.78rem;color:#555} input,select{padding:.3rem;font-size:.9rem} button{padding:.4rem 1rem;cursor:pointer}
.msg{padding:.5rem .7rem;border-radius:6px;margin:.5rem 0} .ok{background:#e7f7ec;border:1px solid #abe2bd} .bad{background:#fdecec;border:1px solid #f3b6b6}
.tailnet{font-size:.75rem;color:#888;margin-top:1.6rem}
"""


def _challenge_cards(arena: Arena) -> str:
    out = []
    for c in LC.CHALLENGES:
        bits = []
        if c["box"] and c["id"] in arena.box_urls:
            bits.append("live target: <code>%s</code>" % _esc(arena.box_urls[c["id"]]))
        elif c["box"]:
            bits.append("<span class=meta>(box not launched — run with --with-boxes)</span>")
        if c["artifact"]:
            bits.append("artifact: <code>%s</code>" % _esc(c["artifact"]))
        out.append(
            "<div class=card><h3>%s <span class=meta>· %s · %d pts</span></h3>"
            "<div class=hint>%s</div>%s</div>"
            % (_esc(c["id"]), _esc(c["category"]), c["points"], _esc(c["hint"]),
               "<div class=hint>%s</div>" % " &nbsp;·&nbsp; ".join(bits) if bits else ""))
    return "".join(out)


def _scoreboard_table(board: dict) -> str:
    rows = board["scoreboard"]
    head = "<tr><th>#</th><th>handle</th><th>points</th><th>solves</th><th>first&nbsp;bloods</th></tr>"
    body = "".join(
        "<tr><td>%d</td><td>%s</td><td>%d</td><td>%d</td><td>%d</td></tr>"
        % (i + 1, _esc(r["handle"]), r["points"], r["solves"], r["first_bloods"])
        for i, r in enumerate(rows))
    return "<table>%s%s</table>" % (head, body or "<tr><td colspan=5 class=meta>no solves yet — be the first</td></tr>")


def _submit_form() -> str:
    opts = "".join("<option value=\"%s\">%s (%d)</option>" % (_esc(c["id"]), _esc(c["id"]), c["points"])
                   for c in LC.CHALLENGES)
    return (
        "<form class=submit method=post action=/submit>"
        "<label>handle<input name=handle size=16 required></label>"
        "<label>challenge<select name=challenge>%s</select></label>"
        "<label>flag<input name=flag size=34 placeholder=\"FLAG{...}\" required></label>"
        "<button type=submit>submit</button></form>" % opts)


def render_page(arena: Arena, bind_host: str, msg: dict | None = None) -> str:
    banner = ""
    if msg:
        banner = "<div class=\"msg %s\">%s</div>" % ("ok" if msg.get("ok") else "bad", _esc(msg.get("msg", "")))
    return (
        "<!doctype html><html><head><meta charset=utf-8><title>Vaked CTF — live arena</title>"
        "<style>%s</style></head><body>"
        "<h1>🚩 Vaked CTF — live arena <span class=meta>tailnet-only</span></h1>"
        "%s"
        "<h2>Submit a flag</h2>%s"
        "<h2>Challenges</h2>%s"
        "<h2>Scoreboard</h2>%s"
        "<p class=tailnet>tailnet-only · bound to %s · not public-facing · "
        "<a href=/scoreboard.json>scoreboard.json</a></p>"
        "</body></html>"
        % (_CSS, banner, _submit_form(), _challenge_cards(arena),
           _scoreboard_table(arena.board()), _esc(bind_host)))


def make_handler(arena: Arena, bind_host: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            if u.path == "/scoreboard.json":
                body = json.dumps(arena.board(), sort_keys=True).encode()
                return self._send(200, body, "application/json")
            if u.path == "/challenges.json":
                pub = [{"id": c["id"], "category": c["category"], "points": c["points"],
                        "hint": c["hint"], "artifact": c["artifact"],
                        "box_url": arena.box_urls.get(c["id"])} for c in LC.CHALLENGES]
                return self._send(200, json.dumps(pub, sort_keys=True).encode(), "application/json")
            if u.path == "/":
                q = urllib.parse.parse_qs(u.query)
                msg = {"ok": q.get("ok", ["1"])[0] == "1", "msg": q["msg"][0]} if "msg" in q else None
                return self._send(200, render_page(arena, bind_host, msg).encode(), "text/html; charset=utf-8")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if u.path != "/submit":
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length", 0) or 0)
            form = urllib.parse.parse_qs(self.rfile.read(n).decode())
            res = arena.submit(form.get("handle", [""])[0], form.get("challenge", [""])[0],
                               form.get("flag", [""])[0])
            # POST/redirect/GET so a refresh doesn't resubmit
            qs = urllib.parse.urlencode({"ok": "1" if res["ok"] else "0", "msg": res["msg"]})
            self.send_response(303)
            self.send_header("Location", "/?" + qs)
            self.end_headers()

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 0, arena: Arena | None = None):
    host = web.validate_bind_host(host)
    arena = arena or Arena()
    return http.server.HTTPServer((host, port), make_handler(arena, host)), arena


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Live CTF arena (tailnet-only, never public)")
    ap.add_argument("--host", default=None, help="bind host (loopback or tailnet 100.x only)")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--tailnet", action="store_true", help="bind the detected tailnet (100.x) IP")
    ap.add_argument("--ledger", default=None, help="JSONL submission ledger path (persisted + replayable)")
    ap.add_argument("--with-boxes", action="store_true", help="launch the real vulnbox targets on loopback")
    ns = ap.parse_args(argv)
    host = ns.host
    if ns.tailnet and not host:
        host = web.detect_tailnet_ip()
        if not host:
            print("ctf-live: no tailnet (100.64.0.0/10) address found; pass --host <100.x> explicitly.")
            return 2
    try:
        host = web.validate_bind_host(host or "127.0.0.1")
    except ValueError as e:
        print("ctf-live: %s" % e)
        return 2
    box_urls = {}
    if ns.with_boxes:
        box_urls, _ = launch_boxes()
    arena = Arena(ns.ledger, box_urls)
    srv = http.server.HTTPServer((host, ns.port), make_handler(arena, host))
    print("Live CTF arena (TAILNET-ONLY) on http://%s:%d" % (srv.server_address[0], srv.server_address[1]))
    if box_urls:
        print("real boxes: " + ", ".join("%s=%s" % kv for kv in box_urls.items()))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
