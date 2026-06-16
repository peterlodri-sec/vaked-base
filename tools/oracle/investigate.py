"""Read-only structural investigation for the agentic reverser (slice 3 + 4a).

The hybrid 'investigate' action: answer a function query (signature / callers /
refs / outline / fuzzy) from crabcc over the C ground-truth source (crabcc indexes
C, not C++ — so ggml.c + C headers), then **universal-ctags** for the C++ source
bodies crabcc skips (slice 4a — the gap-filler; Serena/clangd is the richer agent-facing
MCP complement for the same job), then binutils over the target binary, else a 'none'
observation. Never raises — investigation must never crash the loop.
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


def ctags_query(query, *, source_root, ctags="ctags", runner=_run):
    """C/C++ source symbols via universal-ctags JSON — covers the C++ bodies crabcc skips.
    One-shot; graceful (None if ctags absent or no hit). Best-effort: scans the tree and
    filters by name (a prebuilt tags file would be faster; fine for slice 4a)."""
    kind, name = query.get("kind"), query.get("name")
    if kind not in ("sym", "fuzzy", "outline") or not name:
        return None
    rc, out = runner([ctags, "-R", "--languages=C,C++", "--output-format=json",
                      "--fields=+nS", "-f", "-", source_root])
    if rc != 0 or not out.strip():
        return None
    hits = []
    for line in out.splitlines():
        try:
            tag = json.loads(line)
        except json.JSONDecodeError:
            continue
        if tag.get("_type") == "tag" and name in (tag.get("name") or ""):
            hits.append({"name": tag.get("name"), "kind": tag.get("kind"),
                         "signature": tag.get("signature"), "path": tag.get("path"),
                         "line": tag.get("line")})
            if len(hits) >= 20:
                break
    if not hits:
        return None
    return {"query": query, "provider": "ctags", "result": hits}


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


def make_investigator(*, source_root=None, binary=None, crabcc="crabcc", ctags="ctags", runner=_run):
    """investigate(query) -> observation. Chain: crabcc (C) -> ctags (C++) -> binutils
    (binary) -> none. Each provider's failure falls through to the next. Never raises."""
    def investigate(query):
        # per-provider guards: a provider failure (incl. binary not installed —
        # FileNotFoundError) must FALL THROUGH to the next, not short-circuit to none.
        if source_root:
            try:
                obs = crabcc_query(query, source_root=source_root, crabcc=crabcc, runner=runner)
                if obs is not None:
                    return obs
            except Exception:  # noqa: BLE001 — crabcc missing/erroring => try ctags
                pass
            try:
                obs = ctags_query(query, source_root=source_root, ctags=ctags, runner=runner)
                if obs is not None:
                    return obs
            except Exception:  # noqa: BLE001 — ctags missing/erroring => try binutils
                pass
        if binary:
            try:
                obs = binutils_query(query, binary=binary, runner=runner)
                if obs is not None:
                    return obs
            except Exception:  # noqa: BLE001 — investigation must never crash the loop
                pass
        return {"query": query, "provider": "none", "result": None}
    return investigate
