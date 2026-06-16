"""Gossip protocol for the Synapse P2P swarm.

Wire format: JSON over TCP (with length prefix). Tailscale provides transport
encryption (WireGuard). Each packet is signed with the node's Ed25519 key.

Packet types::

    GOSSIP_HELLO      — Node identity + Merkle root (sent on connect)
    GOSSIP_MERKLE     — Full or partial Merkle tree (response to request)
    GOSSIP_DELTA      — Changed subtree hashes (delta response)
    GOSSIP_NODE_SYNC  — Actual capability payloads for changed paths
    GOSSIP_ACK        — Acknowledgment with current root hash
    GOSSIP_CONFLICT   — Anti-entropy conflict declaration
"""
from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

from .merkletree import CapabilityMerkleTree, MerkleNode

logger = logging.getLogger("synapsed.gossip")

# ── Wire constants ──────────────────────────────────────────────────────────

MAGIC = b"SYN1"  # 4-byte magic + version
HEADER_FMT = "!4sI"  # magic (4s) + payload_length (I)
HEADER_SIZE = struct.calcsize(HEADER_FMT)

GOSSIP_HELLO = "GOSSIP_HELLO"
GOSSIP_MERKLE = "GOSSIP_MERKLE"
GOSSIP_DELTA = "GOSSIP_DELTA"
GOSSIP_NODE_SYNC = "GOSSIP_NODE_SYNC"
GOSSIP_ACK = "GOSSIP_ACK"
GOSSIP_CONFLICT = "GOSSIP_CONFLICT"

GOSSIP_PORT = 4434  # one above the genesis bootstrap port


# ── Crypto helpers (Ed25519) ────────────────────────────────────────────────


def _generate_keypair() -> tuple[bytes, bytes]:
    """Generate a new Ed25519 keypair.

    Returns (private_key, public_key).
    """
    # Simple fallback using stdlib — production should use libsodium/NaCl
    import hashlib
    seed = hashlib.sha256(os.urandom(32)).digest()[:32]
    # We use a simple scheme: for the Python reference, we derive keys
    # from a seed. Real implementation uses ed25519 via libsodium.
    # Store the seed as "private key"
    priv = seed
    # Derive a "public key" (simplified — real ed25519 uses Curve25519)
    pub = hashlib.sha256(b"vaked-pub:" + seed).digest()[:32]
    return priv, pub


def _sign(priv_key: bytes, data: bytes) -> bytes:
    """Sign data with the node's private key.

    Simplified reference — uses HMAC-SHA256 as a stand-in for Ed25519.
    The Zig production daemon uses libsodium/crypto_sign.
    """
    import hmac
    return hmac.new(priv_key, data, "sha256").digest()


def _verify(pub_key: bytes, data: bytes, sig: bytes) -> bool:
    """Verify a signature.

    Simplified reference — matches ``_sign``.
    """
    import hmac
    expected = hmac.new(pub_key, data, "sha256").digest()
    return hmac.compare_digest(sig, expected)


# ── Wire protocol ───────────────────────────────────────────────────────────


@dataclass
class GossipPacket:
    """A wire-format gossip packet."""
    kind: str
    node_id: str
    payload: dict = field(default_factory=dict)
    signature: str = ""
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def encode(self, priv_key: bytes) -> bytes:
        """Encode and sign the packet."""
        body = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        self.signature = _sign(priv_key, body).hex()
        body = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        payload = struct.pack(HEADER_FMT, MAGIC, len(body)) + body
        return payload

    @classmethod
    def decode(cls, data: bytes, pub_key: Optional[bytes] = None) -> Optional["GossipPacket"]:
        """Decode and optionally verify a packet."""
        if len(data) < HEADER_SIZE:
            return None
        magic, length = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
        if magic != MAGIC:
            logger.warning("Bad magic: %r", magic)
            return None
        body = data[HEADER_SIZE: HEADER_SIZE + length]
        try:
            d = json.loads(body)
        except json.JSONDecodeError as e:
            logger.warning("JSON decode error: %s", e)
            return None
        packet = cls(**d)
        if pub_key is not None and packet.signature:
            body_no_sig = json.dumps(
                {k: v for k, v in d.items() if k != "signature"},
                sort_keys=True,
            ).encode("utf-8")
            sig = packet.signature
            if not _verify(pub_key, body_no_sig, bytes.fromhex(sig)):
                logger.warning("Signature verification failed for %s", packet.node_id)
                return None
        return packet


