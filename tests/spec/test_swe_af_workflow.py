#!/usr/bin/env python3
"""test_swe_af_workflow.py — the swe_af GHA runner must realize the LOWERED workflow.

Issue #153: `.github/workflows/swe-af.yml` is the GitHub-Actions realization of the
lowered `workflow swe_af` (vaked/examples/agentfield-swe.vaked →
vaked/examples/lowering-agentfield/gen/workflow/swe_af.json). The runner reads that
lowered JSON at run time (the `SPEC=` line) and drives its DAG. If the workflow drifts
from the lowered artifact — the SPEC path moves, the trigger stops matching the spec's
`on`, or a DAG step loses its node — the runner silently breaks while still passing the
Rust/lowering goldens (which never look at the YAML). These checks freeze that contract.

Stdlib-only, offline (regex over two checked-in files) — no build, no network.

Checks:
1. SPEC path — the `SPEC=` path baked into swe-af.yml resolves to an existing file, and
   it is the lowered swe_af.json (not some other artifact).
2. Trigger parity — the spec's `on = "github.issue.labeled:agent"` is realized by the
   workflow's `issues: types: [labeled]` trigger gated on the `agent` label.
3. DAG coverage — every step the lowered spec declares (plan/code/review/publish) has a
   corresponding node step in the workflow.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

WORKFLOW = os.path.join(REPO, ".github", "workflows", "swe-af.yml")
SPEC_REL = "vaked/examples/lowering-agentfield/gen/workflow/swe_af.json"
SPEC = os.path.join(REPO, SPEC_REL)


def _load():
    wf = open(WORKFLOW, encoding="utf-8").read()
    spec = json.load(open(SPEC, encoding="utf-8"))
    return wf, spec


def _spec_path_in_workflow(wf):
    """The `SPEC=<path>` the runner reads at run time."""
    m = re.search(r"^\s*SPEC=(\S+)", wf, re.MULTILINE)
    return m.group(1) if m else None


def _test_spec_path_resolves(lines):
    wf, _ = _load()
    path = _spec_path_in_workflow(wf)
    if path is None:
        lines.append("  FAIL spec-path: no `SPEC=` line found in swe-af.yml")
        return False
    if path != SPEC_REL:
        lines.append(f"  FAIL spec-path: workflow reads {path!r}, "
                     f"expected the lowered artifact {SPEC_REL!r}")
        return False
    if not os.path.exists(os.path.join(REPO, path)):
        lines.append(f"  FAIL spec-path: workflow SPEC {path!r} does not exist on disk")
        return False
    lines.append(f"  spec-path: runner reads the lowered {path}")
    return True


def _test_trigger_parity(lines):
    wf, spec = _load()
    on = spec.get("on", "")
    # The lowered trigger is "<event>:<label>" — here github.issue.labeled:agent.
    if ":" not in on:
        lines.append(f"  FAIL trigger: spec `on` has no label form: {on!r}")
        return False
    _, label = on.rsplit(":", 1)
    ok = True
    # GHA realizes github.issue.labeled via the `issues: types: [labeled]` event.
    if not re.search(r"issues:\s*\n\s*types:\s*\[[^\]]*\blabeled\b", wf):
        lines.append("  FAIL trigger: workflow lacks `issues: types: [labeled]` "
                     f"for spec on={on!r}")
        ok = False
    # ...gated on the spec's label name (the `agent` safety gate).
    if not re.search(rf"github\.event\.label\.name\s*==\s*'{re.escape(label)}'", wf):
        lines.append(f"  FAIL trigger: workflow does not gate on label {label!r} "
                     f"(spec on={on!r})")
        ok = False
    if ok:
        lines.append(f"  trigger parity: spec on={on!r} ⇒ "
                     f"issues.labeled gated on label {label!r}")
    return ok


def _test_dag_coverage(lines):
    wf, spec = _load()
    steps = [s["name"] for s in spec.get("steps", [])]
    if not steps:
        lines.append("  FAIL dag: spec declares no steps")
        return False
    # Each lowered step is realized by a workflow step whose name carries the step
    # name as a word — `plan`/`code`/`review` as `Node — <step>`, and `publish` as the
    # `Publish — …` step (the broker marks the PR ready). Match the step name as a word
    # in any `- name:` line so the test tracks the realization, not a naming convention.
    step_names = [m.lower() for m in re.findall(r"^\s*-\s*name:\s*(.+)$", wf, re.MULTILINE)]
    missing = [s for s in steps
               if not any(re.search(rf"\b{re.escape(s)}\b", n) for n in step_names)]
    if missing:
        lines.append(f"  FAIL dag: workflow has no step realizing spec steps {missing}")
        return False
    lines.append(f"  dag coverage: all {len(steps)} lowered steps "
                 f"({' → '.join(steps)}) have a realizing workflow step")
    return True


def run():
    lines = []
    ok = True
    for fn in (_test_spec_path_resolves, _test_trigger_parity, _test_dag_coverage):
        try:
            ok = fn(lines) and ok
        except Exception as e:
            import traceback
            ok = False
            lines.append(f"    ERROR in {fn.__name__}: {type(e).__name__}: {e}")
            lines.append(traceback.format_exc())
    return ok, lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_swe_af_workflow ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
