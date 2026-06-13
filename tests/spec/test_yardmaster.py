#!/usr/bin/env python3
"""test_yardmaster.py — the merge-train conductor's pure logic + ledger.

No network: exercises the DAG/topo-sort, the total mergeability→action decision
table, the stacked-PR planning, and the eventd ledger round-trip (the same
hash-chain the live agent writes). The GitHub REST client is not exercised here
(it is a thin urllib wrapper; the live `plan` dry-run validates it end to end).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools", "yardmaster"))

import yardmaster as ym                       # noqa: E402
from eventd import EventLog, TamperError       # noqa: E402

ALL_STATES = ["clean", "behind", "dirty", "unstable", "blocked", "draft", "unknown", ""]
ACTIONS = {ym.MERGE, ym.UPDATE_BRANCH, ym.WAIT, ym.BLOCK_CONFLICT, ym.SKIP}


def _pr(num, head, base, state="clean", ci="success", draft=False,
        labels=(ym.OPT_IN_LABEL,), author=""):
    return ym.PR(number=num, head_ref=head, base_ref=base, mergeable_state=state,
                 ci=ci, draft=draft, labels=tuple(labels), author=author)


# --------------------------------------------------------------------------- #

def _test_topo(lines):
    ok = True
    # #112 (head B, base A) is stacked on #103 (head A, base main).
    prs = [_pr(112, "B", "A"), _pr(103, "A", "main")]
    order = ym.topo_order(prs)
    if order != [103, 112]:
        ok = False
        lines.append(f"  FAIL topo: expected [103,112], got {order}")
    # base on main only → no edges; deterministic ascending tie-break.
    flat = [_pr(5, "e", "main"), _pr(2, "b", "main"), _pr(9, "i", "main")]
    if ym.topo_order(flat) != [2, 5, 9]:
        ok = False
        lines.append(f"  FAIL topo: flat order not ascending: {ym.topo_order(flat)}")
    # a cycle must be detected.
    cyc = [_pr(1, "x", "y"), _pr(2, "y", "x")]
    try:
        ym.topo_order(cyc)
        ok = False
        lines.append("  FAIL topo: cycle not detected")
    except ValueError:
        pass
    if ok:
        lines.append("  PASS topo: stacked order [103,112], deterministic, cycle detected")
    return ok


def _test_decision_total(lines):
    ok = True
    # every mergeable_state maps to exactly one known action (opt-in, base merged).
    for st in ALL_STATES:
        action, _ = ym.decide(_pr(1, "h", "main", state=st, ci="pending"), base_open=False)
        if action not in ACTIONS:
            ok = False
            lines.append(f"  FAIL decide: state {st!r} → unknown action {action!r}")
    # spot-check the load-bearing rows.
    cases = [
        (dict(state="clean", ci="success"), False, ym.MERGE),
        (dict(state="clean", ci="failure"), False, ym.SKIP),
        (dict(state="clean", ci="pending"), False, ym.WAIT),
        (dict(state="behind"), False, ym.UPDATE_BRANCH),
        (dict(state="dirty"), False, ym.BLOCK_CONFLICT),
        (dict(state="unstable", ci="pending"), False, ym.WAIT),
        (dict(state="unstable", ci="failure"), False, ym.SKIP),
        (dict(state="unknown"), False, ym.WAIT),
        (dict(state="clean", ci="success", draft=True), False, ym.SKIP),
        (dict(state="clean", ci="success", labels=()), False, ym.SKIP),   # not opt-in
        (dict(state="clean", ci="success"), True, ym.SKIP),               # base unmerged
    ]
    for kw, base_open, want in cases:
        action, reason = ym.decide(_pr(1, "h", "main", **kw), base_open=base_open)
        if action != want:
            ok = False
            lines.append(f"  FAIL decide: {kw} base_open={base_open} → {action} (want {want})")
    # fleet author is opt-in without the label.
    a, _ = ym.decide(_pr(1, "h", "main", labels=(), author="ralph-loop"), base_open=False)
    if a != ym.MERGE:
        ok = False
        lines.append(f"  FAIL decide: fleet author not opt-in ({a})")
    # orphaned stacked PR: base is a non-default branch with no open parent PR
    # (parent merged/closed) → never merge into the stale base; retarget first.
    a, r = ym.decide(_pr(1, "h", "stale-parent-branch", state="clean", ci="success"),
                     base_open=False, default_branch="main")
    if a != ym.SKIP or "retarget" not in r:
        ok = False
        lines.append(f"  FAIL decide: orphaned stacked PR not held for retarget ({a}: {r})")
    if ok:
        lines.append("  PASS decide: total over all mergeable_states; deny-by-default opt-in; "
                     "dirty→needs-human, behind→update, clean+green→merge")
    return ok


def _test_plan_stacked(lines):
    ok = True
    # #103 clean+green; #112 stacked + clean+green. Plan must hold #112 until #103 merges.
    prs = [_pr(112, "B", "A", state="clean", ci="success"),
           _pr(103, "A", "main", state="clean", ci="success")]
    plan = ym.plan_train(prs)
    pa = {n: (a, r) for n, a, r in plan}
    if [n for n, _, _ in plan] != [103, 112]:
        ok = False
        lines.append(f"  FAIL plan: order {[n for n,_,_ in plan]} != [103,112]")
    if pa[103][0] != ym.MERGE:
        ok = False
        lines.append(f"  FAIL plan: #103 should merge, got {pa[103]}")
    if pa[112][0] != ym.SKIP or "base" not in pa[112][1]:
        ok = False
        lines.append(f"  FAIL plan: #112 should wait on base, got {pa[112]}")
    if ok:
        lines.append("  PASS plan: stacked #112 held until base #103 merges (no premature merge)")
    return ok


def _test_ledger(lines):
    ok = True
    with tempfile.TemporaryDirectory() as td:
        log_path = os.path.join(td, "log.jsonl")
        kinds = [
            {"kind": "observed", "open_prs": 2, "train": [[103, "merge"], [112, "skip"]]},
            {"kind": "rebased", "pr": 112, "action": "update_branch"},
            {"kind": "merged", "pr": 103, "action": "merge"},
            {"kind": "blocked_conflict", "pr": 112, "action": "block_conflict"},
        ]
        with EventLog(log_path, writer=True) as log:
            for k in kinds:
                log.append(k)
        # reopen → boot-verify the chain
        if len(EventLog(log_path)) != len(kinds):
            ok = False
            lines.append("  FAIL ledger: entry count mismatch on reopen")
        # tamper: flip a byte → boot-verify must refuse
        data = bytearray(open(log_path, "rb").read())
        i = data.find(b'"merged"')
        data[i + 2] ^= 0x20
        open(log_path, "wb").write(data)
        try:
            EventLog(log_path)
            ok = False
            lines.append("  FAIL ledger: tamper not detected")
        except TamperError:
            pass
    if ok:
        lines.append("  PASS ledger: eventd round-trip of train events, chain intact, tamper refused")
    return ok


# --------------------------------------------------------------------------- #

def _test_clear_step(lines):
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cp = os.path.join(td, "control.json")
        saved = ym.CONTROL_PATH
        ym.CONTROL_PATH = cp
        try:
            json.dump({"paused": True, "step": True}, open(cp, "w"))
            ym._clear_step()
            after = json.load(open(cp))
            if after.get("step") is not False or after.get("paused") is not True:
                ok = False
                lines.append(f"  FAIL step: control after clear = {after} "
                             "(want step false, paused true)")
        finally:
            ym.CONTROL_PATH = saved
    if ok:
        lines.append("  PASS step: one-shot step flag consumed (paused preserved) — "
                     "no runaway acting while paused")
    return ok


def run():
    lines = []
    ok = True
    for label, fn in [
        ("topo-sort (stacked PRs)", _test_topo),
        ("decision table (total)", _test_decision_total),
        ("plan (stacked hold)", _test_plan_stacked),
        ("ledger (eventd round-trip)", _test_ledger),
        ("control (one-shot step)", _test_clear_step),
    ]:
        lines.append(label + ":")
        ok &= fn(lines)
    return bool(ok), lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_yardmaster ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
