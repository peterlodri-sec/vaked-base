"""WebSocket gateway for Synapse — streams real-time mesh telemetry.

Endpoints:
    GET /ws  — WebSocket upgrade, streams JSON telemetry frames
    GET /mesh.json — REST snapshot (existing)
    GET /terminal.html — Live public terminal view

Telemetry frame::

    {
        "t": <unix_ms>,
        "convergence_ms": <float>,
        "nodes": <int>,
        "peers": <int>,
        "root": "<hash>",
    "caps": <int>,
    "status": "synced" | "syncing" | "divergence",
    "integrity_hash": "<sha256 of full state>",
    "trust_index": <float 0-1>,
    "flagged_peers": ["peer_id", ...]
}
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from .gossip import SwarmState

logger = logging.getLogger("synapsed.gateway")

HTML_TERMINAL = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Vaked Live — Synapse Gateway</title>
<style>
  body { background:#0a0a0f; color:#c0c0d0; font-family:'SF Mono','Courier New',monospace; font-size:13px; margin:0; padding:20px; }
  #log { white-space:pre-wrap; word-break:break-all; }
  .t { color:#606070; } .ok { color:#00c864; } .warn { color:#ffc800; } .err { color:#ff3232; }
  .hl { color:#60b0ff; } .dim { color:#404050; }
  #header { border-bottom:1px solid #2a2a3a; padding-bottom:8px; margin-bottom:12px; }
  #header h1 { margin:0; font-size:14px; color:#60b0ff; letter-spacing:2px; }
  #header .sub { font-size:10px; color:#606070; }
  #badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:10px; margin-left:8px; }
  .badge-live { background:rgba(0,200,100,0.15); border:1px solid rgba(0,200,100,0.3); color:#00c864; }
</style></head>
<body>
<div id="header">
  <h1>⚡ SYNAPSE GATEWAY <span id="badge" class="badge-badge badge-live">● LIVE</span></h1>
  <div class="sub">genesis.vaked.dev — P2P Mesh Telemetry</div>
</div>
<div id="log">Connecting to mesh gateway...</div>
<script>
const el = document.getElementById('log');
const ws = new WebSocket((location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws');
ws.onmessage = (e) => {
  const d = JSON.parse(e.data);
  const t = new Date(d.t).toISOString().slice(11,23);
  const status = d.status === 'synced' ? '<span class="ok">●</span>' : d.status === 'syncing' ? '<span class="warn">◐</span>' : '<span class="err">○</span>';
  const trustPct = (d.trust_index * 100).toFixed(0);
  const trustColor = d.trust_index > 0.8 ? 'ok' : d.trust_index > 0.5 ? 'warn' : 'err';
  const flagged = d.flagged_peers && d.flagged_peers.length > 0 ? ` <span class="warn">⚑ ${d.flagged_peers.join(",")}</span>` : '';
  const line = `<span class="t">[${t}]</span> ${status} <span class="hl">${d.convergence_ms.toFixed(1)}ms</span> ` +
    `<span class="dim">|</span> ${d.nodes} nodes <span class="dim">|</span> ${d.peers} peers ` +
    `<span class="dim">|</span> root=<span class="hl">${d.root.slice(0,12)}</span> ` +
    `<span class="dim">|</span> caps=${d.caps} ` +
    `<span class="dim">|</span> trust=<span class="${trustColor}">${trustPct}%</span>${flagged} ` +
    `<span class="dim">|</span> integrity=<span class="${d.status === 'synced' ? 'ok' : 'warn'}">${d.integrity_hash.slice(0,12)}</span>`;
  el.innerHTML = line + '<br>' + el.innerHTML;
  if (el.children.length > 200) el.removeChild(el.lastChild);
  const badge = document.getElementById('badge');
  const hasFlags = d.flagged_peers && d.flagged_peers.length > 0;
  const badgeStatus = hasFlags ? 'warning' : d.status;
  badge.textContent = hasFlags ? '⚑ FLAGGED' : d.status === 'synced' ? '● SYNCED' : d.status === 'syncing' ? '◐ SYNCING' : '○ DIVERGENCE';
  const colors = {'synced':'rgba(0,200,100,0.15)','syncing':'rgba(255,200,0,0.15)','divergence':'rgba(255,50,50,0.15)','warning':'rgba(255,150,0,0.15)'};
  const textColors = {'synced':'#00c864','syncing':'#ffc800','divergence':'#ff3232','warning':'#ff9600'};
  const borderColors = {'synced':'rgba(0,200,100,0.3)','syncing':'rgba(255,200,0,0.3)','divergence':'rgba(255,50,50,0.3)','warning':'rgba(255,150,0,0.3)'};
  badge.style.background = colors[badgeStatus] || colors.warning;
  badge.style.borderColor = borderColors[badgeStatus] || borderColors.warning;
  badge.style.color = textColors[badgeStatus] || '#ff9600';
};
ws.onclose = () => { el.innerHTML = '<span class="err">⚠ Connection closed. Reconnecting...</span><br>' + el.innerHTML; setTimeout(() => location.reload(), 3000); };
ws.onerror = () => { el.innerHTML = '<span class="err">⚠ Connection error.</span><br>' + el.innerHTML; };
</script></body></html>
"""


