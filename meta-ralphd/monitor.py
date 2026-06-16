"""L1 (Ralph) monitoring — CPU, memory, Merkle journal integrity.

All monitors raise ``MonitorError`` on failure so the watchdog can
distinguish a health violation from a transient I/O error.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

# ── Constants ───────────────────────────────────────────────────────────────

RALPH_STATE_DIR = os.path.expanduser(
    os.environ.get("RALPH_STATE_DIR", os.path.join(os.path.sep, "var", "lib", "ralph"))
)
RALPH_EVENTS_PATH = os.path.join(RALPH_STATE_DIR, "events.jsonl")
RALPH_PID_PATH = os.path.join(RALPH_STATE_DIR, "ralph.pid")

GENESIS_HASH = "0" * 64

# ── Exceptions ──────────────────────────────────────────────────────────────


class MonitorError(RuntimeError):
    """Raised when a health check fails."""


class MonitorTimeout(MonitorError):
    """L1 hasn't updated its journal within the deadline."""


class MonitorMemoryExceeded(MonitorError):
    """L1's memory usage exceeds the threshold."""


class MonitorChainBroken(MonitorError):
    """L1's hash chain is corrupted or tampered."""


# ── Helpers ─────────────────────────────────────────────────────────────────


def _canonical_json(obj: dict) -> bytes:
    """Canonical JSON for chain hashing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _chain_hash(prev: str, payload: dict) -> str:
    """sha256(prev || canonical_json(payload))."""
    import hashlib
    h = hashlib.sha256()
    h.update(prev.encode("ascii"))
    h.update(_canonical_json(payload))
    return h.hexdigest()


# ── PID Resolution ──────────────────────────────────────────────────────────


def resolve_ralph_pid() -> Optional[int]:
    """Find the PID of the running ``ralph`` process.

    Checks the pidfile first, then falls back to ``pgrep -f ralph``.
    Returns ``None`` if ralph is not running.
    """
    # Try pidfile
    if os.path.isfile(RALPH_PID_PATH):
        try:
            with open(RALPH_PID_PATH) as f:
                pid = int(f.read().strip())
            # Verify the PID is still alive and is ralph
            if os.path.isdir(f"/proc/{pid}"):
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                        cmdline = f.read().decode("utf-8", errors="replace")
                    if "ralph" in cmdline:
                        return pid
                except (OSError, IOError):
                    pass
        except (ValueError, OSError, IOError):
            pass

    # Fallback: pgrep (exclude meta-ralphd — must not match our own process)
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "ralph"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                pid = int(line.strip())
                # Recursion safety checks:
                # 1. Must not be our own PID
                # 2. Must not be "meta-ralphd" (pgrep -f "ralph" matches us)
                cmdline = ""
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                        cmdline = f.read().decode("utf-8", errors="replace")
                except (OSError, IOError):
                    pass
                if pid == os.getpid():
                    continue
                if "meta-ralphd" in cmdline or "meta_ralphd" in cmdline:
                    continue
                if "ralph" in cmdline:
                    return pid
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    return None


def is_ralph_running() -> bool:
    """Check if ralph (L1) is currently running."""
    return resolve_ralph_pid() is not None


# ── CPU Monitor ─────────────────────────────────────────────────────────────


def get_cpu_percent(pid: int, interval: float = 1.0) -> float:
    """Measure CPU usage of a process over ``interval`` seconds.

    Returns percentage (0.0–100.0 * ncpus).
    """
    try:
        stat_path = f"/proc/{pid}/stat"
        with open(stat_path) as f:
            parts = f.read().split()
        utime = int(parts[13])
        stime = int(parts[14])
        cutime = int(parts[15])
        cstime = int(parts[16])
        total1 = utime + stime + cutime + cstime

        with open("/proc/stat") as f:
            cpu_line = f.readline().split()
        host_total1 = sum(int(v) for v in cpu_line[1:])

        time.sleep(interval)

        with open(stat_path) as f:
            parts = f.read().split()
        utime = int(parts[13])
        stime = int(parts[14])
        cutime = int(parts[15])
        cstime = int(parts[16])
        total2 = utime + stime + cutime + cstime

        with open("/proc/stat") as f:
            cpu_line = f.readline().split()
        host_total2 = sum(int(v) for v in cpu_line[1:])

        proc_delta = total2 - total1
        host_delta = host_total2 - host_total1

        if host_delta == 0:
            return 0.0
        return (proc_delta / host_delta) * 100.0
    except (OSError, IOError, IndexError, ValueError) as e:
        raise MonitorError(f"Failed to read CPU stats for PID {pid}: {e}")


# ── Memory Monitor ──────────────────────────────────────────────────────────


def get_memory_bytes(pid: int) -> int:
    """Return the resident memory usage of a process in bytes."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    # Format: "VmRSS:   12345 kB"
                    parts = line.split()
                    return int(parts[1]) * 1024  # kB → bytes
        raise MonitorError(f"Could not find VmRSS for PID {pid}")
    except (OSError, IOError, IndexError, ValueError) as e:
        raise MonitorError(f"Failed to read memory for PID {pid}: {e}")


