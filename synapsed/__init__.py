"""synapsed — P2P capability-graph gossip protocol for the Vaked swarm.

Synapse is the gossip layer that lets Vaked nodes discover each other and
synchronize capability-graph state without a central registry.

Architecture::

    Node A                          Node B
    ┌──────────┐                   ┌──────────┐
    │ Merkle   │ ◄─── gossip ───►  │ Merkle   │
    │ Tree     │      UDP/JSON     │ Tree     │
    │ (caps)   │                   │ (caps)   │
    └────┬─────┘                   └────┬─────┘
         │                              │
    ┌────▼─────┐                   ┌────▼─────┐
    │ Anti-    │                   │ Anti-    │
    │ Entropy  │                   │ Entropy  │
    │ Loop     │                   │ Loop     │
    └──────────┘                   └──────────┘

    Gossip flow:
    1. A sends GOSSIP_HELLO + its Merkle root to B
    2. B compares root hashes — if different, requests delta
    3. A sends MERKLE_DELTA: changed subtree hashes
    4. B requests the actual capability nodes for changed subtrees
    5. A sends NODE_SYNC: the capability payloads
    6. B applies and verifies chain integrity

Protocol: JSON over TCP (for now; io_uring + eBPF fast-path planned).
Encryption: Provided by Tailscale WireGuard at the transport layer.
Signing: Ed25519 node keys, verified on each gossip packet.

Mantra: No central registry. Everything is P2P over Tailscale. State is
convergent: the node with the lowest Merkle root hash wins conflicts.
"""
from __future__ import annotations

VERSION = "0.1.0"
PROTOCOL_VERSION = "1"  # Bump on wire-incompatible changes
