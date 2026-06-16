"""TCP server for the Vaked genesis bootstrap daemon.

Listens on a configured address:port, accepts bootstrap handshakes, and
maintains a lightweight eventd-inspired audit log of all bootstrap exchanges.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import signal
import sys
import time
import threading
from typing import Optional

from .bootstrap import (
    EventdAnchor,
    TopologyEpoch,
    perform_handshake,
    asdict,
)

logger = logging.getLogger("genesisd.server")

# ── Audit log (eventd-compatible) ──────────────────────────────────────────

GENESIS_HASH = "0" * 64


def _canonical_json(obj: dict) -> bytes:
    """Canonical JSON for chain hashing (sorted keys, no whitespace, UTF-8)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _chain_hash(prev: str, payload: bytes) -> str:
    """sha256(prev || payload)."""
    import hashlib
    h = hashlib.sha256()
    h.update(prev.encode("ascii"))
    h.update(payload)
    return h.hexdigest()


class AuditLog:
    """Minimal append-only hash chain for genesis bootstrap events.

    Follows the eventd core format for compatibility::

        {"seq": N, "prev": "<sha256 hex>", "payload": {...}, "hash": "<sha256 hex>"}
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._seq = -1
        self._tail_hash = GENESIS_HASH
        self._load()

    def _load(self):
        """Load existing log to find the tail."""
        log_dir = os.path.dirname(self.path)
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        # Make the log directory world-writable so DynamicUser (which may change
        # UID on restart) can always create/append to the audit file.
        try:
            os.chmod(log_dir, 0o777)
        except OSError:
            pass
        if not os.path.isfile(self.path):
            return
        prev = GENESIS_HASH
        seq = -1
        with open(self.path, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seq = entry.get("seq", -1)
                prev = entry.get("hash", GENESIS_HASH)
        self._seq = seq
        self._tail_hash = prev

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def tail_hash(self) -> str:
        return self._tail_hash

    def append(self, payload: dict) -> dict:
        """Append one entry to the hash chain and fsync.

        Returns the entry dict.
        """
        with self._lock:
            self._seq += 1
            prev = self._tail_hash
            payload_bytes = _canonical_json(payload)
            h = _chain_hash(prev, payload_bytes)
            entry = {
                "seq": self._seq,
                "prev": prev,
                "payload": payload,
                "hash": h,
            }
            line = json.dumps(entry, sort_keys=True).encode("utf-8") + b"\n"
            with open(self.path, "ab") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            # Make the log file world-writable so DynamicUser survives restarts.
            try:
                os.chmod(self.path, 0o666)
            except OSError:
                pass
            self._tail_hash = h
            return entry

    def tip(self) -> EventdAnchor:
        """Return the current chain tip as an EventdAnchor."""
        return EventdAnchor(
            seq=self._seq if self._seq >= 0 else 0,
            hash=self._tail_hash,
            prev=self._tail_hash if self._seq <= 0 else "unknown",
        )


# ── Connection handler ───────────────────────────────────────────────────────


def _handle_peer(conn: socket.socket,
                 addr: tuple,
                 genesis_id: str,
                 genesis_ip: str,
                 audit: AuditLog,
                 topology: TopologyEpoch,
                 ) -> None:
    """Handle one bootstrap connection in a dedicated thread."""
    logger.info("peer connected from %s:%d", addr[0], addr[1])
    try:
        frames = perform_handshake(
            genesis_id=genesis_id,
            genesis_ip=genesis_ip,
            chain_tip=audit.tip(),
            topology=topology,
            peer_sock=conn,
        )
        # Audit the bootstrap exchange
        audit.append({
            "kind": "bootstrap_handshake",
            "peer_addr": f"{addr[0]}:{addr[1]}",
            "frames": frames,
            "timestamp": time.time(),
        })
    except Exception as e:
        logger.error("handshake error from %s: %s", addr[0], e, exc_info=True)
    finally:
        try:
            conn.close()
        except OSError:
            pass


# ── Server ───────────────────────────────────────────────────────────────────


class GenesisServer:
    """TCP server for the Vaked genesis bootstrap daemon.

    Args:
        bind_ip: IP to bind to (e.g., "100.105.72.88" for tailscale0).
        bind_port: TCP port (default 4433).
        genesis_id: Hostname or identifier for this genesis node.
        log_dir: Directory for the audit log (default /var/lib/vaked/genesis/log).
    """

    def __init__(self,
                 bind_ip: str = "127.0.0.1",
                 bind_port: int = 4433,
                 genesis_id: str = "genesis.vaked.dev",
                 log_dir: Optional[str] = None,
                 ):
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.genesis_id = genesis_id
        log_dir = log_dir or os.environ.get(
            "GENESISD_LOG_DIR",
            os.path.join(os.environ.get("STATE_DIRECTORY", "/tmp"), "vaked-genesis", "log"))
        self.audit = AuditLog(os.path.join(log_dir, "genesis.jsonl"))
        self.topology = TopologyEpoch(epoch=0, members=1)
        self._server: Optional[socket.socket] = None
        self._shutdown = threading.Event()

    @property
    def listen_address(self) -> str:
        return f"{self.bind_ip}:{self.bind_port}"

    def serve_forever(self) -> None:
        """Start accepting bootstrap connections (blocking)."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Prevent SIGPIPE on macOS/Linux
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        try:
            self._server.bind((self.bind_ip, self.bind_port))
            self._server.listen(128)
        except OSError as e:
            logger.error("failed to bind to %s: %s", self.listen_address, e)
            sys.exit(1)

        logger.info("genesis bootstrap daemon listening on %s",
                    self.listen_address)

        # Log the genesis event
        self.audit.append({
            "kind": "genesis_start",
            "genesis_id": self.genesis_id,
            "bind_ip": self.bind_ip,
            "bind_port": self.bind_port,
            "timestamp": time.time(),
        })

        self._server.settimeout(1.0)  # allow periodic shutdown checks
        while not self._shutdown.is_set():
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(
                target=_handle_peer,
                args=(conn, addr, self.genesis_id, self.bind_ip,
                      self.audit, self.topology),
                daemon=True,
            )
            t.start()

        logger.info("genesis server shutting down")
        self._server.close()

    def shutdown(self) -> None:
        """Signal the server to shut down."""
        self._shutdown.set()


def run_server(bind_ip: str = "127.0.0.1",
               bind_port: int = 4433,
               genesis_id: str = "genesis.vaked.dev",
               log_dir: Optional[str] = None,
               ) -> None:
    """Entry point: create and run the genesis server (blocking)."""
    logging.basicConfig(
        level=logging.INFO,
        format="genesisd[%(process)d]: %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    server = GenesisServer(
        bind_ip=bind_ip,
        bind_port=bind_port,
        genesis_id=genesis_id,
        log_dir=log_dir,
    )

    # Handle SIGTERM/SIGINT gracefully
    def _signal_handler(signum, frame):
        logger.info("received signal %d, shutting down", signum)
        server.shutdown()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    server.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="vaked genesis bootstrap daemon")
    parser.add_argument("--bind-ip", default="127.0.0.1",
                        help="IP address to bind to (default: 127.0.0.1)")
    parser.add_argument("--bind-port", type=int, default=4433,
                        help="TCP port (default: 4433)")
    parser.add_argument("--genesis-id", default="genesis.vaked.dev",
                        help="Genesis node identifier (default: genesis.vaked.dev)")
    parser.add_argument("--log-dir",
                        help="Directory for the audit log")
    args = parser.parse_args()
    run_server(**vars(args))
