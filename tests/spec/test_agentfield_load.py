#!/usr/bin/env python3
"""test_agentfield_load.py — the agentfield-swe target system at scale.

The language-spec **e2e load test** (#27): a deterministic generator emits the
full daily-use target-system shape — index / streams / memory / budget / mesh /
workflow / fiber / surface / parallel, the whole design in one runtime — in
**massive fan-out mode**: the operator delegates attenuated grants (including
distributed `mem.recall`) to N agent nodes, and the swe_af workflow fans out
`plan -> work_i -> review -> publish` across all of them.

Three groups:

1. **load-clean.** N_LOAD agents (hundreds — CI-load-respecting; the shape, not
   the ceiling, is what's under test) check clean, and the parsed graph carries
   exactly the expected structural counts (mesh nodes = N+1, steps = N+3).
   A deliberately generous wall-clock cap guards against accidental
   super-linear blowups in the checker — it is NOT a performance target.
2. **golden-faults.** A small (N=8) variant injects exactly three deterministic
   faults — a rogue delegation (E-CAP-ATTENUATION), an agent typo
   (E-REF-UNRESOLVED), a depth overflow (E-WORKFLOW-DEPTH) — and the canonical
   ``--json`` output is byte-identical to
   ``golden/agentfield-load.diagnostics.json``. This is the "deterministic
   exceptions" fixture: same generated source ⇒ same bytes, byte offsets and
   all.
3. **determinism.** Two checks of the N_LOAD system produce identical
   diagnostics JSON (cached + fresh catalog).

The generator is pure (no randomness, no environment); everything is derived
from N. vakedc is imported as a top-level package (repo root on sys.path).
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

import vakedc  # noqa: E402

BUILTINS = os.path.join(REPO, "vaked", "schema", "builtins.vaked")
GOLDEN = os.path.join(HERE, "golden", "agentfield-load.diagnostics.json")

N_LOAD = 512          # fan-out width (raised from 256 after the #29 fix
                      # made checking linear: ~0.2s at this width)
N_GOLDEN = 8          # small + readable for the byte-exact fault fixture
TIME_CAP_S = 60.0     # generous blowup guard, not a perf target

# Virtual filenames (appear in diagnostics; must stay stable for the golden).
LOAD_NAME = "tests/spec/gen/agentfield-load.vaked"
GOLDEN_NAME = "tests/spec/gen/agentfield-load-faults.vaked"


def _builtins_cache():
    return vakedc.load_builtins(BUILTINS)


def _diagnostics_json(diags):
    """Mirror vakedc.__main__._diagnostics_json (the canonical --json form)."""
    doc = {"diagnostics": [d.as_dict() for d in diags]}
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def gen_field(n, *, rogue=False, agent_typo=False, deep_tail=False):
    """Deterministically generate the full target system with N agents.

    Fault injection (all off ⇒ the system checks clean):
      * ``rogue``      — a mesh node holding `fs.host_rw` that the operator
                         (max grant `fs.repo_rw`) cannot delegate to
                         ⇒ E-CAP-ATTENUATION.
      * ``agent_typo`` — step work0003 names `field.wrkr0003` (no such node in
                         the sibling mesh) ⇒ E-REF-UNRESOLVED.
      * ``deep_tail``  — two chained steps after publish push the critical
                         path to 6 > maxDepth = 4 ⇒ E-WORKFLOW-DEPTH.
    """
    L = []
    a = L.append
    a('runtime "agent-field-load" {')
    a('  systems = ["x86_64-linux"]')
    a('')
    a('  index corpus {')
    a('    source = [github("peterlodri-sec/vaked-base")]')
    a('    normalize = crabcc.markdown')
    a('    emit = [catalog.jsonl]')
    a('  }')
    a('')
    a('  stream transcripts {')
    a('    source = agentpipe.transcripts')
    a('    type = Agent.Transcript')
    a('    retention = 30d')
    a('  }')
    a('')
    a('  memory palace {')
    a('    source = stream.transcripts')
    a('    mine = mempalace.convos')
    a('    scope = "runtime"')
    a('    retention = 90d')
    a('  }')
    a('')
    a('  budget swe {')
    a('    tokens = 2000000')
    a('    wallClock = 2h')
    a('    toolCalls = 400')
    a('    approvals = "destructive"')
    a('  }')
    a('')
    a('  engine miner {')
    a('    package = nix.derivation')
    a('  }')
    a('')
    a('  mesh field {')
    a('    node operator {')
    a('      role = "control-plane"')
    a('      capabilities = [fs.repo_rw, process.spawn, mem.admin]')
    a('    }')
    for i in range(n):
        a(f'    node worker{i:04d} {{')
        a('      role = "implement"')
        a('      capabilities = [fs.repo_ro, mem.recall]')
        a('    }')
    if rogue:
        a('    node rogue {')
        a('      role = "escalator"')
        a('      capabilities = [fs.host_rw]')
        a('    }')
    for i in range(n):
        a(f'    operator -> worker{i:04d}')
    if rogue:
        a('    operator -> rogue')
    a('  }')
    a('')
    a('  workflow swe_af {')
    a('    on = "github.issue.labeled:agent"')
    a('    budget = budget.swe')
    a('    maxDepth = 4')
    a('    node plan {')
    a('      agent = field.operator')
    a('      output = artifacts.plan')
    a('    }')
    for i in range(n):
        agent = f'field.worker{i:04d}'
        if agent_typo and i == 3:
            agent = 'field.wrkr0003'
        a(f'    node work{i:04d} {{')
        a(f'      agent = {agent}')
        a('      input = artifacts.plan')
        a(f'      output = artifacts.patch{i:04d}')
        a('      retries = 1')
        a('    }')
    a('    node review {')
    a('      agent = field.operator')
    a('    }')
    a('    node publish {')
    a('      agent = field.operator')
    a('    }')
    if deep_tail:
        a('    node tail1 { agent = field.operator }')
        a('    node tail2 { agent = field.operator }')
    for i in range(n):
        a(f'    plan -> work{i:04d} -> review')
    a('    review -> publish')
    if deep_tail:
        a('    publish -> tail1 -> tail2')
    a('  }')
    a('')
    a('  fiber loadMiner {')
    a('    engine = miner')
    a('    input = stream.transcripts')
    a('    output = artifacts.mined')
    a('  }')
    a('')
    a('  surface fieldView {')
    a('    mode = raylib')
    a('    fps = 30')
    a('    input = [stream.transcripts, graph.swe_af, graph.field]')
    a('    views = ["workflow-dag", "mesh-topology", "memory-recall"]')
    a('  }')
    a('')
    a('  parallel "field-runtime" {')
    a('    fibers = [loadMiner, fieldView]')
    a('    strategy = "supervised-dag"')
    a('    supervisor = otp')
    a('  }')
    a('}')
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# 1. load-clean: N_LOAD agents check clean; structural counts; blowup guard
# --------------------------------------------------------------------------- #

def _test_load_clean(lines):
    cache = _builtins_cache()
    src = gen_field(N_LOAD)
    t0 = time.time()
    diags = vakedc.check_source(src, LOAD_NAME, builtins_cache=cache)
    dt = time.time() - t0
    ok = True
    if diags:
        ok = False
        lines.append(f"  FAIL load-clean: expected 0 diagnostics for "
                     f"N={N_LOAD}, got {len(diags)} "
                     f"{[d.code for d in diags][:6]}")
    graph = vakedc.parse_string(src, LOAD_NAME)
    n_nodes = sum(1 for nd in graph.nodes if nd.kind == "node")
    want = (N_LOAD + 1) + (N_LOAD + 3)   # mesh: operator+N; wf: plan+N+review+publish
    if n_nodes != want:
        ok = False
        lines.append(f"  FAIL load-clean: expected {want} graph `node` decls "
                     f"(mesh {N_LOAD + 1} + steps {N_LOAD + 3}), got {n_nodes}")
    if dt > TIME_CAP_S:
        ok = False
        lines.append(f"  FAIL load-clean: check took {dt:.1f}s > {TIME_CAP_S}s "
                     f"cap (super-linear blowup?)")
    if ok:
        lines.append(f"  load-clean: N={N_LOAD} agents (fan-out {N_LOAD}, "
                     f"{n_nodes} graph nodes) check clean in {dt:.2f}s")
    return ok


# --------------------------------------------------------------------------- #
# 2. golden-faults: three deterministic exceptions, byte-identical --json
# --------------------------------------------------------------------------- #

# Position-sorted (diagnostics are ordered by source location): the rogue
# delegation sits in the mesh, the maxDepth record field precedes the typo'd
# step inside the workflow block.
_EXPECTED_FAULTS = ["E-CAP-ATTENUATION", "E-WORKFLOW-DEPTH", "E-REF-UNRESOLVED"]


def _test_golden_faults(lines):
    cache = _builtins_cache()
    src = gen_field(N_GOLDEN, rogue=True, agent_typo=True, deep_tail=True)
    diags = vakedc.check_source(src, GOLDEN_NAME, builtins_cache=cache)
    codes = [d.code for d in diags]
    ok = True
    if codes != _EXPECTED_FAULTS:
        ok = False
        lines.append(f"  FAIL golden-faults: expected exactly "
                     f"{_EXPECTED_FAULTS}, got {codes}")
    produced = _diagnostics_json(diags)
    if not os.path.exists(GOLDEN):
        ok = False
        lines.append(f"  FAIL golden-faults: missing golden {GOLDEN}")
    else:
        expected = open(GOLDEN, encoding="utf-8").read()
        if produced != expected:
            ok = False
            lines.append("  FAIL golden-faults: --json differs from "
                         "golden/agentfield-load.diagnostics.json")
            for i, (x, y) in enumerate(zip(produced, expected)):
                if x != y:
                    lines.append(f"    first diff at byte {i}: produced {x!r} "
                                 f"vs golden {y!r}")
                    break
            else:
                lines.append(f"    length differs: produced {len(produced)} vs "
                             f"golden {len(expected)}")
    if ok:
        lines.append(f"  golden-faults: N={N_GOLDEN} variant yields exactly "
                     f"{_EXPECTED_FAULTS}; --json byte-identical to golden")
    return ok


# --------------------------------------------------------------------------- #
# 3. determinism at scale
# --------------------------------------------------------------------------- #

def _test_determinism(lines):
    cache = _builtins_cache()
    src = gen_field(N_LOAD)
    j1 = _diagnostics_json(vakedc.check_source(src, LOAD_NAME, builtins_cache=cache))
    j2 = _diagnostics_json(vakedc.check_source(src, LOAD_NAME, builtins_path=BUILTINS))
    if j1 == j2:
        lines.append(f"  determinism: N={N_LOAD} system — identical "
                     f"diagnostics JSON (cached + fresh catalog)")
        return True
    lines.append("  FAIL determinism: diagnostics JSON differs across runs")
    return False


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run():
    lines = []
    ok = True
    for fn in (_test_load_clean, _test_golden_faults, _test_determinism):
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
    print("== test_agentfield_load ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
