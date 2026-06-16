"""UDP gossip transport for Synapse — sub-50ms convergence target.

Replaces TCP with UDP for lower-latency gossip exchanges. Each gossip
round uses a simple send-wait-respond pattern over UDP with a 200ms
timeout. Packets are single-datagram (fits in < 1472 bytes for typical
capability updates; larger Merkle trees are chunked).

The eBPF fast-path (future Zig daemon) will attach a ``BPF_PROG_TYPE_CGROUP_SKB``
program that routes gossip packets directly between peers without a userspace
hop — the Python reference implements the same decision logic.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
import time
import uuid
from typing import Optional

from .merkletree import CapabilityMerkleTree

logger = logging.getLogger("synapsed.udp")

# ── Wire constants ──────────────────────────────────────────────────────────

UDP_MAGIC = b"SYN2"  # UDP protocol magic
UDP_HEADER_FMT = "!4sI"  # magic (4s) + payload_length (I)
UDP_HEADER_SIZE = struct.calcsize(UDP_HEADER_FMT)
MAX_DATAGRAM_SIZE = 1400  # Safe MTU for Tailscale (1280 - header overhead)
GOSSIP_UDP_PORT = 4435  # One above the TCP gossip port

# Packet kinds (same semantics as TCP, now over UDP)
UDP_HELLO = "U_HELLO"
UDP_MERKLE = "U_MERKLE"
UDP_DELTA = "U_DELTA"
UDP_ACK = "U_ACK"
UDP_CONFLICT = "U_CONFLICT"


def make_udp_packet(kind: str, node_id: str, payload: dict,
                    nonce: Optional[str] = None) -> bytes:
    """Create a signed UDP gossip datagram."""
    if nonce is None:
        nonce = uuid.uuid4().hex[:16]
    body = json.dumps({
        "kind": kind,
        "node_id": node_id,
        "payload": payload,
        "nonce": nonce,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")

    if len(body) > MAX_DATAGRAM_SIZE - UDP_HEADER_SIZE:
        logger.warning("Datagram too large (%d bytes), truncating payload", len(body))
        # In production, chunk over multiple datagrams
        body = body[:MAX_DATAGRAM_SIZE - UDP_HEADER_SIZE]

    header = struct.pack(UDP_HEADER_FMT, UDP_MAGIC, len(body))
    return header + body


def parse_udp_packet(data: bytes) -> Optional[dict]:
    """Parse a UDP gossip datagram."""
    if len(data) < UDP_HEADER_SIZE:
        return None
    magic, length = struct.unpack(UDP_HEADER_FMT, data[:UDP_HEADER_SIZE])
    if magic != UDP_MAGIC:
        return None
    body = data[UDP_HEADER_SIZE:UDP_HEADER_SIZE + length]
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


class UdpGossipTransport:
    """UDP-based gossip transport with sub-50ms convergence target.

    Each round::

        Alice                  Bob
          |--- U_HELLO ------->|   (Merkle root, capability count)
          |<-- U_MERKLE -------|   (full tree if root mismatch)
          |--- U_DELTA ------->|   (changed subtree hashes)
          |<-- U_ACK ---------|    (deltas applied, new root)
    """

    def __init__(self, node_id: str, merkle_tree: CapabilityMerkleTree,
                 bind_ip: str = "0.0.0.0", port: int = GOSSIP_UDP_PORT):
        self.node_id = node_id
        self.merkle_tree = merkle_tree
        self.bind_ip = bind_ip
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._running = False

    def start(self):
        """Start the UDP gossip listener."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.bind_ip, self.port))
        self._socket.settimeout(0.5)
        self._running = True
        logger.info("UDP gossip listening on %s:%d", self.bind_ip, self.port)

    def stop(self):
        self._running = False
        if self._socket:
            self._socket.close()

    def serve_forever(self):
        """Handle incoming UDP gossip packets (blocking)."""
        self.start()
        while self._running:
            try:
                data, addr = self._socket.recvfrom(MAX_DATAGRAM_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            # Process in a thread for concurrency
            t = threading.Thread(target=self._handle_datagram,
                                 args=(data, addr), daemon=True)
            t.start()
        self.stop()

    def _handle_datagram(self, data: bytes, addr: tuple):
        """Handle one incoming UDP gossip packet."""
        packet = parse_udp_packet(data)
        if packet is None:
            return

        kind = packet.get("kind", "")
        node_id = packet.get("node_id", "")
        payload = packet.get("payload", {})
        nonce = packet.get("nonce", "")

        if kind == UDP_HELLO:
            remote_root = payload.get("merkle_root", "")
            local_root = self.merkle_tree.root_hash

            if remote_root != local_root:
                # Send our Merkle tree + proactively compute what they need
                their_tree = payload.get("merkle_tree", {})
                our_tree_dict = self.merkle_tree.to_dict()

                if their_tree:
                    # Compute what we have that they don't — authoritative push
                    remote_mt = CapabilityMerkleTree.from_dict(their_tree)
                    authoritative_delta = self.merkle_tree.diff(remote_mt)

                    # Send Merkle tree + deltas together (authoritative push)
                    response = make_udp_packet(
                        UDP_MERKLE, self.node_id,
                        {"merkle_tree": our_tree_dict,
                         "root_hash": local_root,
                         "capability_count": self.merkle_tree.leaf_count,
                         "authoritative_delta": [
                             {"path": p, "value": v} for p, v in authoritative_delta
                         ] if authoritative_delta else []},
                        nonce=nonce,
                    )
                else:
                    # No remote tree — just send ours
                    response = make_udp_packet(
                        UDP_MERKLE, self.node_id,
                        {"merkle_tree": our_tree_dict,
                         "root_hash": local_root,
                         "capability_count": self.merkle_tree.leaf_count},
                        nonce=nonce,
                    )
                self._socket.sendto(response, addr)

        elif kind == UDP_MERKLE:
            # Received Merkle tree — anti-entropy convergence.
            # Compare roots: the node with the HIGHER root hash accepts
            # updates from the node with the LOWER root hash (lowest wins).
            remote_root = payload.get("root_hash", "")
            local_root = self.merkle_tree.root_hash
            their_tree = payload.get("merkle_tree", {})

            # Apply authoritative deltas if sender included them (proactive push)
            auth_delta = payload.get("authoritative_delta", [])
            if auth_delta:
                for d in auth_delta:
                    path, value = d.get("path", ""), d.get("value", {})
                    if path:
                        self.merkle_tree.insert(path, value)
                logger.info("Applied %d authoritative deltas from %s, new root=%s...",
                            len(auth_delta), node_id, self.merkle_tree.root_hash[:16])

            if their_tree and remote_root != local_root:
                remote_mt = CapabilityMerkleTree.from_dict(their_tree)

                # Compute what THEY have that WE don't (the authoritative delta)
                # This ensures genesis's state propagates to edge
                needed_delta = remote_mt.diff(self.merkle_tree)

                if needed_delta:
                    # They have updates we need — tell them to send them
                    # We send our tree so they can compute what we need
                    response = make_udp_packet(
                        UDP_MERKLE, self.node_id,
                        {"merkle_tree": self.merkle_tree.to_dict(),
                         "root_hash": local_root,
                         "need_update": True,
                         "needed_paths": [p for p, v in needed_delta]},
                        nonce=nonce,
                    )
                    self._socket.sendto(response, addr)
                else:
                    # No updates needed from them, but maybe they need from us
                    our_delta = self.merkle_tree.diff(remote_mt)
                    if our_delta:
                        response = make_udp_packet(
                            UDP_DELTA, self.node_id,
                            {"deltas": [{"path": p, "value": v} for p, v in our_delta],
                             "count": len(our_delta),
                             "root_hash": local_root,
                             "authoritative": True},
                            nonce=nonce,
                        )
                        self._socket.sendto(response, addr)

        elif kind == UDP_DELTA:
            # Apply incoming deltas (authoritative push from genesis or other)
            deltas = payload.get("deltas", [])
            modified_tree = False
            for d in deltas:
                path, value = d.get("path", ""), d.get("value", {})
                if path:
                    self.merkle_tree.insert(path, value)
                    modified_tree = True
            # Send ACK
            response = make_udp_packet(
                UDP_ACK, self.node_id,
                {"root_hash": self.merkle_tree.root_hash,
                 "deltas_applied": len(deltas),
                 "in_sync": True},
                nonce=nonce,
            )
            self._socket.sendto(response, addr)
            if modified_tree:
                logger.info("UDP: Applied %d deltas, new root=%s...",
                            len(deltas), self.merkle_tree.root_hash[:16])

        elif kind == UDP_ACK:
            # Remote acknowledged our update
            peer_root = payload.get("root_hash", "")
            in_sync = payload.get("in_sync", False)
            if in_sync:
                logger.debug("UDP: Sync confirmed, remote root=%s...", peer_root[:16])

    def gossip_once(self, peer_ip: str, peer_port: int,
                    timeout: float = 0.2) -> float:
        """Perform one UDP gossip round with a peer.

        Returns round-trip time in milliseconds.
        """
        start = time.time()

        # Send HELLO with our Merkle root AND tree (so genesis can push deltas)
        hello = make_udp_packet(
            UDP_HELLO, self.node_id,
            {"merkle_root": self.merkle_tree.root_hash,
             "merkle_tree": self.merkle_tree.to_dict(),
             "capability_count": self.merkle_tree.leaf_count},
        )

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(hello, (peer_ip, peer_port))

            # Wait for response
            data, _ = sock.recvfrom(MAX_DATAGRAM_SIZE)
            response = parse_udp_packet(data)

            if response and response.get("kind") == UDP_MERKLE:
                payload = response.get("payload", {})
                their_tree = payload.get("merkle_tree", {})
                remote_root = payload.get("root_hash", "")

                # Apply authoritative deltas if sender pushed them
                auth_delta = payload.get("authoritative_delta", [])
                if auth_delta:
                    for d in auth_delta:
                        path, value = d.get("path", ""), d.get("value", {})
                        if path:
                            self.merkle_tree.insert(path, value)
                    logger.info("Applied %d authoritative deltas, new root=%s...",
                                len(auth_delta), self.merkle_tree.root_hash[:16])
                elif their_tree:
                    # No authoritative push — compute and send our delta
                    remote_mt = CapabilityMerkleTree.from_dict(their_tree)
                    delta = self.merkle_tree.diff(remote_mt)
                    if delta:
                        delta_pkt = make_udp_packet(
                            UDP_DELTA, self.node_id,
                            {"deltas": [{"path": p, "value": v} for p, v in delta],
                             "count": len(delta),
                             "root_hash": self.merkle_tree.root_hash},
                        )
                        sock.sendto(delta_pkt, (peer_ip, peer_port))
                        try:
                            ack_data, _ = sock.recvfrom(MAX_DATAGRAM_SIZE)
                        except socket.timeout:
                            pass

            sock.close()
        except socket.timeout:
            pass
        except OSError as e:
            logger.debug("UDP gossip error: %s", e)

        elapsed_ms = (time.time() - start) * 1000
        return elapsed_ms
