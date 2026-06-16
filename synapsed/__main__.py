"""Synapse CLI — swarm node management.

Usage::

    synapsed start                      # Start gossip server + anti-entropy loop
    synapsed gossip <peer-ip>           # One-shot gossip to a peer
    synapsed capability add <path> <value-json>   # Add a capability
    synapsed capability list             # List all local capabilities
    synapsed status                      # Show swarm state
    synapsed test-node                   # Start a secondary test node (container mode)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time

from . import VERSION
from .gossip import (
    GOSSIP_PORT,
    SwarmState,
    GossipPacket,
    send_gossip,
    handle_gossip_packet,
    run_gossip_server,
    GOSSIP_HELLO,
)
from .merkletree import CapabilityMerkleTree
from .mesh import run_mesh_server
from .gateway import run_gateway, HTML_TERMINAL

logger = logging.getLogger("synapsed")


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="synapsed[%(process)d]: %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _get_swarm(args) -> SwarmState:
    data_dir = getattr(args, "data_dir", "") or os.environ.get(
        "SYNAPSE_DATA_DIR",
        os.environ.get("STATE_DIRECTORY", "/var/lib/synapsed"),
    )
    node_id = getattr(args, "node_id", "") or os.environ.get(
        "SYNAPSE_NODE_ID", f"node-{os.uname().nodename}"
    )
    return SwarmState(node_id=node_id, data_dir=data_dir)


# ── Commands ────────────────────────────────────────────────────────────────


def cmd_start(args) -> int:
    """Start the gossip server + anti-entropy loop (blocking)."""
    verbose = getattr(args, "verbose", False)
    _setup_logging(verbose)
    swarm = _get_swarm(args)

    bind_ip = getattr(args, "bind_ip", "0.0.0.0")
    port = getattr(args, "port", GOSSIP_PORT)
    genesis_peers = getattr(args, "genesis_peers", "")

    # Start gossip server in a background thread
    server_thread = threading.Thread(
        target=run_gossip_server,
        args=(swarm, bind_ip, port),
        daemon=True,
    )
    server_thread.start()
    logger.info("Synapse v%s started (node_id=%s, root=%s...)",
                VERSION, swarm.node_id, swarm.root_hash[:16])

    # Connect to genesis peers
    if genesis_peers:
        for peer_spec in genesis_peers.split(","):
            peer_spec = peer_spec.strip()
            if ":" in peer_spec:
                ip, p = peer_spec.split(":")
                peer_port = int(p)
            else:
                ip = peer_spec
                peer_port = port
            logger.info("Connecting to genesis peer %s:%d", ip, peer_port)
            hello = GossipPacket(
                kind=GOSSIP_HELLO,
                node_id=swarm.node_id,
                payload={
                    "tailscale_ip": bind_ip,
                    "gossip_port": port,
                    "public_key": swarm.pub_key_hex,
                    "merkle_root": swarm.root_hash,
                    "capability_count": swarm.merkle_tree.leaf_count,
                },
            )
            response = send_gossip(ip, peer_port, hello, swarm)
            if response:
                logger.info("Genesis peer %s responded: %s", ip, response.kind)
            else:
                logger.warning("Genesis peer %s unreachable", ip)

    # Anti-entropy loop
    logger.info("Anti-entropy loop started (interval=10s)")
    while True:
        time.sleep(10)
        for peer_id, peer in list(swarm.peers.items()):
            if time.time() - peer.last_seen > 60:
                logger.info("Peer %s stale, removing", peer_id)
                del swarm.peers[peer_id]
                continue
            # Periodic root hash comparison
            hello = GossipPacket(
                kind=GOSSIP_HELLO,
                node_id=swarm.node_id,
                payload={
                    "merkle_root": swarm.root_hash,
                    "capability_count": swarm.merkle_tree.leaf_count,
                },
            )
            resp = send_gossip(peer.tailscale_ip, peer.gossip_port, hello, swarm)
            if resp and resp.kind == "GOSSIP_CONFLICT":
                conflict = GossipPacket(
                    kind=GOSSIP_CONFLICT,
                    node_id=swarm.node_id,
                    payload={"root_hash": swarm.root_hash},
                )
                resolution = send_gossip(peer.tailscale_ip, peer.gossip_port, conflict, swarm)
                if resolution:
                    logger.info("Anti-entropy resolution: %s from %s",
                                resolution.kind, peer_id)

    return 0


def cmd_gossip(args) -> int:
    """One-shot gossip with a specific peer."""
    _setup_logging(True)
    swarm = _get_swarm(args)
    peer_ip = args.peer_ip
    port = getattr(args, "port", GOSSIP_PORT)

    hello = GossipPacket(
        kind=GOSSIP_HELLO,
        node_id=swarm.node_id,
        payload={
            "tailscale_ip": peer_ip,
            "gossip_port": port,
            "public_key": swarm.pub_key_hex,
            "merkle_root": swarm.root_hash,
            "capability_count": swarm.merkle_tree.leaf_count,
        },
    )

    logger.info("Gossiping with %s:%d...", peer_ip, port)
    response = send_gossip(peer_ip, port, hello, swarm)
    if response:
        print(f"Response: {response.kind}")
        print(json.dumps(response.payload, indent=2)[:500])
        return 0
    else:
        print(f"No response from {peer_ip}:{port}")
        return 1


def cmd_capability_add(args) -> int:
    """Add a capability to the local state."""
    _setup_logging(True)
    swarm = _get_swarm(args)
    path = args.path
    try:
        value = json.loads(args.value_json)
    except json.JSONDecodeError:
        value = {"value": args.value_json}

    root_hash = swarm.add_capability(path, value)
    print(f"Added capability {path}")
    print(f"New Merkle root: {root_hash[:32]}...")
    print(f"Total capabilities: {swarm.merkle_tree.leaf_count}")
    return 0


def cmd_capability_list(args) -> int:
    """List all local capabilities."""
    swarm = _get_swarm(args)

    def _walk(node, prefix=""):
        if node.leaf_value is not None:
            print(f"  {node.path}: {json.dumps(node.leaf_value, sort_keys=True)[:80]}")
        for key in sorted(node.children.keys()):
            _walk(node.children[key], prefix)

    _walk(swarm.merkle_tree.root)
    print(f"\nTotal: {swarm.merkle_tree.leaf_count} capabilities")
    print(f"Merkle root: {swarm.root_hash[:32]}...")
    return 0


def cmd_status(args) -> int:
    """Show current swarm state."""
    swarm = _get_swarm(args)
    print(f"Node ID:        {swarm.node_id}")
    print(f"Public key:     {swarm.pub_key_hex[:32]}...")
    print(f"Merkle root:    {swarm.root_hash[:32]}...")
    print(f"Capabilities:   {swarm.merkle_tree.leaf_count}")
    print(f"Peers known:    {len(swarm.peers)}")
    for pid, ps in swarm.peers.items():
        age = time.time() - ps.last_seen
        print(f"  {pid:30s}  IP={ps.tailscale_ip:15s}  root={ps.merkle_root[:16]}...  seen={age:.0f}s ago")
    return 0


def cmd_test_node(args) -> int:
    """Start a secondary test node (simulates edge-node-02)."""
    _setup_logging(True)
    # Override node_id and data_dir for isolated test state
    os.environ.setdefault("SYNAPSE_NODE_ID", "edge-node-02-test")
    os.environ.setdefault("SYNAPSE_DATA_DIR", "/tmp/synapsed-test-node")
    swarm = _get_swarm(args)

    bind_ip = getattr(args, "bind_ip", "127.0.0.1")
    port = getattr(args, "port", 14434)  # Different port for test node
    genesis_ip = getattr(args, "genesis_ip", "100.105.72.88")
    genesis_port = getattr(args, "genesis_port", GOSSIP_PORT)

    logger.info("Test node starting (node_id=%s, bind=%s:%d, genesis=%s:%d)",
                swarm.node_id, bind_ip, port, genesis_ip, genesis_port)

    # Add some test capabilities
    swarm.add_capability("test/alpha", {"version": "1", "status": "ok"})
    swarm.add_capability("test/beta", {"version": "2", "status": "synced"})
    logger.info("Added 2 test capabilities, root=%s...", swarm.root_hash[:16])

    # Start gossip server
    t = threading.Thread(target=run_gossip_server, args=(swarm, bind_ip, port), daemon=True)
    t.start()

    # Gossip to genesis node
    hello = GossipPacket(
        kind=GOSSIP_HELLO,
        node_id=swarm.node_id,
        payload={
            "tailscale_ip": bind_ip,
            "gossip_port": port,
            "public_key": swarm.pub_key_hex,
            "merkle_root": swarm.root_hash,
            "capability_count": swarm.merkle_tree.leaf_count,
        },
    )

    # Measure convergence time
    start = time.time()
    response = send_gossip(genesis_ip, genesis_port, hello, swarm, timeout=10.0)
    convergence = (time.time() - start) * 1000

    if response:
        logger.info("Genesis response: %s (convergence=%.1fms)", response.kind, convergence)
        if convergence > 100:
            logger.warning("OPTIMIZATION WARNING: Convergence %.1fms exceeds 100ms threshold", convergence)
        print(json.dumps(response.payload, indent=2)[:300])
    else:
        logger.warning("No response from genesis %s:%d", genesis_ip, genesis_port)

    # Keep running
    logger.info("Test node running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Test node stopping")
    return 0


def cmd_mesh_server(args) -> int:
    """Start the mesh visualization HTTP server."""
    _setup_logging(True)
    swarm = _get_swarm(args)
    bind_ip = getattr(args, "bind_ip", "0.0.0.0")
    port = getattr(args, "port", 8080)
    convergence = getattr(args, "convergence", 0.0)

    from .mesh import MeshHandler
    MeshHandler.convergence_ms = convergence
    MeshHandler.swarm = swarm

    logger.info("Mesh visualization server starting on %s:%d (convergence=%.1fms)",
                bind_ip, port, convergence)
    run_mesh_server(swarm, bind_ip, port, convergence)
    return 0


def cmd_gateway(args) -> int:
    """Start the WebSocket gateway + terminal."""
    _setup_logging(True)
    swarm = _get_swarm(args)
    bind_ip = getattr(args, "bind_ip", "0.0.0.0")
    port = getattr(args, "port", 8081)
    convergence = getattr(args, "convergence", 0.0)

    from .gateway import GatewayHandler
    GatewayHandler.convergence_ms = convergence
    GatewayHandler.swarm = swarm

    logger.info("Gateway starting on %s:%d (convergence=%.1fms)",
                bind_ip, port, convergence)
    logger.info("Terminal: http://%s:%d/terminal.html", bind_ip, port)
    logger.info("WebSocket: ws://%s:%d/ws", bind_ip, port)
    run_gateway(swarm, bind_ip, port, convergence)
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="synapsed",
        description="Synapse P2P gossip protocol daemon for the Vaked swarm",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose")
    parser.add_argument("--data-dir", help="Data directory for swarm state")
    parser.add_argument("--node-id", help="Node identifier (default: hostname-based)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # start
    p = sub.add_parser("start", help="Start gossip server + anti-entropy loop")
    p.add_argument("--bind-ip", default="0.0.0.0", help="IP to bind gossip server")
    p.add_argument("--port", type=int, default=GOSSIP_PORT, help="Gossip port")
    p.add_argument("--genesis-peers", default="",
                   help="Comma-separated peer IPs to connect to at startup")
    p.set_defaults(fn=cmd_start)

    # gossip
    p = sub.add_parser("gossip", help="One-shot gossip with a peer")
    p.add_argument("peer_ip", help="Peer IP address")
    p.add_argument("--port", type=int, default=GOSSIP_PORT, help="Peer gossip port")
    p.set_defaults(fn=cmd_gossip)

    # capability
    p = sub.add_parser("capability", help="Manage capabilities")
    cap_sub = p.add_subparsers(dest="cap_cmd", required=True)
    pa = cap_sub.add_parser("add", help="Add a capability")
    pa.add_argument("path", help="Capability path (e.g., network/egress)")
    pa.add_argument("value_json", help="JSON value for the capability")
    pa.set_defaults(fn=cmd_capability_add)
    pl = cap_sub.add_parser("list", help="List capabilities")
    pl.set_defaults(fn=cmd_capability_list)

    # gateway
    p = sub.add_parser("gateway", help="Start WebSocket gateway + terminal")
    p.add_argument("--bind-ip", default="0.0.0.0", help="Gateway bind IP")
    p.add_argument("--port", type=int, default=8081, help="Gateway port")
    p.add_argument("--convergence", type=float, default=0.0, help="Baseline convergence ms")
    p.set_defaults(fn=cmd_gateway)

    # mesh-server
    p = sub.add_parser("mesh-server", help="Start mesh visualization HTTP server")
    p.add_argument("--bind-ip", default="0.0.0.0", help="HTTP bind IP")
    p.add_argument("--port", type=int, default=8080, help="HTTP port")
    p.add_argument("--convergence", type=float, default=0.0,
                   help="Baseline convergence in ms (for display)")
    p.set_defaults(fn=cmd_mesh_server)

    # status
    p = sub.add_parser("status", help="Show swarm state")
    p.set_defaults(fn=cmd_status)

    # test-node
    p = sub.add_parser("test-node", help="Start a secondary test node")
    p.add_argument("--bind-ip", default="127.0.0.1", help="Bind IP for test node")
    p.add_argument("--port", type=int, default=14434, help="Gossip port for test node")
    p.add_argument("--genesis-ip", default="100.105.72.88", help="Genesis node IP")
    p.add_argument("--genesis-port", type=int, default=GOSSIP_PORT, help="Genesis gossip port")
    p.set_defaults(fn=cmd_test_node)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