class GatewayHandler(BaseHTTPRequestHandler):
    """HTTP handler with WebSocket upgrade for streaming telemetry."""

    swarm: Optional[SwarmState] = None
    sentinel: Optional["Sentinel"] = None  # noqa: F821
    convergence_ms: float = 0.0
    constellation_path: str = "/var/www/constellation/index.html"
    _ledger_path: str = "/var/lib/private/meta-ralphd/oculus.jsonl"
    _strategy_cache: Optional[dict] = None
    _strategy_cache_ts: float = 0
    _ws_client: Optional[object] = None

    @classmethod
    def _load_latest_strategy(cls) -> Optional[dict]:
        """Read the latest STRATEGY_UPDATE from the Oculus ledger."""
        now = time.time()
        if cls._strategy_cache and now - cls._strategy_cache_ts < 30:
            return cls._strategy_cache
        ledger = getattr(cls, "_ledger_path", "/var/lib/private/meta-ralphd/oculus.jsonl")
        try:
            with open(ledger) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        e = json.loads(line)
                        if e.get("payload",{}).get("kind") in ("STRATEGY_UPDATE", "WISE_NODE_DEPLOYED"):
                            cls._strategy_cache = {
                                "kind": "WISDOM_EVENT",
                                "seq": e.get("seq"),
                                "primary_focus": e.get("payload",{}).get("primary_focus", "unknown"),
                                "directives": e.get("payload",{}).get("directives_issued", 0),
                                "heuristics": e.get("payload",{}).get("heuristics", 0),
                                "timestamp": e.get("payload",{}).get("timestamp", 0),
                            }
                            cls._strategy_cache_ts = now
                    except: pass
        except (OSError, IOError):
            pass
        return cls._strategy_cache
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/ws":
            self._handle_ws()
        elif self.path == "/mesh.json":
            self._serve_json()
        elif self.path in ("/", "/terminal.html"):
            self._serve_terminal()
        elif self.path in ("/constellation", "/constellation.html"):
            self._serve_constellation()
        elif self.path == "/health":
            self._serve_health()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_json(self):
        data = self._build_mesh_state(False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, sort_keys=True).encode())

    def _serve_constellation(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        # Load from disk — allows hot-updating the visualization
        const_path = getattr(GatewayHandler, "constellation_path",
                             "/var/www/constellation/index.html")
        try:
            with open(const_path) as f:
                self.wfile.write(f.read().encode())
        except (OSError, IOError):
            self.wfile.write(b"<html><body><h1>Constellation not deployed</h1></body></html>")

    def _serve_terminal(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(HTML_TERMINAL.encode())

    def _serve_health(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def _build_mesh_state(self, for_ws: bool = False) -> dict:
        swarm = GatewayHandler.swarm
        if swarm is None:
            return {"status": "uninitialized"}

        with swarm._lock:
            nodes_list = []
            nodes_list.append({
                "id": swarm.node_id, "caps": swarm.merkle_tree.leaf_count,
                "root": swarm.root_hash[:16], "is_self": True,
            })
            for pid, peer in swarm.peers.items():
                nodes_list.append({
                    "id": pid, "ip": peer.tailscale_ip,
                    "caps": peer.capabilities,
                    "root": peer.merkle_root[:16] if peer.merkle_root else "",
                    "last_seen": peer.last_seen, "is_self": False,
                })
            links_list = []
            for pid, peer in swarm.peers.items():
                age = time.time() - peer.last_seen
                state = "synced" if age < 30 else ("syncing" if age < 60 else "divergence")
                links_list.append({"source": swarm.node_id, "target": pid, "state": state})

        # Load latest strategy from Oculus ledger
        strategy = GatewayHandler._load_latest_strategy()

        # Compute integrity hash over full state
        integrity = hashlib.sha256(
            json.dumps({"root": swarm.root_hash, "caps": swarm.merkle_tree.leaf_count,
                        "peers": len(swarm.peers)}, sort_keys=True).encode()
        ).hexdigest()

        # Sentinel trust data
        sentinel_data = {}
        if GatewayHandler.sentinel is not None:
            s = GatewayHandler.sentinel
            sentinel_data = {
                "trust_index": round(s.trust_index, 3),
                "flagged_peers": s.trust.flagged_peers(),
            }

        return {
            "t": int(time.time() * 1000),
            "convergence_ms": round(GatewayHandler.convergence_ms, 1),
            "nodes": len(nodes_list),
            "peers": len(swarm.peers),
            "root": swarm.root_hash[:16],
            "caps": swarm.merkle_tree.leaf_count,
            "integrity_hash": integrity,
            "status": "synced" if len(swarm.peers) == 0 or all(
                time.time() - p.last_seen < 30 for p in swarm.peers.values()
            ) else ("syncing" if any(
                time.time() - p.last_seen < 60 for p in swarm.peers.values()
            ) else "divergence"),
            "trust_index": sentinel_data.get("trust_index", 1.0),
            "flagged_peers": sentinel_data.get("flagged_peers", []),
            "strategy": strategy,
            "nodes_list": nodes_list if not for_ws else [],
            "links_list": links_list if not for_ws else [],
        }

    def _handle_ws(self):
        """Minimal WebSocket handshake — for production use an async framework."""
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_response(400)
            self.end_headers()
            return

        import hashlib as _h, base64 as _b64
        accept = _b64.b64encode(
            _h.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()

        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        # Stream telemetry frames
        wfile = self.wfile
        try:
            while True:
                # Mesh state frame
                state = self._build_mesh_state(for_ws=True)
                frame = self._ws_encode(json.dumps(state, sort_keys=True).encode())
                wfile.write(frame)
                # Separate wisdom event frame every 5th tick (2.5s)
                if int(time.time() * 2) % 5 == 0:
                    strategy = GatewayHandler._load_latest_strategy()
                    if strategy:
                        wisdom_frame = self._ws_encode(json.dumps({
                            "t": int(time.time() * 1000),
                            "kind": "WISDOM_EVENT",
                            "data": strategy,
                        }).encode())
                        wfile.write(wisdom_frame)
                wfile.flush()
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionError, OSError):
            pass

    def _ws_encode(self, payload: bytes) -> bytes:
        """Encode a WebSocket text frame (unmasked)."""
        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode
        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, "big"))
        frame.extend(payload)
        return bytes(frame)

    def log_message(self, fmt, *args):
        logger.debug("HTTP: " + fmt % args)


def run_gateway(swarm: SwarmState, host: str = "0.0.0.0",
                port: int = 8081, convergence_ms: float = 0.0,
                sentinel: Optional["Sentinel"] = None) -> None:  # noqa: F821
    """Run the gateway server (blocking)."""
    GatewayHandler.swarm = swarm
    GatewayHandler.sentinel = sentinel
    GatewayHandler.convergence_ms = convergence_ms
    server = HTTPServer((host, port), GatewayHandler)
    logger.info("Gateway listening on http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
