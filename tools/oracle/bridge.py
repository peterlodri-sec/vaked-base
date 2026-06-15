"""Bridge an oracle finding to the aegis kernel's evidence seam.

The kernel (tools/dogfood/) consumes observed_effects = {writes, deletes}. Oracle
runs produce files (findings, reports) in its workspace; to_observed_effects exposes
those as the kernel-compatible shape. attach_transition links a finding to a kernel
transition by its content hash (double-dogfood; null in slice 1).
"""
from __future__ import annotations

import copy


def to_observed_effects(finding: dict, *, files_written: list[str] | None = None,
                        files_deleted: list[str] | None = None) -> dict:
    return {"writes": sorted(files_written or []), "deletes": sorted(files_deleted or [])}


def attach_transition(finding: dict, transition_hash: str) -> dict:
    out = copy.deepcopy(finding)
    out["transition_xref"] = transition_hash
    return out