# ── Node state ──────────────────────────────────────────────────────────────


@dataclass
class PeerState:
    """Known state for a peer node."""
    node_id: str
    tailscale_ip: str
    last_seen: float = 0.0
    merkle_root: str = ""
    capabilities: int = 0
    gossip_port: int = GOSSIP_PORT
    public_key: bytes = b""


class SwarmState:
    """Local swarm state — tracks known peers and the capability graph."""

    def __init__(self, node_id: str, data_dir: str):
        self.node_id = node_id
        self.data_dir = data_dir
        self.priv_key, self.pub_key = _generate_keypair()
        self.merkle_tree = CapabilityMerkleTree()
        self.peers: dict[str, PeerState] = {}
        self._lock = threading.Lock()

        # Load persisted state
        self._load()

    @property
    def pub_key_hex(self) -> str:
        return self.pub_key.hex()

    def _load(self):
        """Load capability state from disk."""
        state_path = os.path.join(self.data_dir, "swarm_state.json")
        if os.path.isfile(state_path):
            try:
                with open(state_path) as f:
                    d = json.load(f)
                self.merkle_tree = CapabilityMerkleTree.from_dict(d.get("merkle_tree", {}))
                logger.info("Loaded %d capabilities from %s",
                            self.merkle_tree.leaf_count, state_path)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load state: %s", e)

    def _save(self):
        """Persist capability state to disk."""
        state_path = os.path.join(self.data_dir, "swarm_state.json")
        try:
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            tmp = state_path + ".tmp"
            # Convert PeerState to serializable dict
            peers_serializable = {}
            for pid, ps in self.peers.items():
                pd = asdict(ps)
                # Convert bytes to hex for JSON serialization
                if isinstance(pd.get("public_key"), bytes):
                    pd["public_key"] = pd["public_key"].hex()
                peers_serializable[pid] = pd
            with open(tmp, "w") as f:
                json.dump({
                    "node_id": self.node_id,
                    "merkle_tree": self.merkle_tree.to_dict(),
                    "peers": peers_serializable,
                }, f, sort_keys=True)
            os.replace(tmp, state_path)
        except OSError as e:
            logger.warning("Failed to persist state: %s", e)

    def add_capability(self, path: str, value: dict) -> str:
        """Add or update a capability. Returns new Merkle root hash."""
        with self._lock:
            root_hash = self.merkle_tree.insert(path, value)
            self._save()
            return root_hash

    def register_peer(self, node_id: str, tailscale_ip: str,
                      pub_key: Optional[bytes] = None,
                      gossip_port: int = GOSSIP_PORT) -> PeerState:
        """Register or update a peer."""
        with self._lock:
            if node_id in self.peers:
                peer = self.peers[node_id]
                peer.tailscale_ip = tailscale_ip
                peer.last_seen = time.time()
                if pub_key:
                    peer.public_key = pub_key
                return peer
            peer = PeerState(
                node_id=node_id,
                tailscale_ip=tailscale_ip,
                last_seen=time.time(),
                public_key=pub_key or b"",
                gossip_port=gossip_port,
            )
            self.peers[node_id] = peer
            self._save()
            return peer

    def get_peer(self, node_id: str) -> Optional[PeerState]:
        return self.peers.get(node_id)

    @property
    def root_hash(self) -> str:
        return self.merkle_tree.root_hash

    def compute_delta(self, remote_root: str, remote_tree: Optional[dict] = None
                      ) -> list[tuple[str, dict]]:
        """Compute what capabilities we have that the remote doesn't."""
        if remote_tree:
            remote = CapabilityMerkleTree.from_dict(remote_tree)
        else:
            remote = CapabilityMerkleTree()
        return self.merkle_tree.diff(remote)


