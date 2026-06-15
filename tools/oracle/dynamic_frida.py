"""Userspace dynamic evidence via Frida (no root; ptrace on revdev's own process).

parse_frida_trace() is pure (tested). run_frida() is the impure runner: it launches
the target via a frida-python driver (frida_driver.py) which spawns the target with
stdio="pipe", hooks named exported functions via findGlobalExportByName, and emits
one JSON line per hooked-function call. Aggregates to {fn: {calls, timing_ms}}.
"""
from __future__ import annotations

import json
import os
import subprocess


def parse_frida_trace(text: str) -> dict[str, dict]:
    """Aggregate per-function call events. Non-JSON / non-event lines are ignored."""
    agg: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        fn = ev.get("fn")
        if fn is None:
            continue
        slot = agg.setdefault(fn, {"calls": 0, "_ns": 0})
        slot["calls"] += 1
        slot["_ns"] += int(ev.get("dur_ns", 0))
    for fn, slot in agg.items():
        slot["timing_ms"] = round(slot.pop("_ns") / 1e6, 6)
    return agg


def run_frida(*, target_cmd: list[str], functions: list[str],
              frida_python: str | None = None, max_wait: float = 90.0,
              timeout: float = 300.0) -> dict[str, dict]:
    """Impure. Spawn target under a frida-python driver hooking `functions`; return
    {fn: {calls, timing_ms}}. `frida_python` is an interpreter with frida-python
    installed (defaults to $ORACLE_FRIDA_PYTHON or python3). Trusted targets run
    directly (no sandbox); untrusted samples should be wrapped by the caller."""
    driver = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frida_driver.py")
    py = frida_python or os.environ.get("ORACLE_FRIDA_PYTHON", "python3")
    env = dict(os.environ, FRIDA_MAX_WAIT=str(max_wait))
    proc = subprocess.run([py, driver, ",".join(functions), *target_cmd],
                          capture_output=True, text=True, timeout=timeout, env=env)
    return parse_frida_trace(proc.stdout)
