"""Userspace dynamic evidence via Frida (no root; ptrace on revdev's own process).

parse_frida_trace() is pure (tested). run_frida() is the impure runner: it launches
the target via sample-run (bubblewrap, no-net) under frida with hook.js, which emits
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
              sample_run: str = "sample-run", timeout: float = 300.0) -> dict[str, dict]:
    """Impure. Run target under frida+hook.js inside sample-run; return aggregated trace."""
    hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook.js")
    env = dict(os.environ, ORACLE_HOOK_FUNCS=",".join(functions))
    cmd = [sample_run, "frida", "-q", "-l", hook, "-f", *target_cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return parse_frida_trace(proc.stdout)