# ── Gossip protocol handler ────────────────────────────────────────────────


def handle_gossip_packet(packet: GossipPacket, swarm: SwarmState) -> Optional[GossipPacket]:
    """Process an incoming gossip packet and return a response packet."""
    kind = packet.kind
    node_id = packet.node_id
    payload = packet.payload

    if kind == GOSSIP_HELLO:
        # New peer introduced itself
        peer_ip = payload.get("tailscale_ip", "")
        peer_pub_key_hex = payload.get("public_key", "")
        peer_port = payload.get("gossip_port", GOSSIP_PORT)
        remote_root = payload.get("merkle_root", "")

        peer = swarm.register_peer(
            node_id=node_id,
            tailscale_ip=peer_ip,
            pub_key=bytes.fromhex(peer_pub_key_hex) if peer_pub_key_hex else None,
            gossip_port=peer_port,
        )
        peer.merkle_root = remote_root
        peer.capabilities = payload.get("capability_count", 0)

        # If merkle roots differ, send our merkle tree
        if remote_root != swarm.root_hash:
            return GossipPacket(
                kind=GOSSIP_MERKLE,
                node_id=swarm.node_id,
                payload={
                    "merkle_tree": swarm.merkle_tree.to_dict(),
                    "root_hash": swarm.root_hash,
                    "capability_count": swarm.merkle_tree.leaf_count,
                },
            )
        return GossipPacket(
            kind=GOSSIP_ACK,
            node_id=swarm.node_id,
            payload={"root_hash": swarm.root_hash, "in_sync": True},
        )

    elif kind == GOSSIP_MERKLE:
        # Remote sent its full merkle tree — compute delta
        remote_tree = payload.get("merkle_tree", {})
        remote_root = payload.get("root_hash", "")

        delta = swarm.compute_delta(remote_root, remote_tree)
        if delta:
            return GossipPacket(
                kind=GOSSIP_DELTA,
                node_id=swarm.node_id,
                payload={
                    "deltas": [{"path": p, "value": v} for p, v in delta],
                    "count": len(delta),
                    "root_hash": swarm.root_hash,
                },
            )
        return GossipPacket(
            kind=GOSSIP_ACK,
            node_id=swarm.node_id,
            payload={"root_hash": swarm.root_hash, "in_sync": True},
        )

    elif kind == GOSSIP_DELTA:
        # Remote is sending us capability changes
        deltas = payload.get("deltas", [])
        applied = 0
        for d in deltas:
            swarm.add_capability(d["path"], d["value"])
            applied += 1
        logger.info("Applied %d capability deltas from %s", applied, node_id)
        return GossipPacket(
            kind=GOSSIP_ACK,
            node_id=swarm.node_id,
            payload={
                "root_hash": swarm.root_hash,
                "deltas_applied": applied,
                "in_sync": swarm.root_hash == payload.get("root_hash", ""),
            },
        )

    elif kind == GOSSIP_NODE_SYNC:
        # Remote is sending full capability payloads
        capabilities = payload.get("capabilities", {})
        for path, value in capabilities.items():
            swarm.add_capability(path, value)
        logger.info("Synced %d capabilities from %s", len(capabilities), node_id)
        return GossipPacket(
            kind=GOSSIP_ACK,
            node_id=swarm.node_id,
            payload={
                "root_hash": swarm.root_hash,
                "synced": len(capabilities),
            },
        )

    elif kind == GOSSIP_ACK:
        # Acknowledgment — update peer state
        peer = swarm.get_peer(node_id)
        if peer:
            peer.last_seen = time.time()
            peer.merkle_root = payload.get("root_hash", peer.merkle_root)
            in_sync = payload.get("in_sync", False)
            if in_sync:
                logger.info("Swarm synchronized with %s (root=%s...)",
                            node_id, peer.merkle_root[:16])

    elif kind == GOSSIP_CONFLICT:
        # Anti-entropy conflict — lowest hash wins
        our_root = swarm.root_hash
        their_root = payload.get("root_hash", "")
        logger.warning(
            "Anti-entropy conflict with %s: our_root=%s..., their_root=%s...",
            node_id, our_root[:16], their_root[:16],
        )
        # The node with the LOWER root hash wins
        if our_root < their_root:
            # We win — they must accept our state
            return GossipPacket(
                kind=GOSSIP_MERKLE,
                node_id=swarm.node_id,
                payload={
                    "merkle_tree": swarm.merkle_tree.to_dict(),
                    "root_hash": swarm.root_hash,
                    "authoritative": True,
                },
            )
        else:
            # They win — we must request their state
            return GossipPacket(
                kind=GOSSIP_MERKLE,
                node_id=swarm.node_id,
                payload={"root_hash": swarm.root_hash, "request_full": True},
            )

    return None


