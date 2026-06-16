"""Live mesh status HTTP server for Synapse — feeds the D3.js visualization.

Provides a ``GET /mesh.json`` endpoint returning the current swarm state
as JSON, consumed by ``docs/website/swarm.html``.

Usage::

    synapsed mesh-server --port 8080

Then open ``docs/website/swarm.html`` and it fetches ``mesh.json`` for live data.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from .gossip import SwarmState

logger = logging.getLogger("synapsed.mesh")


class MeshHandler(BaseHTTPRequestHandler):
    """Serves the live swarm state as JSON."""

    swarm: Optional[SwarmState] = None
    convergence_ms: float = 0.0
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        if self.path == "/mesh.json":
            self._serve_mesh()
        elif self.path == "/health":
            self._serve_health()
        elif self.path == "/":
            self._serve_index()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_mesh(self):
        swarm = MeshHandler.swarm
        if swarm is None:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error":"swarm not initialized"}')
            return

        with swarm._lock:
            nodes = []
            # Self node
            nodes.append({
                "id": swarm.node_id,
                "ip": "self",
                "role": "genesis" if "genesis" in swarm.node_id else "edge",
                "caps": swarm.merkle_tree.leaf_count,
                "root": swarm.root_hash[:16],
                "is_self": True,
            })

            # Peer nodes
            for pid, peer in swarm.peers.items():
                nodes.append({
                    "id": pid,
                    "ip": peer.tailscale_ip,
                    "role": "edge" if "genesis" not in pid else "genesis",
                    "caps": peer.capabilities,
                    "root": peer.merkle_root[:16] if peer.merkle_root else "",
                    "last_seen": peer.last_seen,
                    "is_self": False,
                })

            # Links (gossip connections)
            links = []
            for pid, peer in swarm.peers.items():
                age = __import__("time").time() - peer.last_seen
                state = "synced" if age < 30 else ("syncing" if age < 60 else "divergence")
                links.append({
                    "source": swarm.node_id,
                    "target": pid,
                    "state": state,
                    "latency": round(age * 1000, 1),  # ms since last seen as proxy
                })

        data = {
            "nodes": nodes,
            "links": links,
            "metrics": {
                "convergence_ms": round(MeshHandler.convergence_ms, 1),
                "total_capabilities": swarm.merkle_tree.leaf_count,
                "root_hash": swarm.root_hash[:16],
                "peers": len(swarm.peers),
            }
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, sort_keys=True).encode("utf-8"))

    def _serve_health(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def _serve_index(self):
        self.send_response(302)
        self.send_header("Location", "/mesh.json")
        self.end_headers()

    def log_message(self, format, *args):
        logger.debug("HTTP: %s", format % args)


def run_mesh_server(swarm: SwarmState, host: str = "0.0.0.0",
                    port: int = 8080, convergence_ms: float = 0.0) -> None:
    """Start the mesh visualization HTTP server (blocking)."""
    MeshHandler.swarm = swarm
    MeshHandler.convergence_ms = convergence_ms

    server = HTTPServer((host, port), MeshHandler)
    logger.info("Mesh server listening on http://%s:%d", host, port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
