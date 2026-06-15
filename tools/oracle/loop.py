"""Oracle ralph loop: control/budget gate -> policy -> run producer -> append ledger.

Producers are injected callables so the loop is testable with fakes:
  decompile(fn) -> (pseudo_c, refined_c, fidelity)
  refine(fn, prev_refined) -> (refined_c, fidelity)
  dynamic(fn) -> (frida_dict|None, ebpf_dict|None)
Control: if control_path is given, a JSON file with {"stop": true} halts the loop
(read each tick), mirroring ralph's live control.
"""
from __future__ import annotations

import json
import os

import policy
import schema


def _control_stop(control_path: str | None) -> bool:
    if not control_path or not os.path.exists(control_path):
        return False
    try:
        return bool(json.load(open(control_path)).get("stop"))
    except (OSError, json.JSONDecodeError):
        return False


def run_loop(*, functions, target, decompiler_meta, ledger_,
             decompile, refine, dynamic, budget_iters=50, control_path=None,
             decide=None, investigate=None) -> dict:
    decide = decide or policy.next_action      # slice-3: injectable LLM brain (default deterministic)
    results: dict[str, dict] = {}
    observations: list[dict] = []
    iters = 0
    while True:
        if _control_stop(control_path):
            ledger_.append({"kind": "decision", "action": "control_stop"})
            break
        state = policy.LoopState(functions=functions, results=results,
                                 iters=iters, budget_iters=budget_iters,
                                 observations=observations)
        act = decide(state)
        ledger_.append({"kind": "decision", **act, "iter": iters})
        if act["action"] == "finalize":
            break
        if act["action"] == "investigate":
            obs = (investigate(act["query"]) if investigate
                   else {"query": act["query"], "provider": "none", "result": None})
            observations.append(obs)
            ledger_.append({"kind": "observation", "iter": iters, **obs})
            iters += 1
            continue
        fn = act["fn"]
        if act["action"] == "decompile":
            pseudo_c, refined_c, fid = decompile(fn)
            fr, eb = dynamic(fn)
            results[fn] = {"pseudo_c": pseudo_c, "refined": refined_c, "fidelity": fid,
                           "refine_passes": 0, "frida": fr, "ebpf": eb}
        elif act["action"] == "refine":
            refined_c, fid = refine(fn, results[fn]["refined"])
            results[fn]["refined"] = refined_c
            results[fn]["fidelity"] = fid
            results[fn]["refine_passes"] += 1
        iters += 1

    # assemble finding
    import hashlib
    fn_entries = []
    for fn in functions:
        r = results.get(fn)
        if not r:
            continue
        pseudo_sha = hashlib.sha256(r["pseudo_c"].encode()).hexdigest()
        fn_entries.append(schema.function_entry(
            name=fn, addr="0x0", pseudo_c_sha=pseudo_sha, refined_c=r["refined"],
            fidelity_score=r["fidelity"], frida=r["frida"], ebpf=r["ebpf"]))
    scores = [e["fidelity"]["score"] for e in fn_entries if e["fidelity"]["score"] is not None]
    confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
    finding = schema.build_finding(target=target, decompiler=decompiler_meta,
                                   functions=fn_entries, confidence=confidence)
    schema.validate_finding(finding)
    ledger_.append({"kind": "finding", "confidence": confidence,
                    "n_functions": len(fn_entries)})
    return finding
