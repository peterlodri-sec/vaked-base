"""Watchdog — orchestrates L1 monitoring and restart with circuit breaker.

The watchdog runs a periodic health check loop. If L1 fails a check:
1. Verify it's not us (recursion safety).
2. Check the circuit breaker (max 3 restarts / 5 min).
3. If breaker is open → Emergency Hold: kill tailscale0, log emergency.
4. Otherwise → ``systemctl restart ralphd`` and commit a WATCHDOG_RESET_EVENT
   to the Oculus ledger (the genesis audit log).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from .monitor import (
    HealthReport,
    MonitorTimeout,
    MonitorMemoryExceeded,
    MonitorChainBroken,
    check_l1_health,
    resolve_ralph_pid,
)

logger = logging.getLogger("meta-ralphd.watchdog")

# ── Constants ───────────────────────────────────────────────────────────────

WATCHDOG_RESET_EVENT = "WATCHDOG_RESET_EVENT"
WATCHDOG_EMERGENCY_EVENT = "WATCHDOG_EMERGENCY_HOLD"
CIRCUIT_BREAKER_MAX_RESTARTS = 3
CIRCUIT_BREAKER_WINDOW_SEC = 300  # 5 minutes
EMERGENCY_TAILSCALE_INTERFACE = os.environ.get(
    "META_RALPH_TAILSCALE_IF", "tailscale0"
)

# ── Audit log (Oculus ledger) ───────────────────────────────────────────────


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _chain_hash(prev: str, payload: dict) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(prev.encode("ascii"))
    h.update(_canonical_json(payload))
    return h.hexdigest()


class OculusLedger:
    """Append-only, hash-chained event log for watchdog events.

    Compatible with the eventd/ralphcore format so the same verification
    tooling works across all layers.
    """

    def __init__(self, path: str):
        self.path = path
        self._seq = -1
        self._tail_hash = "0" * 64
        self._load()

    def _load(self):
        if not os.path.isfile(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            return
        prev = "0" * 64
        with open(self.path, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._seq = entry.get("seq", -1)
                prev = entry.get("hash", "0" * 64)
        self._tail_hash = prev

    def append(self, payload: dict) -> dict:
        self._seq += 1
        payload_bytes = _canonical_json(payload)
        h = _chain_hash(self._tail_hash, payload)
        entry = {
            "seq": self._seq,
            "prev": self._tail_hash,
            "payload": payload,
            "hash": h,
        }
        line = json.dumps(entry, sort_keys=True).encode("utf-8") + b"\n"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self._tail_hash = h
        return entry


# ── Circuit Breaker ─────────────────────────────────────────────────────────


@dataclass
class CircuitBreaker:
    """Tracks restart attempts and opens (triggers emergency hold) when
    ``max_restarts`` are exceeded within ``window_seconds``."""

    max_restarts: int = CIRCUIT_BREAKER_MAX_RESTARTS
    window_seconds: int = CIRCUIT_BREAKER_WINDOW_SEC
    _attempts: list[float] = field(default_factory=list)
    _open: bool = False

    def record_attempt(self) -> None:
        """Record a restart attempt at the current time."""
        now = time.time()
        self._attempts.append(now)
        # Prune old entries outside the window
        self._attempts = [t for t in self._attempts if now - t < self.window_seconds]

    @property
    def is_open(self) -> bool:
        """The breaker opens when restart count >= max in the sliding window."""
        if self._open:
            return True
        now = time.time()
        recent = [t for t in self._attempts if now - t < self.window_seconds]
        if len(recent) >= self.max_restarts:
            self._open = True
            return True
        return False

    @property
    def recent_attempts(self) -> int:
        now = time.time()
        return len([t for t in self._attempts if now - t < self.window_seconds])

    def reset(self) -> None:
        """Reset the breaker (called after emergency hold is resolved)."""
        self._attempts = []
        self._open = False


# ── Recursion Safety ────────────────────────────────────────────────────────


def _is_self(pid: int) -> bool:
    """Check if ``pid`` is the current process (recursion guard)."""
    return pid == os.getpid()


# ── System Actions ──────────────────────────────────────────────────────────


def restart_l1() -> bool:
    """Restart the ``ralphd`` service via systemd.

    Returns True if the command succeeded.
    """
    # Recursion safety: verify the target PID is NOT us
    target_pid = resolve_ralph_pid()
    if target_pid is not None and _is_self(target_pid):
        logger.error("RECURSION DETECTED: refusing to restart self (L2)")
        return False

    logger.warning("Issuing systemctl restart ralphd")
    try:
        result = subprocess.run(
            ["systemctl", "restart", "ralphd"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info("ralphd restart succeeded")
            return True
        else:
            logger.error(
                "ralphd restart failed: %s", result.stderr.strip()
            )
            return False
    except subprocess.TimeoutExpired:
        logger.error("ralphd restart timed out after 30s")
        return False
    except FileNotFoundError:
        logger.error("systemctl not found — cannot restart ralphd")
        return False


def emergency_hold() -> bool:
    """Circuit breaker opened: kill tailscale0 to isolate, return True.

    The emergency hold disconnects the node from the Tailscale mesh to
    prevent cascading failure. A human operator must re-enable Tailscale
    and reset the breaker after investigating.
    """
    logger.critical(
        "EMERGENCY HOLD: circuit breaker tripped. "
        "Disconnecting %s", EMERGENCY_TAILSCALE_INTERFACE
    )
    try:
        # Bring down the tailscale interface
        result = subprocess.run(
            ["ip", "link", "set", "dev", EMERGENCY_TAILSCALE_INTERFACE, "down"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.critical("Tailscale interface %s taken down", EMERGENCY_TAILSCALE_INTERFACE)
        else:
            logger.error("Failed to take down tailscale: %s", result.stderr.strip())

        # Also try tailscale logout as a stronger measure
        subprocess.run(
            ["tailscale", "logout"],
            capture_output=True, text=True, timeout=10,
        )
        logger.critical("Tailscale logged out")
    except subprocess.TimeoutExpired:
        logger.error("Emergency hold timed out")
    except FileNotFoundError:
        logger.error("ip/tailscale command not found")
        return False
    return True


# ── Health-Check Loop ───────────────────────────────────────────────────────


def run_watchdog(
    check_interval_sec: float = 5.0,
    journal_max_stale: float = 10.0,
    memory_max_mb: int = 200,
    ledger_path: Optional[str] = None,
) -> None:
    """Main watchdog loop — runs health checks and responds to failures.

    Args:
        check_interval_sec: How often to run the health check.
        journal_max_stale: Max seconds since L1's last journal write.
        memory_max_mb: Max RSS memory for L1 in MiB.
        ledger_path: Path to the Oculus ledger JSONL file.
    """
    if ledger_path is None:
        ledger_path = os.path.join(
            os.environ.get("STATE_DIRECTORY", "/var/lib/meta-ralphd"),
            "oculus.jsonl",
        )

    ledger = OculusLedger(ledger_path)
    breaker = CircuitBreaker()

    logger.info(
        "Meta-Ralph watchdog starting (interval=%ss, journal_stale=%ss, "
        "memory_max=%sMiB, ledger=%s)",
        check_interval_sec, journal_max_stale, memory_max_mb, ledger_path,
    )

    # Log genesis event
    ledger.append({
        "kind": "meta_ralph_start",
        "version": "0.1.0",
        "pid": os.getpid(),
        "timestamp": time.time(),
    })

    while True:
        time.sleep(check_interval_sec)

        report = check_l1_health()
        if report.healthy:
            continue

        # Unhealthy — determine what's wrong
        pid = resolve_ralph_pid()
        if pid is not None and _is_self(pid):
            logger.critical(
                "RECURSION DETECTED: L2 resolved to self (PID %s). "
                "Refusing restart — this should never happen.",
                pid,
            )
            ledger.append({
                "kind": "RECURSION_DETECTED",
                "pid": pid,
                "timestamp": time.time(),
            })
            continue

        # Check circuit breaker before acting
        if breaker.is_open:
            logger.critical(
                "Circuit breaker OPEN (%d restarts in %ds window). "
                "Entering EMERGENCY HOLD.",
                breaker.recent_attempts, CIRCUIT_BREAKER_WINDOW_SEC,
            )
            emergency_hold()
            ledger.append({
                "kind": WATCHDOG_EMERGENCY_EVENT,
                "reason": "circuit_breaker_open",
                "restarts": breaker.recent_attempts,
                "errors": report.errors,
                "timestamp": time.time(),
            })
            # Once in emergency hold, stop the loop — human must intervene
            logger.critical(
                "Watchdog entering sleep. Human operator intervention required "
                "to re-enable Tailscale and reset circuit breaker."
            )
            # Signal via the ledger
            ledger.append({
                "kind": "EMERGENCY_HOLD_ACTIVE",
                "message": "Operator intervention required",
                "timestamp": time.time(),
            })
            # Sleep indefinitely — the loop pauses until manual reset
            while True:
                time.sleep(60)

        # Perform the restart
        logger.warning(
            "L1 unhealthy (errors: %s). Initiating restart.",
            "; ".join(report.errors),
        )
        breaker.record_attempt()
        success = restart_l1()

        # Commit watchdog event to Oculus ledger
        ledger.append({
            "kind": WATCHDOG_RESET_EVENT,
            "trigger": report.errors,
            "restart_attempt": breaker.recent_attempts,
            "success": success,
            "timestamp": time.time(),
        })

        if not success:
            logger.error("Restart failed — will retry on next check cycle.")