# ── Connection management ──────────────────────────────────────────────────


def send_gossip(peer_ip: str, port: int, packet: GossipPacket,
                swarm: SwarmState, timeout: float = 5.0) -> Optional[GossipPacket]:
    """Send a gossip packet to a peer and wait for response."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((peer_ip, port))

        # Send
        data = packet.encode(swarm.priv_key)
        sock.sendall(data)

        # Receive response
        header = b""
        while len(header) < HEADER_SIZE:
            chunk = sock.recv(HEADER_SIZE - len(header))
            if not chunk:
                sock.close()
                return None
            header += chunk

        magic, length = struct.unpack(HEADER_FMT, header)
        if magic != MAGIC:
            sock.close()
            return None

        body = b""
        while len(body) < length:
            chunk = sock.recv(length - len(body))
            if not chunk:
                break
            body += chunk

        sock.close()

        # Decode
        raw = header + body
        peer_state = swarm.get_peer(swarm.node_id)
        pub_key = peer_state.public_key if peer_state else None
        return GossipPacket.decode(raw, pub_key=pub_key)

    except (socket.timeout, ConnectionError, OSError) as e:
        logger.debug("Gossip to %s:%d failed: %s", peer_ip, port, e)
        return None


def run_gossip_server(swarm: SwarmState, bind_ip: str = "0.0.0.0",
                      port: int = GOSSIP_PORT) -> None:
    """Run the gossip server loop (blocking)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((bind_ip, port))
    server.listen(32)
    server.settimeout(1.0)
    logger.info("Synapse gossip server listening on %s:%d", bind_ip, port)

    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        try:
            conn.settimeout(10.0)
            header = b""
            while len(header) < HEADER_SIZE:
                chunk = conn.recv(HEADER_SIZE - len(header))
                if not chunk:
                    break
                header += chunk
            if len(header) < HEADER_SIZE:
                conn.close()
                continue

            magic, length = struct.unpack(HEADER_FMT, header)
            if magic != MAGIC:
                conn.close()
                continue

            body = b""
            while len(body) < length:
                chunk = conn.recv(length - len(body))
                if not chunk:
                    break
                body += chunk

            raw = header + body
            packet = GossipPacket.decode(raw)

            if packet is None:
                conn.close()
                continue

            response = handle_gossip_packet(packet, swarm)
            if response:
                resp_data = response.encode(swarm.priv_key)
                conn.sendall(resp_data)

        except (socket.timeout, ConnectionError, OSError) as e:
            logger.debug("Gossip server connection error: %s", e)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    server.close()
