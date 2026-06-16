"""vaked-genesis — the bootstrap genesis daemon for the Vaked mesh.

The genesis node is the bootstrap entry point for the Vaked peer-to-peer mesh.
It is discovered via DNS SRV (``_vaked-bootstrap._tcp.vaked.dev`` → the host),
and responds to bootstrap handshake requests from joining nodes with the genesis
identity, the current topology epoch, and the eventd chain anchor.

This is the **Python reference / oracle** implementation, following the #15
pattern established by eventd and agent_guardd: Python defines the wire bytes
and the decision logic; a future Zig daemon reproduces them.

Roster position (docs/runtime/README.md): genesis node — the bootstrap anchor
in the Vaked mesh. Provides the initial discovery endpoint that SRV records
resolve, and seeds the eventd hash chain from its local log.

Architecture::

    Joining node                  genesisd (port 4433)
         │  TCP connect               │
         ├── HCP preamble ──────────►  │
         │  ◄── GenesisHello ────────  │      (identity + chain anchor)
         │  ◄── EventdAnchor ────────  │      (seq, hash, prev)
         │  ◄── TopologyEpoch ────────  │      (current epoch + member count)
         │  ◄── EndOfBootstrap ───────  │
         │  TCP close                  │
         │                              │
         │  (Both sides append the     │
         │   handshake to eventd.)     │

"""
from __future__ import annotations

__all__ = [
    "GENESIS_VERSION",
    "GenesisIdentity",
    "BootstrapHandshake",
    "GenesisServer",
    "run_server",
]

GENESIS_VERSION = "0.1.0"
