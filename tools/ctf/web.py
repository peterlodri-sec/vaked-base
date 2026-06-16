#!/usr/bin/env python3
"""Simple, server-rendered web UI for the CTF sim. TAILNET-ONLY — never public-facing.

Pure stdlib `http.server`, no JS framework. `GET /` shows a run form and renders the
result (scoreboard, ranking, trophy, event feed) entirely server-side — the sim is
deterministic, so the same form params always render the same page. `GET /healthz` → ok.

SAFETY: the bind host is hard-gated by `validate_bind_host` — only loopback or the
Tailscale CGNAT range 100.64.0.0/10 is allowed. `0.0.0.0`, `::`, and any public/other
address are refused. Default bind is 127.0.0.1; `--tailnet` binds the host's 100.x addr.
"""
from __future__ import annotations

import argparse
import html
import http.server
import ipaddress
import re
import subprocess
import urllib.parse

import arena as arena_mod
import ctf as ctf_mod
import engine

# Tailscale hands out addresses from the 100.64.0.0/10 carrier-grade NAT block.
TAILNET_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def validate_bind_host(host: str) -> str:
    """Return `host` iff it is loopback or inside the tailnet CGNAT range; else ValueError.

    This is the security boundary: it refuses 0.0.0.0 / :: / public / LAN addresses so the
    UI can never be bound public-facing."""
    if not host or host in _LOOPBACK_NAMES:
        return host or "127.0.0.1"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("bind host %r is not an IP or loopback name" % host)
    if ip.is_loopback:
        return host
    if ip.version == 4 and ip in TAILNET_CGNAT:
        return host
    raise ValueError(
        "refusing to bind %r — only loopback or tailnet (100.64.0.0/10) is allowed "
        "(this UI must never be public-facing)" % host)


def detect_tailnet_ip() -> str | None:
    """Best-effort: find this host's Tailscale (100.64.0.0/10) IPv4 by reading the OS's
    interface table. Read-only; returns None if none found. The bind guard is the real
    safety net — this is convenience only."""
    cmds = (["tailscale", "ip", "-4"], ["ip", "-o", "-4", "addr", "show"], ["ifconfig"])
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for m in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", out):
            try:
                if ipaddress.ip_address(m) in TAILNET_CGNAT:
                    return m
            except ValueError:
                continue
    return None


def _parse_params(query: str) -> dict:
    q = urllib.parse.parse_qs(query)

    def one(key, default):
        return q.get(key, [default])[0]

    teams = max(2, min(4, int(one("teams", "4") or 4)))
    seed = int(one("seed", "1337") or 1337)
    box_min = max(1, int(one("box_min", "20") or 20))
    mode = one("mode", "jeopardy")
    if mode not in arena_mod.MODES:
        mode = "jeopardy"
    board = one("board", "default")
    strat = one("strategies", "")
    strategies = [s for s in strat.split(",") if s] or ctf_mod.DEFAULT_STRATEGIES
    return {"teams": teams, "seed": seed, "box_min": box_min, "mode": mode,
            "board": board, "strategies": strategies}


def run_for_params(p: dict) -> dict:
    """Build the arena + teams from form params and run the deterministic sim."""
    if p["board"] == "vuln":
        ar = arena_mod.vuln_arena()
        ar["time_box_min"] = p["box_min"]
        ar["mode"] = p["mode"]
    else:
        ar = arena_mod.default_arena(seed=p["seed"])
        ar["time_box_min"] = p["box_min"]
        ar["mode"] = p["mode"]
    teams = ctf_mod.build_teams(p["teams"], p["strategies"])
    return engine.run_ctf(ar, teams)


_CSS = """
body{font:15px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{font-size:1.4rem} h2{font-size:1.05rem;margin-top:1.6rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0} th,td{border:1px solid #ddd;padding:.35rem .6rem;text-align:left}
th{background:#f4f4f4} tr:first-child td{font-weight:600}
form{background:#f8f8f8;border:1px solid #e0e0e0;padding:.8rem;border-radius:6px;display:flex;flex-wrap:wrap;gap:.6rem;align-items:end}
label{display:flex;flex-direction:column;font-size:.8rem;color:#555} input,select{padding:.3rem;font-size:.9rem}
button{padding:.4rem .9rem;font-size:.9rem;cursor:pointer} .feed{font-family:ui-monospace,monospace;font-size:.82rem;max-height:18rem;overflow:auto;background:#fafafa;border:1px solid #eee;padding:.5rem}
.trophy{background:#fff8e1;border:1px solid #ffe082;padding:.6rem;border-radius:6px} .badge{font-size:.75rem;color:#666}
.tailnet{font-size:.75rem;color:#888;margin-top:2rem}
"""


def _esc(x) -> str:
    return html.escape(str(x))


def _opt(value, current, label=None):
    sel = " selected" if value == current else ""
    return "<option value=\"%s\"%s>%s</option>" % (_esc(value), sel, _esc(label or value))


