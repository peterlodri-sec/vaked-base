"""Pure decision policy for the oracle ralph loop.

Round-robin: decompile each function once, then refine any below the fidelity
threshold (bounded by MAX_REFINE passes), then finalize. Budget-exhaustion or
control-stop forces finalize (handled by the loop; the policy only sees budget).
"""
from __future__ import annotations

from dataclasses import dataclass

FIDELITY_THRESHOLD = 0.75
MAX_REFINE = 2


@dataclass
class LoopState:
    functions: list[str]
    results: dict[str, dict]   # fn -> {"fidelity": float, "refined": bool, "refine_passes": int}
    iters: int
    budget_iters: int


def next_action(state: LoopState) -> dict:
    if state.iters >= state.budget_iters:
        return {"action": "finalize"}
    # 1. any function not yet decompiled?
    for fn in state.functions:
        if fn not in state.results:
            return {"action": "decompile", "fn": fn}
    # 2. any below threshold with refine budget left?
    for fn in state.functions:
        r = state.results[fn]
        if (r.get("fidelity") or 0.0) < FIDELITY_THRESHOLD and r.get("refine_passes", 0) < MAX_REFINE:
            return {"action": "refine", "fn": fn}
    # 3. done
    return {"action": "finalize"}
