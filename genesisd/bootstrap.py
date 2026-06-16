"""Bootstrap protocol for the Vaked genesis node.

The wire format is newline-delimited JSON (JSONL), following the eventd pattern.
The genesis daemon speaks a minimal bootstrap sub-protocol over TCP:

Server flow::

    Recv: {"kind": "BootstrapHello", "version": "0.1.0", "node_id": "<peer-id>"}
    Send: {"kind": "GenesisHello", "version": "0.1.0", "genesis_id": "<host>"}
    Send: {"kind": "EventdAnchor", "seq": <int>, "hash": "<hex>", "prev": "<hex>"}
    Send: {"kind": "TopologyEpoch", "epoch": <int>, "members": <int>}
    Send: {"kind": "EndOfBootstrap"}
    Close

All frames are valid JSON one-liners terminated by ``\\n``.
"""
from __future__ import annotations

import json
import logging
import socket
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("genesisd.bootstrap")

# ── Wire frame kinds ────────────────────────────────────────────────────────

FRAME_BOOTSTRAP_HELLO = "BootstrapHello"
FRAME_GENESIS_HELLO = "GenesisHello"
FRAME_EVENTD_ANCHOR = "EventdAnchor"
FRAME_TOPOLOGY_EPOCH = "TopologyEpoch"
FRAME_END_OF_BOOTSTRAP = "EndOfBootstrap"
FRAME_ERROR = "BootstrapError"

# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class BootstrapHello:
    """Sent by the joining peer to initiate the bootstrap handshake."""
    kind: str = FRAME_BOOTSTRAP_HELLO
    version: str = "0.1.0"
    node_id: str = ""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])


@dataclass
class GenesisHello:
    """Sent by the genesis node in response to BootstrapHello."""
    kind: str = FRAME_GENESIS_HELLO
    version: str = "0.1.0"
    genesis_id: str = ""
    genesis_ip: str = ""
    genesis_port: int = 4433
    session_id: str = ""


@dataclass
class EventdAnchor:
    """The current tip of the genesis eventd hash chain."""
    kind: str = FRAME_EVENTD_ANCHOR
    seq: int = 0
    hash: str = "0" * 64
    prev: str = "0" * 64


@dataclass
class TopologyEpoch:
    """The current topology epoch known to the genesis node."""
    kind: str = FRAME_TOPOLOGY_EPOCH
    epoch: int = 0
    members: int = 1


@dataclass
class EndOfBootstrap:
    """Signals the end of the bootstrap exchange."""
    kind: str = FRAME_END_OF_BOOTSTRAP


@dataclass
class BootstrapError:
    """An error occurred during the bootstrap exchange."""
    kind: str = FRAME_ERROR
    code: str = ""
    message: str = ""


# ── Wire helpers ─────────────────────────────────────────────────────────────


def read_frame(sock: socket.socket, buf: bytes = b"", timeout: float = 10.0
               ) -> Optional[dict]:
    """Read one newline-delimited JSON frame from ``sock``.

    Returns ``None`` on timeout or connection close.
    """
    sock.settimeout(timeout)
    while b"\n" not in buf:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            logger.debug("read_frame timeout after %.1fs", timeout)
            return None
        except ConnectionError as e:
            logger.debug("read_frame connection error: %s", e)
            return None
        if not chunk:
            return None
        buf += chunk
    line, _, buf = buf.partition(b"\n")
    if not line.strip():
        return {}
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning("read_frame json decode error: %s (line=%r)", e, line[:120])
        return None


def write_frame(sock: socket.socket, obj: dict) -> bool:
    """Write one JSON frame (with newline) to ``sock``.

    Returns True on success, False on connection error.
    """
    try:
        data = json.dumps(obj, sort_keys=True).encode("utf-8") + b"\n"
        sock.sendall(data)
        return True
    except ConnectionError as e:
        logger.debug("write_frame connection error: %s", e)
        return False


# ── Handshake logic ──────────────────────────────────────────────────────────


def perform_handshake(genesis_id: str,
                      genesis_ip: str,
                      chain_tip: EventdAnchor,
                      topology: TopologyEpoch,
                      peer_sock: socket.socket,
                      ) -> list[dict]:
    """Run the bootstrap handshake with one connecting peer.

    Returns the list of frames exchanged (for audit logging).
    """
    frames: list[dict] = []

    # 1. Read BootstrapHello from peer
    hello = read_frame(peer_sock)
    if hello is None or hello.get("kind") != FRAME_BOOTSTRAP_HELLO:
        logger.info("peer sent invalid bootstrap hello: %r", hello)
        write_frame(peer_sock, asdict(BootstrapError(
            code="INVALID_HELLO",
            message="Expected BootstrapHello frame",
        )))
        frames.append({"direction": "recv", "frame": hello or {}})
        frames.append({"direction": "send", "frame": {
            "kind": FRAME_ERROR, "code": "INVALID_HELLO"}})
        return frames

    session_id = hello.get("session_id", uuid.uuid4().hex[:16])
    frames.append({"direction": "recv", "frame": hello})

    # 2. Send GenesisHello
    genesis_hello = GenesisHello(
        genesis_id=genesis_id,
        genesis_ip=genesis_ip,
        session_id=session_id,
    )
    ok = write_frame(peer_sock, asdict(genesis_hello))
    frames.append({"direction": "send", "frame": asdict(genesis_hello)})
    if not ok:
        return frames

    # 3. Send EventdAnchor
    ok = write_frame(peer_sock, asdict(chain_tip))
    frames.append({"direction": "send", "frame": asdict(chain_tip)})
    if not ok:
        return frames

    # 4. Send TopologyEpoch
    ok = write_frame(peer_sock, asdict(topology))
    frames.append({"direction": "send", "frame": asdict(topology)})
    if not ok:
        return frames

    # 5. Send EndOfBootstrap
    write_frame(peer_sock, asdict(EndOfBootstrap()))
    frames.append({"direction": "send", "frame": {"kind": FRAME_END_OF_BOOTSTRAP}})

    logger.info("handshake complete with peer %s (session=%s)",
                hello.get("node_id", "?"), session_id)
    return frames