def _form(p: dict) -> str:
    strat = ",".join(p["strategies"])
    return (
        "<form method=get action=/>"
        "<label>teams<input name=teams type=number min=2 max=4 value=%d></label>"
        "<label>seed<input name=seed type=number value=%d></label>"
        "<label>box_min<input name=box_min type=number min=1 value=%d></label>"
        "<label>mode<select name=mode>%s%s</select></label>"
        "<label>board<select name=board>%s%s</select></label>"
        "<label>strategies<input name=strategies size=42 value=\"%s\"></label>"
        "<button type=submit>run</button></form>"
        % (p["teams"], p["seed"], p["box_min"],
           _opt("jeopardy", p["mode"]), _opt("koth", p["mode"]),
           _opt("default", p["board"]), _opt("vuln", p["board"], "vuln (real boxes)"),
           _esc(strat)))


def _scoreboard_table(res: dict) -> str:
    koth = res["mode"] == "koth"
    head = "<tr><th>#</th><th>team</th><th>strategy</th><th>points</th>" + (
        "<th>captures</th>" if koth else "<th>solves</th><th>first&nbsp;bloods</th>") + "</tr>"
    rank = {t: i + 1 for i, t in enumerate(res["ranking"])}
    rows = sorted(res["scoreboard"], key=lambda r: rank[r["team"]])
    body = ""
    for r in rows:
        extra = ("<td>%d</td>" % r["captures"]) if koth else (
            "<td>%d</td><td>%d</td>" % (r["solves"], r["first_bloods"]))
        body += "<tr><td>%d</td><td>%s</td><td>%s</td><td>%d</td>%s</tr>" % (
            rank[r["team"]], _esc(r["team"]), _esc(r["strategy"]), r["points"], extra)
    return "<table>%s%s</table>" % (head, body)


def _feed(res: dict) -> str:
    lines = []
    for e in res["timeline"]:
        p = e.get("payload", e)
        kind = p.get("kind")
        if kind == "solve":
            lines.append("t%-3s %s solved %s (+%d%s)" % (
                p.get("tick"), p.get("team"), p.get("challenge"), p.get("awarded", 0),
                " FIRST-BLOOD" if p.get("first_blood") else ""))
        elif kind == "capture":
            sf = p.get("stolen_from")
            lines.append("t%-3s %s captured %s%s" % (
                p.get("tick"), p.get("team"), p.get("challenge"),
                " (stole from %s)" % sf if sf else ""))
    return "<div class=feed>%s</div>" % ("<br>".join(_esc(x) for x in lines) or "(no events)")


def render_page(res: dict, p: dict, bind_host: str = "127.0.0.1") -> str:
    tr = res["trophy"]
    trophy = (
        "<div class=trophy>🏆 <b>%s</b> — codename <b>%s</b> "
        "<span class=badge>welfare %s · bound %s</span></div>"
        % (_esc(tr["champion"]), _esc(tr["codename"]), _esc(tr["welfare"]),
           _esc(str(tr["bound_to"])[:12])))
    chain = "chain %s · %s" % ("OK" if res["chain_ok"] else "BROKEN", _esc(str(res["chain_hash"])[:16]))
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        "<title>CTF — %s</title><style>%s</style></head><body>"
        "<h1>🚩 Vaked CTF <span class=badge>%s mode · %d teams · seed %d · box %dm</span></h1>"
        "%s"
        "<h2>Champion</h2>%s"
        "<h2>Scoreboard</h2>%s"
        "<h2>Event feed</h2>%s"
        "<p class=badge>%s</p>"
        "<p class=tailnet>tailnet-only · bound to %s · not public-facing</p>"
        "</body></html>"
        % (_esc(res["mode"]), _CSS, _esc(res["mode"]), p["teams"], p["seed"], p["box_min"],
           _form(p), trophy, _scoreboard_table(res), _feed(res), chain, _esc(bind_host)))


def make_handler(bind_host: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/healthz":
                self._send(200, b"ok", "text/plain")
                return
            if u.path == "/":
                p = _parse_params(u.query)
                page = render_page(run_for_params(p), p, bind_host)
                self._send(200, page.encode(), "text/html; charset=utf-8")
                return
            self._send(404, b"not found", "text/plain")

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 0):
    host = validate_bind_host(host)
    return http.server.HTTPServer((host, port), make_handler(host))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CTF web UI (tailnet-only, never public)")
    ap.add_argument("--host", default=None, help="bind host (loopback or tailnet 100.x only)")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--tailnet", action="store_true", help="bind the detected tailnet (100.x) IP")
    ns = ap.parse_args(argv)
    host = ns.host
    if ns.tailnet and not host:
        host = detect_tailnet_ip()
        if not host:
            print("ctf-web: no tailnet (100.64.0.0/10) address found; refusing to guess. "
                  "Pass --host <100.x.y.z> explicitly.")
            return 2
    try:
        host = validate_bind_host(host or "127.0.0.1")
    except ValueError as e:
        print("ctf-web: %s" % e)
        return 2
    srv = http.server.HTTPServer((host, ns.port), make_handler(host))
    print("CTF web UI (TAILNET-ONLY) on http://%s:%d" % (srv.server_address[0], srv.server_address[1]))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
