"""Read-only structural investigation for the agentic reverser (slice 3).

The hybrid 'investigate' action: answer a function query (signature / callers /
refs / outline / fuzzy) from crabcc over the C ground-truth source (crabcc indexes
C, not C++ — so ggml.c + C headers like llama.h/ggml.h), falling back to binutils
over the target binary, else a 'none' observation. Never raises — investigation
must never crash the loop.
"""
from __future__ import annotations

import json
import subprocess

_CRABCC_KINDS = ("sym", "callers", "refs", "outline", "fuzzy")


def _run(cmd, *, timeout=30):
    """Run a command -> (rc, stdout). Injectable via make_investigator(runner=...)."""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # noqa: S603
    return p.returncode, p.stdout


def crabcc_query(query, *, source_root, crabcc="crabcc", runner=_run):
    kind, name = query.get("kind"), query.get("name")
    if kind not in _CRABCC_KINDS or not name:
        return None
    rc, out = runner([crabcc, "--root", source_root, "lookup", kind, name])
    if rc != 0 or not out.strip():
        return None
    try:
        result = json.loads(out)
    except json.JSONDecodeError:
        result = out.strip()[:1000]
    return {"query": query, "provider": "crabcc", "result": result}


def binutils_query(query, *, binary, runner=_run):
    kind, name = query.get("kind"), query.get("name")
    if not binary or not name:
        return None
    if kind in ("sym", "fuzzy"):
        rc, out = runner(["nm", "-C", "--defined-only", binary])
        if rc != 0:
            return None
        hits = [ln for ln in out.splitlines() if name in ln][:20]
        return {"query": query, "provider": "binutils",
                "result": {"symbols": hits, "found": bool(hits)}}
    return {"query": query, "provider": "binutils",
            "result": {"note": f"{kind} not available from a binary"}}


def make_investigator(*, source_root=None, binary=None, crabcc="crabcc", runner=_run):
    """investigate(query) -> observation. crabcc-preferred, binutils fallback, 'none'
    if neither usable. Never raises."""
    def investigate(query):
        try:
            if source_root:
                obs = crabcc_query(query, source_root=source_root, crabcc=crabcc, runner=runner)
                if obs is not None:
                    return obs
            if binary:
                obs = binutils_query(query, binary=binary, runner=runner)
                if obs is not None:
                    return obs
        except Exception:  # noqa: BLE001 — investigation must never crash the loop
            pass
        return {"query": query, "provider": "none", "result": None}
    return investigate
