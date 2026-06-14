"""nocturne gate — PURE decision over a harvested results.jsonl. Never trains.

Reads the trial rows produced on the GPU box and decides whether the night's best
mutation is a genuine, confirmed, novel win worth escalating to swe_af — or whether
to abstain (the optitron move). Every condition must hold; else abstain.

A results.jsonl row (written by driver.py) looks like:
  {"kind":"baseline","val_bpb":0.9979,...}
  {"kind":"trial","trial":7,"val_bpb":0.9931,"signature":"wsd-schedule","status":"keep",
   "peak_vram_mb":46000,"diff":"<unified diff of train.py>","description":"cosine->WSD"}
  {"kind":"confirm","signature":"wsd-schedule","seed":1234,"val_bpb":0.9933}
Stdlib only.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# thresholds (env-overridable in the orchestrator; defaults are conservative)
MIN_BPB_DELTA = 0.002      # winner must beat the committed baseline by at least this
CONFIRM_SEEDS_MIN = 2      # independent re-run seeds that must also clear the baseline


@dataclass
class Verdict:
    escalate: bool
    reason: str
    best: dict[str, Any] | None = None
    baseline_bpb: float | None = None
    confirm: list[float] = field(default_factory=list)


def _rows(results_path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with open(results_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def evaluate(
    results_path: str,
    committed_baseline_bpb: float | None,
    known_signatures: set[str] | None = None,
    min_delta: float = MIN_BPB_DELTA,
    confirm_min: int = CONFIRM_SEEDS_MIN,
) -> Verdict:
    rows = _rows(results_path)
    known = known_signatures or set()

    # 1. Measured, not claimed: only rows with a real numeric val_bpb count.
    trials = [
        r for r in rows
        if r.get("kind") == "trial"
        and isinstance(r.get("val_bpb"), (int, float))
        and math.isfinite(r["val_bpb"])
        and r["val_bpb"] > 0
        and r.get("status") != "crash"
    ]
    if not trials:
        return Verdict(False, "no measured trial (all crashed/empty)")

    # Baseline: committed value if we have one, else this night's own baseline row.
    baseline = committed_baseline_bpb
    if baseline is None:
        brow = next((r for r in rows if r.get("kind") == "baseline"
                     and isinstance(r.get("val_bpb"), (int, float))), None)
        baseline = brow["val_bpb"] if brow else None
    if baseline is None:
        return Verdict(False, "no baseline to compare against")

    best = min(trials, key=lambda r: r["val_bpb"])

    # 2. Beats the committed baseline by >= min_delta.
    delta = baseline - best["val_bpb"]
    if delta < min_delta:
        return Verdict(False, f"best {best['val_bpb']:.6f} vs baseline {baseline:.6f} "
                              f"(delta {delta:+.6f} < {min_delta})", best, baseline)

    # 4. Novel — signature not already promoted in a prior night.
    sig = best.get("signature")
    if sig and sig in known:
        return Verdict(False, f"winner signature '{sig}' already in ledger (not novel)", best, baseline)

    # 5. Sane — finite vram, no divergence flag.
    if best.get("diverged") or (best.get("peak_vram_mb") and not math.isfinite(best["peak_vram_mb"])):
        return Verdict(False, "winner failed sanity (divergence/vram)", best, baseline)

    # 3. Confirmed on independent re-run seeds (measured on the box in the confirm phase).
    confirms = [
        r["val_bpb"] for r in rows
        if r.get("kind") == "confirm" and r.get("signature") == sig
        and isinstance(r.get("val_bpb"), (int, float)) and math.isfinite(r["val_bpb"])
    ]
    held = [v for v in confirms if (baseline - v) >= min_delta]
    if len(held) < confirm_min:
        return Verdict(False, f"only {len(held)}/{confirm_min} confirm seeds cleared baseline",
                       best, baseline, confirms)

    return Verdict(True, f"confirmed win: {best['val_bpb']:.6f} vs {baseline:.6f} "
                         f"(delta {delta:+.6f}, {len(held)} seeds)", best, baseline, confirms)


if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) < 2:
        print("usage: gate.py <results.jsonl> [baseline_bpb]", file=sys.stderr)
        sys.exit(2)
    base = float(sys.argv[2]) if len(sys.argv) > 2 else (
        float(os.environ["NOCTURNE_BASELINE_BPB"]) if os.environ.get("NOCTURNE_BASELINE_BPB") else None)
    v = evaluate(sys.argv[1], base)
    print(("ESCALATE" if v.escalate else "ABSTAIN") + ": " + v.reason)
    sys.exit(0)
