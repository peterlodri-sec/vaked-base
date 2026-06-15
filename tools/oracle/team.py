"""team.py — slice-4a reverser-team coordinator (brett-shaw).

Deterministic control over the debate panel: per function — decompile (slice-1 pseudo-C)
-> recall prior team knowledge (the-dossier) + investigate -> debate_function (panel +
judge) -> record every candidate + verdict to the ledger (katedralis) -> remember
(deterministic facts) -> assemble the finding (slice-2 ground unchanged). Budget = total
model calls; control-file stop. Pure stdlib; producers/investigate/memory injected.
"""
from __future__ import annotations

import hashlib
import json
import os

import panel as P
import schema


def _control_stop(control_path):
    if not control_path or not os.path.exists(control_path):
        return False
    try:
        return bool(json.load(open(control_path)).get("stop"))
    except (OSError, json.JSONDecodeError):
        return False


def _context(fn, memory, investigate):
    parts = []
    if memory:
        inj = memory.inject(fn, fn)
        if inj:
            parts.append(inj)
    if investigate:
        obs = investigate({"kind": "sym", "name": fn})
        if obs and obs.get("result"):
            parts.append(f"investigate({obs.get('provider')}): {json.dumps(obs['result'])[:400]}")
    return "\n".join(parts)


def run_team(*, functions, target, decompiler_meta, ledger_, decompile, panelists, judge_client,
             score=None, ground_truth=None, investigate=None, memory=None, run_id="run",
             budget_calls=60, control_path=None, max_workers=4) -> dict:
    fn_entries = []
    calls = 0
    for fn in functions:
        if _control_stop(control_path):
            ledger_.append({"kind": "decision", "action": "control_stop"})
            break
        if calls + (len(panelists) + 1) > budget_calls:    # conservative worst-case pre-check
            ledger_.append({"kind": "decision", "action": "finalize", "reason": "budget_exhausted", "fn": fn})
            break
        pseudo_c = decompile(fn) or ""
        gt = ground_truth(fn) if ground_truth else None
        ctx = _context(fn, memory, investigate)
        result = P.debate_function(fn, pseudo_c, ctx, panelists, judge_client,
                                   score=score, ground_truth=gt, max_workers=max_workers)
        calls += len(panelists) + (0 if result["effort"] == "none" else 1)
        for c in result["candidates"]:
            rc = c.get("refined_c")
            ledger_.append({"kind": "candidate", "fn": fn, "panelist": c["panelist"],
                            "model": c.get("model"), "error": c.get("error"),
                            "refined_sha": hashlib.sha256(rc.encode()).hexdigest() if rc else None})
        v = result["verdict"]
        ledger_.append({"kind": "verdict", "fn": fn, "mode": v["mode"], "effort": result["effort"],
                        "drew_from": v.get("drew_from", []), "rationale": v.get("rationale", "")})
        if memory:
            memory.remember(run_id=run_id, fn=fn, kind="finding",
                            text=f"{fn}: chosen via {v['mode']} (drew_from {v.get('drew_from')}), "
                                 f"fidelity={result['fidelity']}", tags=[fn])
        fn_entries.append(schema.function_entry(
            name=fn, addr="0x0", pseudo_c_sha=hashlib.sha256(pseudo_c.encode()).hexdigest(),
            refined_c=result["chosen"], fidelity_score=result["fidelity"]))

    scores = [e["fidelity"]["score"] for e in fn_entries if e["fidelity"]["score"] is not None]
    confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
    finding = schema.build_finding(target=target, decompiler=decompiler_meta,
                                   functions=fn_entries, confidence=confidence)
    schema.validate_finding(finding)
    ledger_.append({"kind": "finding", "confidence": confidence, "n_functions": len(fn_entries)})
    return finding
