"""dogfood.capability — the POLA gate: used(paths) must be within granted(scope).

This is the local, M1-runnable approximation of Vaked's capability model. The
runtime enforces capabilities in the kernel (eBPF/seccomp, L2 — owned elsewhere);
here we enforce the *principle* at the file-path level: a proposed transition may
only write/delete paths that lie under a granted scope prefix. Anything outside
is a confused-deputy / scope-escape and is rejected before the WAL ever sees it.

This directly exercises the ``used(p) ⊑ granted(p)`` use-check that is otherwise
unimplemented on trunk (the open ``E-CAP-USE`` / negative-POLA gap), at the one
layer that runs without a Linux kernel.
"""
from __future__ import annotations

import os


def _normalize(rel: str) -> str:
    # Reject absolute paths and any traversal that escapes the repo root.
    return os.path.normpath(rel)


def in_scope(rel: str, scope: list[str]) -> bool:
    """True iff repo-relative ``rel`` lies under one of the granted prefixes.

    Absolute paths and ``..`` escapes are never in scope. Prefix matching is
    path-segment aware (``tools/dogfood`` does not grant ``tools/dogfood-evil``).
    """
    if os.path.isabs(rel):
        return False
    norm = _normalize(rel)
    if norm == ".." or norm.startswith(".." + os.sep):
        return False
    for prefix in scope:
        p = _normalize(prefix)
        if norm == p or norm.startswith(p + os.sep):
            return True
    return False


def check(paths: list[str], scope: list[str]) -> dict:
    """Partition ``paths`` into in-scope and violations.

    Returns ``{"ok": bool, "violations": [paths]}``. ``ok`` is True only when
    every path is granted — a single escape fails the whole transition (a
    capability check is all-or-nothing, like the kernel boundary it models).
    """
    violations = sorted(p for p in paths if not in_scope(p, scope))
    return {"ok": not violations, "violations": violations}