def check_memory(pid: int, max_bytes: int = 200 * 1024 * 1024) -> None:
    """Raise ``MonitorMemoryExceeded`` if L1's RSS exceeds ``max_bytes``."""
    rss = get_memory_bytes(pid)
    if rss > max_bytes:
        raise MonitorMemoryExceeded(
            f"L1 memory {rss / 1024 / 1024:.1f} MiB exceeds "
            f"threshold {max_bytes / 1024 / 1024:.0f} MiB"
        )


# ── Journal / Chain Integrity Monitor ───────────────────────────────────────


def get_journal_mtime() -> Optional[float]:
    """Return the mtime of L1's events.jsonl, or None if absent."""
    try:
        return os.path.getmtime(RALPH_EVENTS_PATH)
    except OSError:
        return None


def check_journal_freshness(max_stale_seconds: float = 10.0) -> None:
    """Raise ``MonitorTimeout`` if L1 hasn't written to its journal recently."""
    mtime = get_journal_mtime()
    if mtime is None:
        raise MonitorTimeout("L1 journal not found — ralph may not be running")
    age = time.time() - mtime
    if age > max_stale_seconds:
        raise MonitorTimeout(
            f"L1 journal stale for {age:.1f}s "
            f"(threshold: {max_stale_seconds:.0f}s)"
        )


def verify_chain_integrity() -> int:
    """Verify the full hash chain of L1's events.jsonl.

    Returns the number of verified entries. Raises ``MonitorChainBroken``
    if any entry fails chain verification.
    """
    if not os.path.isfile(RALPH_EVENTS_PATH):
        raise MonitorChainBroken("L1 journal file does not exist")

    prev = GENESIS_HASH
    n = 0
    with open(RALPH_EVENTS_PATH, "rb") as f:
        for line_no, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as e:
                raise MonitorChainBroken(
                    f"L1 journal line {line_no}: invalid JSON — {e}"
                )
            if not isinstance(entry, dict):
                raise MonitorChainBroken(
                    f"L1 journal line {line_no}: not a JSON object"
                )
            payload = entry.get("payload", {})
            expected_hash = _chain_hash(prev, payload)
            actual_hash = entry.get("hash", "")
            if actual_hash != expected_hash:
                exp_short = expected_hash[:16]
                act_short = actual_hash[:16]
                raise MonitorChainBroken(
                    f"L1 journal line {line_no}: hash mismatch. "
                    f"Expected {exp_short}..., got {act_short}..."
                )
            if entry.get("prev", "") != prev:
                prev_short = prev[:16]
                got_short = entry.get("prev", "")[:16]
                raise MonitorChainBroken(
                    f"L1 journal line {line_no}: prev hash mismatch. "
                    f"Expected {prev_short}..., got {got_short}..."
                )
            prev = actual_hash
            n += 1

    return n


# ── Combined Health Check ───────────────────────────────────────────────────


class HealthReport:
    """Result of a full L1 health check."""

    def __init__(self):
        self.pid: Optional[int] = None
        self.running: bool = False
        self.cpu_percent: float = 0.0
        self.memory_bytes: int = 0
        self.memory_mib: float = 0.0
        self.journal_age_sec: float = -1.0
        self.chain_entries: int = 0
        self.healthy: bool = True
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "running": self.running,
            "cpu_percent": round(self.cpu_percent, 1),
            "memory_mib": round(self.memory_mib, 1),
            "journal_age_sec": round(self.journal_age_sec, 1),
            "chain_entries": self.chain_entries,
            "healthy": self.healthy,
            "errors": self.errors,
        }


def check_l1_health() -> HealthReport:
    """Run all health checks against L1 and return a ``HealthReport``."""
    report = HealthReport()
    errors: list[str] = []

    pid = resolve_ralph_pid()
    report.pid = pid

    if pid is None:
        report.running = False
        report.healthy = False
        errors.append("L1 not running")
        report.errors = errors
        return report

    report.running = True

    # CPU
    try:
        report.cpu_percent = get_cpu_percent(pid, interval=0.5)
    except MonitorError as e:
        errors.append(f"CPU: {e}")

    # Memory
    try:
        report.memory_bytes = get_memory_bytes(pid)
        report.memory_mib = report.memory_bytes / (1024 * 1024)
    except MonitorError as e:
        errors.append(f"Memory: {e}")

    # Journal freshness
    try:
        check_journal_freshness()
        mtime = get_journal_mtime()
        if mtime is not None:
            report.journal_age_sec = time.time() - mtime
    except MonitorTimeout as e:
        errors.append(f"Journal: {e}")

    # Chain integrity
    try:
        report.chain_entries = verify_chain_integrity()
    except MonitorChainBroken as e:
        errors.append(f"Chain: {e}")

    report.errors = errors
    report.healthy = len(errors) == 0
    return report
