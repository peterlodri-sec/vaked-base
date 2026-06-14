# Inline ARP Compiled-Parallelized Execution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the vakedc typed semantic graph with a first-class execution + capability overlay (lifecycle states/transitions, wavefront schedule, capability grants/holds) plus the checker rules and verification oracle specified in `docs/language/0015-inline-arp-compiled-execution.md`.

**Architecture:** A new pure module `vakedc/schedule.py` computes the static parallel schedule. A new additive pass `vakedc/overlay.py` materializes execution/capability nodes+edges onto the LPG *after* `Resolver.build()` — it never edits the existing `_build_*` internals (lowest-risk: existing graph output for non-exec files is unchanged). `check.py` gains `E-EXEC-*` diagnostics (reusing `compute_schedule`) and extends `E-CAP-*` ref validation to fiber `policy` / surface `input`. A new `vakedc/oracle.py` derives `expected_behavior(graph)` — the projection-equivalence reference (spec §7 P3). Emitters (OTP, inline-compiled) are **out of scope** (deferred specs).

**Tech Stack:** Python 3 (stdlib only), dataclasses; existing vakedc modules (`parser` as `P`, `resolve`, `graph`, `check`); test harness `tests/spec/run_all.py` (plain-script modules, no pytest).

**Target workspace:** `.worktrees/exec-semantics` (branch `lang/execution-semantics`). All paths below are relative to that worktree root. Run tests from there: `python3 tests/spec/run_all.py`.

---

## File Structure

| File | Create/Modify | Responsibility |
|------|---------------|----------------|
| `vakedc/schedule.py` | Create | Pure schedule: `FiberIO`, `Schedule`, `compute_schedule`, AST→IO extractors |
| `vakedc/overlay.py` | Create | Additive LPG pass: lifecycle, capability, schedule materialization |
| `vakedc/resolve.py` | Modify (`build_graph`, ~L346) | Call `apply_execution_overlay` after `Resolver.build()` |
| `vakedc/check.py` | Modify (`check_source`, ~L1117) | `E-EXEC-*` + extend `E-CAP-*` to fiber/surface |
| `vakedc/oracle.py` | Create | `expected_behavior(graph)` projection-equivalence oracle |
| `vaked/examples/primitives/wavefront.vaked` | Create | 3-fiber dependency chain for wavefront levels |
| `tests/spec/test_exec_schedule.py` | Create | Unit tests for schedule + overlay + oracle |
| `tests/spec/run_all.py` | Modify (~L21-37) | Register `exec_schedule` module |
| `tests/spec/test_examples_parse.py` | Modify (~L33) | Bump `EXPECTED_VAKED_COUNT` 17→18 |
| `tests/spec/test_vakedc.py` | Modify (~L33) | Add `wavefront.vaked` to graph-golden set |
| `tests/spec/test_vakedc_check.py` | Modify | Assert new example error codes |
| `tests/spec/golden/*.graph.json` | Create | Regenerated goldens for lifecycle/capability-graph/wavefront |
| `docs/language/0012-lowering.md` | (none) | reference only |

**Three independent file-streams** (for parallel fan-out): **(A)** `schedule.py` → Task 2. **(B)** `overlay.py`+`resolve.py` → Tasks 3→4→5 (sequential, same file). **(C)** `check.py` → Tasks 6→7→8 (sequential, same file). Streams A/B/C run in parallel. Task 9 (oracle) depends on B. Task 10 (goldens+suite) depends on all.

---

## Task 1: Scaffolding — baseline + wavefront example

**Parallelization:** sequential (gate). depends-on: none.

**Files:**
- Create: `vaked/examples/primitives/wavefront.vaked`
- Modify: `tests/spec/test_examples_parse.py:33`

- [ ] **Step 1: Verify clean baseline**

Run: `python3 tests/spec/run_all.py`
Expected: `7/7 test modules passed => ALL GREEN`. If not green, STOP and report.

- [ ] **Step 2: Create the wavefront example**

Create `vaked/examples/primitives/wavefront.vaked`:

```vaked
# wavefront.vaked — explicit fiber dependency chain (0015)
# capture (L0) -> compress (L1) -> publish (L2): three wavefronts.

fiber capture {
  engine = zigcap
  input  = device.camera
  output = stream.raw
}

fiber compress {
  engine = zigimg
  input  = stream.raw
  output = artifacts.compressed
}

fiber publish {
  engine = zigpub
  input  = artifacts.compressed
  output = surface.feed
}

parallel "capture-pipeline" {
  fibers = [capture, compress, publish]

  strategy   = "supervised-dag"
  supervisor = otp

  lifecycle {
    on pause  { drain_timeout = "2s" }
    on resume { }
    on stop   { flush = true }
  }
}
```

- [ ] **Step 3: Bump the example count**

In `tests/spec/test_examples_parse.py`, change `EXPECTED_VAKED_COUNT = 17` to `EXPECTED_VAKED_COUNT = 18` (and update the `# 11` comment on the `primitives/*.vaked` glob to `# 12`).

- [ ] **Step 4: Verify parse + count**

Run: `python3 tests/spec/run_all.py`
Expected: still `7/7 ... ALL GREEN` (the new file parses; count matches 18).

- [ ] **Step 5: Commit**

```bash
git add vaked/examples/primitives/wavefront.vaked tests/spec/test_examples_parse.py
git commit -m "test(examples): add wavefront.vaked (3-level dependency chain)"
```

---

## Task 2: `vakedc/schedule.py` — static parallel schedule [STREAM A]

**Parallelization:** parallel-safe. depends-on: Task 1.

**Files:**
- Create: `vakedc/schedule.py`
- Create (partial): `tests/spec/test_exec_schedule.py`
- Modify: `tests/spec/run_all.py:21-37`

- [ ] **Step 1: Write the failing test**

Create `tests/spec/test_exec_schedule.py` (mirror the module run-protocol of `tests/spec/test_vakedc_check.py` — same `def run(lines)`/return convention; open that sibling file and copy its top-level structure):

```python
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from vakedc.schedule import FiberIO, compute_schedule

def _t_levels(lines):
    ok = True
    ios = [
        FiberIO("capture",  frozenset({"device.camera"}),     frozenset({"stream.raw"})),
        FiberIO("compress", frozenset({"stream.raw"}),         frozenset({"artifacts.compressed"})),
        FiberIO("publish",  frozenset({"artifacts.compressed"}), frozenset({"surface.feed"})),
    ]
    s = compute_schedule(ios)
    if s.cycle is not None:
        ok = False; lines.append(f"  FAIL: unexpected cycle {s.cycle}")
    if (s.levels.get("capture"), s.levels.get("compress"), s.levels.get("publish")) != (0, 1, 2):
        ok = False; lines.append(f"  FAIL levels: {s.levels}")
    if s.checkpoints != [0, 1, 2]:
        ok = False; lines.append(f"  FAIL checkpoints: {s.checkpoints}")
    return ok

def _t_cycle(lines):
    ios = [
        FiberIO("a", frozenset({"x"}), frozenset({"y"})),
        FiberIO("b", frozenset({"y"}), frozenset({"x"})),
    ]
    s = compute_schedule(ios)
    if s.cycle is None:
        lines.append("  FAIL: expected a cycle, got none"); return False
    return True

def run(lines):
    return _t_levels(lines) and _t_cycle(lines)

if __name__ == "__main__":
    out = []
    print("PASS" if run(out) else "FAIL"); [print(l) for l in out]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python3 tests/spec/test_exec_schedule.py`
Expected: FAIL / ImportError (`vakedc.schedule` does not exist).

- [ ] **Step 3: Implement `vakedc/schedule.py`**

```python
#!/usr/bin/env python3
"""vakedc.schedule — static parallel schedule (0015 §5).

Pure function of a parallel group's fibers: dependency DAG (A depends-on B when
A's `input` ref matches B's `output` ref) -> cycle check -> longest-path
wavefront levels -> one checkpoint per boundary. Consumed by both check.py
(diagnostics) and overlay.py (IR materialization). Deterministic: all iteration
over sorted names.
"""
from __future__ import annotations
from dataclasses import dataclass

from . import parser as P


@dataclass
class FiberIO:
    name: str
    inputs: "frozenset[str]"
    outputs: "frozenset[str]"


@dataclass
class Schedule:
    levels: dict           # fiber name -> wavefront level (int)
    deps: list             # sorted list of (a, b, via): a depends-on b through ref `via`
    checkpoints: list      # [0..max_level]
    rewindable: dict       # level -> bool
    cycle: "list | None"   # offending cycle names, or None


def _ref_str(value):
    return ".".join(value.parts) if isinstance(value, P.Ref) else None


def fiber_ios(member_decls):
    """member_decls: list[P.Decl] (the group's fibers). -> list[FiberIO]."""
    out = []
    for d in member_decls:
        inputs, outputs = set(), set()
        for st in d.body:
            if isinstance(st, P.Assignment):
                rs = _ref_str(st.value)
                if rs is None:
                    continue
                if st.target == "input":
                    inputs.add(rs)
                elif st.target == "output":
                    outputs.add(rs)
        out.append(FiberIO(d.name, frozenset(inputs), frozenset(outputs)))
    return out


def member_names(group_decl):
    """Names listed in a parallel group's `fibers = [a, b, ...]`."""
    names = []
    for st in group_decl.body:
        if isinstance(st, P.Assignment) and st.target == "fibers" \
                and isinstance(st.value, P.ListLit):
            for item in st.value.items:
                if isinstance(item, P.Ref) and len(item.parts) == 1:
                    names.append(item.parts[0])
    return names


def _find_cycle(adj):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    stack = []

    def dfs(n):
        color[n] = GRAY
        stack.append(n)
        for m in sorted(adj[n]):
            if color[m] == GRAY:
                return stack[stack.index(m):] + [m]
            if color[m] == WHITE:
                r = dfs(m)
                if r:
                    return r
        stack.pop()
        color[n] = BLACK
        return None

    for n in sorted(adj):
        if color[n] == WHITE:
            r = dfs(n)
            if r:
                return r
    return None


def compute_schedule(fiber_io_list, retained=frozenset()):
    ios = sorted(fiber_io_list, key=lambda f: f.name)
    by_output = {}
    for f in ios:
        for o in sorted(f.outputs):
            by_output.setdefault(o, f.name)
    adj = {f.name: set() for f in ios}
    deps = []
    for f in ios:
        for inp in sorted(f.inputs):
            producer = by_output.get(inp)
            if producer is not None and producer != f.name and producer not in adj[f.name]:
                adj[f.name].add(producer)
                deps.append((f.name, producer, inp))
    deps.sort()

    cycle = _find_cycle(adj)
    if cycle is not None:
        return Schedule({}, deps, [], {}, cycle)

    levels = {}

    def level_of(n):
        if n in levels:
            return levels[n]
        levels[n] = 0 if not adj[n] else 1 + max(level_of(d) for d in sorted(adj[n]))
        return levels[n]

    for f in ios:
        level_of(f.name)
    max_level = max(levels.values()) if levels else 0
    checkpoints = list(range(max_level + 1))

    rewindable = {}
    for lv in checkpoints:
        crossing = set()
        for f in ios:
            if levels[f.name] == lv + 1:
                crossing |= f.inputs
        rewindable[lv] = bool(crossing) and crossing.issubset(retained)
    return Schedule(levels, deps, checkpoints, rewindable, None)
```

- [ ] **Step 4: Register the test module**

In `tests/spec/run_all.py`, add the import alongside the others and an entry in `MODULES`:

```python
import test_exec_schedule as t_exec
# ... in MODULES list:
    ("exec_schedule", t_exec),
```

- [ ] **Step 5: Run tests**

Run: `python3 tests/spec/run_all.py`
Expected: `8/8 test modules passed => ALL GREEN`.

- [ ] **Step 6: Commit**

```bash
git add vakedc/schedule.py tests/spec/test_exec_schedule.py tests/spec/run_all.py
git commit -m "feat(vakedc): schedule.py — static wavefront schedule + cycle detection"
```

---

## Task 3: `vakedc/overlay.py` — lifecycle states/transitions [STREAM B]

**Parallelization:** parallel-safe vs streams A/C. depends-on: Task 1.

**Files:**
- Create: `vakedc/overlay.py`
- Modify: `vakedc/resolve.py:346-350` (`build_graph`)
- Modify: `tests/spec/test_exec_schedule.py` (add overlay test)

- [ ] **Step 1: Write the failing test** — append to `tests/spec/test_exec_schedule.py`:

```python
from vakedc.parser import parse_source
from vakedc.resolve import build_graph

_LIFECYCLE_SRC = """fiber mediaCompress {
  input = stream.screenrec
  output = artifacts.out
  lifecycle {
    on pause  { drain_timeout = "2s" }
    on resume { }
    on stop   { flush = true }
  }
}
"""

def _t_overlay_lifecycle(lines):
    ok = True
    g = build_graph(parse_source(_LIFECYCLE_SRC, "m.vaked"), "m.vaked")
    ids = {n.id for n in g.nodes}
    kinds = {n.kind for n in g.nodes}
    for need in ("m.vaked#mediaCompress/state:running",
                 "m.vaked#mediaCompress/state:paused",
                 "m.vaked#mediaCompress/state:stopped",
                 "m.vaked#mediaCompress/transition:pause"):
        if need not in ids:
            ok = False; lines.append(f"  FAIL: missing node {need}")
    if "lifecycle-state" not in kinds or "transition" not in kinds:
        ok = False; lines.append(f"  FAIL: kinds {kinds}")
    edges = {(e.source, e.label, e.target) for e in g.edges}
    want = ("m.vaked#mediaCompress", "controls", "m.vaked#mediaCompress/transition:pause")
    if want not in edges:
        ok = False; lines.append("  FAIL: missing controls edge")
    return ok
```

Add `_t_overlay_lifecycle(lines)` to the `and`-chain in `run(lines)`.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/test_exec_schedule.py`
Expected: FAIL (states/transitions not materialized; `build_graph` ignores lifecycle).

- [ ] **Step 3: Implement `vakedc/overlay.py`** (lifecycle portion; capability + schedule added in Tasks 4–5)

```python
#!/usr/bin/env python3
"""vakedc.overlay — additive execution/capability overlay on the LPG (0015 §4).

Runs AFTER Resolver.build(). Only ADDS nodes/edges; never mutates existing build
logic. Reconstructs node ids by the same path-derived chain rule the resolver
uses (graph.node_id(basename, chain)).
"""
from __future__ import annotations

from . import parser as P
from .graph import GraphNode, GraphEdge, Provenance, Span, node_id

# transition state machine (0015 §4)
_TRANSITIONS = {
    "pause":  ("running", "paused"),
    "resume": ("paused",  "running"),
    "stop":   ("running", "stopped"),
    "rewind": ("paused",  "running"),
}


def _prov(decl, provfile):
    return Provenance(file=provfile, decl=f"{decl.kind} {decl.name}",
                      span=Span(decl.byteStart, decl.byteEnd, decl.line, decl.col))


def _emit_lifecycle(graph, life, chain, owner_id, owner, basename, provfile):
    prov = _prov(owner, provfile)
    needed = {"running"}
    for cl in life.clauses:
        frm, to = _TRANSITIONS[cl.event]
        needed.add(frm); needed.add(to)
    state_id = {}
    for name in sorted(needed):
        sid = node_id(basename, chain + ["state:" + name])
        graph.add_node(GraphNode(id=sid, kind="lifecycle-state", name=name,
                                 labels=["lifecycle-state"],
                                 props={"terminal": name == "stopped"},
                                 provenance=prov))
        state_id[name] = sid
    for cl in life.clauses:
        frm, to = _TRANSITIONS[cl.event]
        tid = node_id(basename, chain + ["transition:" + cl.event])
        graph.add_node(GraphNode(id=tid, kind="transition", name=cl.event,
                                 labels=["transition"], props={"event": cl.event},
                                 provenance=prov))
        graph.add_edge(GraphEdge(owner_id, tid, "controls"))
        graph.add_edge(GraphEdge(tid, state_id[frm], "enabled-in"))
        graph.add_edge(GraphEdge(tid, state_id[to], "results-in"))


def _walk(graph, body, chain, owner_id, owner, basename, provfile):
    """Recurse a decl/nodedecl body, dispatching overlay handlers."""
    for st in body:
        if isinstance(st, P.LifecycleDecl):
            _emit_lifecycle(graph, st, chain, owner_id, owner, basename, provfile)
        elif isinstance(st, P.NodeDecl):
            child_chain = chain + [st.name]
            child_id = node_id(basename, child_chain)
            _walk(graph, st.body, child_chain, child_id, owner, basename, provfile)
        elif isinstance(st, P.Decl):
            child_chain = chain + [st.name]
            child_id = node_id(basename, child_chain)
            _walk(graph, st.body, child_chain, child_id, st, basename, provfile)


def apply_execution_overlay(graph, items, basename, provfile):
    for it in items:
        if isinstance(it, P.Decl):
            chain = [it.name]
            _walk(graph, it.body, chain, node_id(basename, chain), it, basename, provfile)
```

- [ ] **Step 4: Wire into `build_graph`** — modify `vakedc/resolve.py` (`build_graph`, ~L346):

```python
def build_graph(items, filename: str) -> Graph:
    resolver = Resolver(items, filename)
    g = resolver.build()
    from .overlay import apply_execution_overlay
    apply_execution_overlay(g, items, resolver.basename, resolver.provfile)
    return g
```

(Confirm the attribute names `resolver.basename` / `resolver.provfile` by reading the `Resolver.__init__`; they are used internally as `self.basename` / `self.provfile`. If named differently, use the actual attribute.)

- [ ] **Step 5: Run tests**

Run: `python3 tests/spec/test_exec_schedule.py` then `python3 tests/spec/run_all.py`
Expected: overlay test PASS; `8/8 ... ALL GREEN`.

- [ ] **Step 6: Commit**

```bash
git add vakedc/overlay.py vakedc/resolve.py tests/spec/test_exec_schedule.py
git commit -m "feat(vakedc): overlay.py — lifecycle states/transitions on the LPG"
```

---

## Task 4: overlay — capability grants + holds edges [STREAM B]

**Parallelization:** sequential after Task 3 (same file). depends-on: Task 3.

**Files:**
- Modify: `vakedc/overlay.py`
- Modify: `tests/spec/test_exec_schedule.py`

- [ ] **Step 1: Write the failing test** — append:

```python
_CAP_SRC = """capability fs {
  grant repo_ro repo_rw
  order repo_ro < repo_rw
}
mesh agentfield {
  node codex {
    capabilities = [fs.repo_rw]
  }
}
"""

def _t_overlay_caps(lines):
    ok = True
    g = build_graph(parse_source(_CAP_SRC, "c.vaked"), "c.vaked")
    ids = {n.id for n in g.nodes}
    if "c.vaked#fs/grant:repo_rw" not in ids:
        ok = False; lines.append("  FAIL: missing grant node")
    edges = {(e.source, e.label, e.target) for e in g.edges}
    want = ("c.vaked#agentfield/codex", "holds", "c.vaked#fs/grant:repo_rw")
    if want not in edges:
        ok = False; lines.append(f"  FAIL: missing holds edge; edges={sorted(edges)}")
    return ok
```

Add to `run()` chain.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/test_exec_schedule.py`
Expected: FAIL (no grant nodes / holds edges yet).

- [ ] **Step 3: Implement** — add to `vakedc/overlay.py`:

```python
def _emit_grants(graph, cap_decl, basename, provfile):
    """capability domain decl -> one `grant` node per declared grant."""
    prov = _prov(cap_decl, provfile)
    for st in cap_decl.body:
        if isinstance(st, P.GrantDecl):
            for gname in st.names:
                gid = node_id(basename, [cap_decl.name, "grant:" + gname])
                graph.add_node(GraphNode(id=gid, kind="grant", name=gname,
                                         labels=["grant"], props={}, provenance=prov))
```

Add a `holds`-edge branch inside `_walk` (handle `Assignment` named `capabilities`):

```python
        elif isinstance(st, P.Assignment) and st.target == "capabilities" \
                and isinstance(st.value, P.ListLit):
            for item in st.value.items:
                if isinstance(item, P.Ref) and len(item.parts) == 2:
                    domain, grant = item.parts
                    gid = node_id(basename, [domain, "grant:" + grant])
                    graph.add_edge(GraphEdge(owner_id, gid, "holds"))
```

Call `_emit_grants` first in `apply_execution_overlay`:

```python
def apply_execution_overlay(graph, items, basename, provfile):
    for it in items:
        if isinstance(it, P.Decl) and it.kind == "capability":
            _emit_grants(graph, it, basename, provfile)
    for it in items:
        if isinstance(it, P.Decl):
            chain = [it.name]
            _walk(graph, it.body, chain, node_id(basename, chain), it, basename, provfile)
```

Note: for a fiber `policy { capabilities = [...] }`, `holds` originates from the `policy` NodeDecl node (`#fiber/policy`), reachable from the fiber via the existing `contains` edge — traversal `fiber → policy → holds → grant` answers "does fiber hold X". This is captured by the golden in Task 10.

- [ ] **Step 4: Run tests**

Run: `python3 tests/spec/test_exec_schedule.py` then `python3 tests/spec/run_all.py`
Expected: caps test PASS; `8/8 ALL GREEN`.

- [ ] **Step 5: Commit**

```bash
git add vakedc/overlay.py tests/spec/test_exec_schedule.py
git commit -m "feat(vakedc): overlay grant nodes + holds edges (0014 capability graph)"
```

---

## Task 5: overlay — schedule materialization [STREAM B]

**Parallelization:** sequential after Task 4; also needs Task 2. depends-on: Task 2, Task 4.

**Files:**
- Modify: `vakedc/overlay.py`
- Modify: `tests/spec/test_exec_schedule.py`

- [ ] **Step 1: Write the failing test** — append (uses the wavefront source inline):

```python
_WAVE_SRC = """fiber capture  { input = device.camera        output = stream.raw }
fiber compress { input = stream.raw           output = artifacts.compressed }
fiber publish  { input = artifacts.compressed output = surface.feed }
parallel "pipe" {
  fibers = [capture, compress, publish]
  lifecycle { on rewind { } }
}
"""

def _t_overlay_schedule(lines):
    ok = True
    g = build_graph(parse_source(_WAVE_SRC, "w.vaked"), "w.vaked")
    node = {n.id: n for n in g.nodes}
    if node["w.vaked#compress"].props.get("level") != 1:
        ok = False; lines.append(f"  FAIL compress level: {node['w.vaked#compress'].props}")
    edges = {(e.source, e.label, e.target) for e in g.edges}
    if ("w.vaked#compress", "depends-on", "w.vaked#capture") not in edges:
        ok = False; lines.append("  FAIL: missing depends-on edge")
    if "w.vaked#pipe/checkpoint:0" not in node:
        ok = False; lines.append("  FAIL: missing checkpoint node")
    return ok
```

Add to `run()` chain.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/test_exec_schedule.py`
Expected: FAIL (no level prop / depends-on / checkpoint).

- [ ] **Step 3: Implement** — add to `vakedc/overlay.py`:

```python
from .schedule import fiber_ios, member_names, compute_schedule


def _emit_schedule(graph, group_decl, basename, provfile, decl_by_name):
    prov = _prov(group_decl, provfile)
    names = member_names(group_decl)
    members = [decl_by_name[n] for n in names if n in decl_by_name]
    if not members:
        return
    sched = compute_schedule(fiber_ios(members))
    if sched.cycle is not None:
        return  # cycle is a checker error (E-EXEC-CYCLE); skip materialization
    for a, b, via in sched.deps:
        graph.add_edge(GraphEdge(node_id(basename, [a]), node_id(basename, [b]),
                                 "depends-on", {"via": via}))
    for name, lvl in sched.levels.items():
        nd = graph.get_node(node_id(basename, [name]))
        if nd is not None:
            nd.props["level"] = lvl
    gchain = [group_decl.name]
    for lv in sched.checkpoints:
        cid = node_id(basename, gchain + ["checkpoint:" + str(lv)])
        graph.add_node(GraphNode(id=cid, kind="checkpoint", name=str(lv),
                                 labels=["checkpoint"],
                                 props={"level": lv, "rewindable": sched.rewindable[lv]},
                                 provenance=prov))
        for name, nlvl in sched.levels.items():
            if nlvl == lv:
                graph.add_edge(GraphEdge(cid, node_id(basename, [name]), "boundary-for"))
    # rewind-to: any rewind transition on the group -> nearest rewindable checkpoint
    rewindable_levels = [lv for lv in sched.checkpoints if sched.rewindable[lv]]
    if rewindable_levels:
        tid = node_id(basename, gchain + ["transition:rewind"])
        if graph.get_node(tid) is not None:
            target = node_id(basename, gchain + ["checkpoint:" + str(min(rewindable_levels))])
            graph.add_edge(GraphEdge(tid, target, "rewind-to"))
```

Extend `apply_execution_overlay` to build `decl_by_name` and call `_emit_schedule` for parallel groups:

```python
def apply_execution_overlay(graph, items, basename, provfile):
    decl_by_name = {it.name: it for it in items if isinstance(it, P.Decl)}
    for it in items:
        if isinstance(it, P.Decl) and it.kind == "capability":
            _emit_grants(graph, it, basename, provfile)
    for it in items:
        if isinstance(it, P.Decl):
            chain = [it.name]
            _walk(graph, it.body, chain, node_id(basename, chain), it, basename, provfile)
            if it.kind == "parallel":
                _emit_schedule(graph, it, basename, provfile, decl_by_name)
```

- [ ] **Step 4: Run tests**

Run: `python3 tests/spec/test_exec_schedule.py` then `python3 tests/spec/run_all.py`
Expected: schedule test PASS; `8/8 ALL GREEN`.

- [ ] **Step 5: Commit**

```bash
git add vakedc/overlay.py tests/spec/test_exec_schedule.py
git commit -m "feat(vakedc): overlay schedule — depends-on, levels, checkpoints"
```

---

## Task 6: checker — E-EXEC-LIFECYCLE-CONTEXT + E-EXEC-BAD-TRANSITION [STREAM C]

**Parallelization:** parallel-safe vs streams A/B. depends-on: Task 1. (Sequential before Tasks 7, 8 — same file `check.py`.)

**Files:**
- Modify: `vakedc/check.py` (add `_check_execution`; call from `check_source`)
- Modify: `tests/spec/test_vakedc_check.py`

- [ ] **Step 1: Write the failing test** — add to `tests/spec/test_vakedc_check.py` a case asserting a `lifecycle` block in a non-parallel/fiber kind yields `E-EXEC-LIFECYCLE-CONTEXT`, and a duplicate `on pause` yields `E-EXEC-BAD-TRANSITION`:

```python
def _t_exec_context(lines):
    src = 'index foo {\n  lifecycle { on pause { } }\n}\n'
    diags = vakedc.check_source(src, "x.vaked", builtins_cache=cache)
    codes = [d.code for d in diags]
    if "E-EXEC-LIFECYCLE-CONTEXT" not in codes:
        lines.append(f"  FAIL: expected E-EXEC-LIFECYCLE-CONTEXT, got {codes}"); return False
    return True

def _t_exec_bad_transition(lines):
    src = 'fiber f {\n  lifecycle { on pause { } on pause { } }\n}\n'
    diags = vakedc.check_source(src, "x.vaked", builtins_cache=cache)
    codes = [d.code for d in diags]
    if "E-EXEC-BAD-TRANSITION" not in codes:
        lines.append(f"  FAIL: expected E-EXEC-BAD-TRANSITION, got {codes}"); return False
    return True
```

Register both in the module's `run`/entry chain (follow the file's existing pattern for adding a case).

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/run_all.py`
Expected: `vakedc_check` FAILs (codes not emitted).

- [ ] **Step 3: Implement** — add to `vakedc/check.py` and call from `check_source` (after the existing decl-walk loop, before `diags.sort(...)`):

```python
_LIFECYCLE_KINDS = frozenset(("parallel", "fiber"))
_LIFECYCLE_EVENTS = frozenset(("pause", "resume", "stop", "rewind"))


def _decl_span(decl):
    return (decl.byteStart, decl.byteEnd, decl.line, decl.col)


def _check_execution(items, smap, filename, diags):
    def walk(decl):
        for st in decl.body:
            if isinstance(st, P.LifecycleDecl):
                if decl.kind not in _LIFECYCLE_KINDS:
                    _emit(diags, "E-EXEC-LIFECYCLE-CONTEXT", filename,
                          _decl_span(decl), decl,
                          f"`lifecycle` is only valid in `parallel`/`fiber`, not `{decl.kind}`")
                seen = set()
                for cl in st.clauses:
                    if cl.event in seen:
                        _emit(diags, "E-EXEC-BAD-TRANSITION", filename,
                              _decl_span(decl), decl,
                              f"duplicate `on {cl.event}` in lifecycle block")
                    seen.add(cl.event)
            elif isinstance(st, (P.Decl,)):
                walk(st)
    for it in items:
        if isinstance(it, P.Decl):
            walk(it)
```

Add the call inside `check_source` (the `items` and `smap` are already in scope there):

```python
    _check_execution(items, smap, filename, diags)
```

(`_emit` signature is `_emit(diags, code, file, span, decl_or_spec, message)`; `P` is the parser import already used in `check.py`.)

- [ ] **Step 4: Run tests**

Run: `python3 tests/spec/run_all.py`
Expected: `8/8 ALL GREEN` (both new cases pass; nothing else regresses).

- [ ] **Step 5: Commit**

```bash
git add vakedc/check.py tests/spec/test_vakedc_check.py
git commit -m "feat(check): E-EXEC-LIFECYCLE-CONTEXT + E-EXEC-BAD-TRANSITION"
```

---

## Task 7: checker — E-EXEC-CYCLE + E-EXEC-REWIND-NO-RETENTION [STREAM C]

**Parallelization:** sequential after Task 6 (same file). depends-on: Task 2, Task 6.

**Files:**
- Modify: `vakedc/check.py` (extend `_check_execution`)
- Modify: `tests/spec/test_vakedc_check.py`

- [ ] **Step 1: Write the failing test** — add cases:

```python
def _t_exec_cycle(lines):
    src = ('fiber a { input = s.y output = s.x }\n'
           'fiber b { input = s.x output = s.y }\n'
           'parallel "p" { fibers = [a, b] }\n')
    codes = [d.code for d in vakedc.check_source(src, "x.vaked", builtins_cache=cache)]
    if "E-EXEC-CYCLE" not in codes:
        lines.append(f"  FAIL: expected E-EXEC-CYCLE, got {codes}"); return False
    return True

def _t_exec_rewind_no_retention(lines):
    src = ('fiber a { input = s.in output = s.out }\n'
           'parallel "p" { fibers = [a]\n  lifecycle { on rewind { } } }\n')
    codes = [d.code for d in vakedc.check_source(src, "x.vaked", builtins_cache=cache)]
    if "E-EXEC-REWIND-NO-RETENTION" not in codes:
        lines.append(f"  FAIL: expected E-EXEC-REWIND-NO-RETENTION, got {codes}"); return False
    return True
```

Register both.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/run_all.py` → `vakedc_check` FAIL.

- [ ] **Step 3: Implement** — extend `_check_execution` to handle `parallel` groups (add inside `walk`, or as a second loop over parallel decls):

```python
    from .schedule import fiber_ios, member_names, compute_schedule
    for it in items:
        if isinstance(it, P.Decl) and it.kind == "parallel":
            decl_by_name = {d.name: d for d in items if isinstance(d, P.Decl)}
            members = [decl_by_name[n] for n in member_names(it) if n in decl_by_name]
            sched = compute_schedule(fiber_ios(members))
            if sched.cycle is not None:
                _emit(diags, "E-EXEC-CYCLE", filename, _decl_span(it), it,
                      f"dependency cycle among fibers: {' -> '.join(sched.cycle)}")
                continue
            has_rewind = any(
                isinstance(st, P.LifecycleDecl)
                and any(cl.event == "rewind" for cl in st.clauses)
                for st in it.body)
            if has_rewind and not any(sched.rewindable.get(lv) for lv in sched.checkpoints):
                _emit(diags, "E-EXEC-REWIND-NO-RETENTION", filename, _decl_span(it), it,
                      "`on rewind` requires an input stream with `retention`; "
                      "no rewindable checkpoint exists")
```

- [ ] **Step 4: Run tests**

Run: `python3 tests/spec/run_all.py`
Expected: `8/8 ALL GREEN`.

- [ ] **Step 5: Commit**

```bash
git add vakedc/check.py tests/spec/test_vakedc_check.py
git commit -m "feat(check): E-EXEC-CYCLE + E-EXEC-REWIND-NO-RETENTION (reuse compute_schedule)"
```

---

## Task 8: checker — extend E-CAP-* to fiber policy + surface input [STREAM C]

**Parallelization:** sequential after Task 7 (same file). depends-on: Task 7.

**Files:**
- Modify: `vakedc/check.py`
- Modify: `tests/spec/test_vakedc_check.py`

- [ ] **Step 1: Write the failing test** — a fiber `policy` referencing an unknown grant must yield `E-CAP-UNKNOWN-GRANT`:

```python
def _t_cap_fiber_policy(lines):
    src = ('capability fs { grant repo_ro repo_rw\n  order repo_ro < repo_rw }\n'
           'fiber f {\n  policy { capabilities = [fs.nope] }\n}\n')
    codes = [d.code for d in vakedc.check_source(src, "x.vaked", builtins_cache=cache)]
    if "E-CAP-UNKNOWN-GRANT" not in codes:
        lines.append(f"  FAIL: expected E-CAP-UNKNOWN-GRANT, got {codes}"); return False
    return True
```

Register it.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/run_all.py` → FAIL (refs in fiber policy not validated today).

- [ ] **Step 3: Implement** — add a walk that finds `capabilities` assignments in `fiber`/`surface` decls and validates each ref via the existing `_check_capability_refs`. Add to `_check_execution` (it already has `items`, `registry` must be passed in — update its signature and the call site to include `registry`):

```python
# update signature: def _check_execution(items, registry, smap, filename, diags):
    _CAP_CONTEXT_KINDS = frozenset(("fiber", "surface"))

    def caps_in(decl):
        found = []
        def rec(body):
            for st in body:
                if isinstance(st, P.Assignment) and st.target == "capabilities" \
                        and isinstance(st.value, P.ListLit):
                    found.append(st.value)
                elif isinstance(st, P.NodeDecl):
                    rec(st.body)
                elif isinstance(st, P.Decl):
                    rec(st.body)
        rec(decl.body)
        return found

    for it in items:
        if isinstance(it, P.Decl) and it.kind in _CAP_CONTEXT_KINDS:
            for listlit in caps_in(it):
                for ref in listlit.items:
                    if isinstance(ref, P.Ref) and len(ref.parts) == 2:
                        span = (ref.byteStart, ref.byteEnd, ref.line, ref.col)
                        _check_capability_refs(ref.parts[0], ref.parts[1],
                                               registry, filename, span, it, diags)
```

Update the `check_source` call: `_check_execution(items, registry, smap, filename, diags)`.

- [ ] **Step 4: Run tests**

Run: `python3 tests/spec/run_all.py`
Expected: `8/8 ALL GREEN`. Confirm `capability-graph.vaked` (which has a valid `fs.repo_rw` in fiber policy) still produces **no** new errors.

- [ ] **Step 5: Commit**

```bash
git add vakedc/check.py tests/spec/test_vakedc_check.py
git commit -m "feat(check): extend E-CAP-* ref validation to fiber policy + surface"
```

---

## Task 9: verification oracle — `expected_behavior(graph)` [depends STREAM B]

**Parallelization:** sequential. depends-on: Task 5.

**Files:**
- Create: `vakedc/oracle.py`
- Modify: `tests/spec/test_exec_schedule.py`

- [ ] **Step 1: Write the failing test** — append:

```python
from vakedc.oracle import expected_behavior

def _t_oracle(lines):
    g = build_graph(parse_source(_WAVE_SRC, "w.vaked"), "w.vaked")
    beh = expected_behavior(g)
    ok = True
    if beh["start_order"] != [["capture"], ["compress"], ["publish"]]:
        ok = False; lines.append(f"  FAIL start_order: {beh['start_order']}")
    if "pause" not in beh["control_alphabet"] or "stop" not in beh["control_alphabet"]:
        ok = False; lines.append(f"  FAIL control_alphabet: {beh['control_alphabet']}")
    return ok
```

Add to `run()` chain.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 tests/spec/test_exec_schedule.py`
Expected: FAIL (`vakedc.oracle` missing).

- [ ] **Step 3: Implement `vakedc/oracle.py`** (spec §7 P3 — projection-independent behavior):

```python
#!/usr/bin/env python3
"""vakedc.oracle — projection-equivalence reference (0015 §7 P3).

expected_behavior(graph) returns the projection-independent observable behavior
both projections (OTP, inline-compiled) must reproduce: the control alphabet,
each entity's capability set, and the fiber-start partial order (wavefronts).
Pure function of the graph; deterministic (sorted).
"""
from __future__ import annotations


def expected_behavior(graph):
    nodes = {n.id: n for n in graph.nodes}
    # control alphabet: distinct transition events
    control = sorted({n.props.get("event") for n in graph.nodes
                      if n.kind == "transition"})
    # capability set per holder (from `holds` edges)
    caps = {}
    for e in graph.edges:
        if e.label == "holds":
            caps.setdefault(e.source, set()).add(nodes[e.target].name
                                                 if e.target in nodes else e.target)
    caps = {k: sorted(v) for k, v in sorted(caps.items())}
    # start partial order: fibers grouped by `level`, ascending
    by_level = {}
    for n in graph.nodes:
        if "level" in n.props:
            by_level.setdefault(n.props["level"], []).append(n.name)
    start_order = [sorted(by_level[lv]) for lv in sorted(by_level)]
    return {"control_alphabet": control, "capabilities": caps,
            "start_order": start_order}
```

- [ ] **Step 4: Run tests**

Run: `python3 tests/spec/test_exec_schedule.py` then `python3 tests/spec/run_all.py`
Expected: oracle test PASS; `8/8 ALL GREEN`.

- [ ] **Step 5: Commit**

```bash
git add vakedc/oracle.py tests/spec/test_exec_schedule.py
git commit -m "feat(vakedc): oracle.py — expected_behavior projection-equivalence reference"
```

---

## Task 10: goldens + full suite + review

**Parallelization:** sequential (integration gate). depends-on: Tasks 3,4,5,6,7,8,9.

**Files:**
- Modify: `tests/spec/test_vakedc.py:33` (add `wavefront.vaked`)
- Create: `tests/spec/golden/lifecycle.graph.json`, `tests/spec/golden/capability-graph.graph.json`, `tests/spec/golden/wavefront.graph.json`

- [ ] **Step 1: Add wavefront to the graph-golden set** — in `tests/spec/test_vakedc.py`, add `"wavefront.vaked"` to the list of files compared against goldens (next to the existing `lifecycle.vaked` / `capability-graph.vaked` entries, ~L33-34).

- [ ] **Step 2: Generate the goldens** (the implementation is the source of truth; capture canonical JSON):

```bash
python3 -m vakedc parse vaked/examples/primitives/lifecycle.vaked --print > tests/spec/golden/lifecycle.graph.json
python3 -m vakedc parse vaked/examples/primitives/capability-graph.vaked --print > tests/spec/golden/capability-graph.graph.json
python3 -m vakedc parse vaked/examples/primitives/wavefront.vaked --print > tests/spec/golden/wavefront.graph.json
```

(Confirm the exact golden filename convention by reading `test_vakedc.py` — it may expect `<name>.graph.json` vs `<name>`. Match it. If `--print` is not the canonical-JSON flag, use the flag `test_vakedc` itself uses to obtain `to_canonical_json(graph)`.)

- [ ] **Step 3: Eyeball the goldens** — open each and verify it contains the expected overlay: `lifecycle-state`/`transition`/`controls`/`enabled-in`/`results-in` for lifecycle.vaked; `grant`/`holds` for capability-graph.vaked; `depends-on`/`level`/`checkpoint`/`boundary-for` for wavefront.vaked. If any expected structure is missing, fix the overlay (Tasks 3–5) before committing the golden.

- [ ] **Step 4: Run full suite**

Run: `python3 tests/spec/run_all.py`
Expected: `8/8 test modules passed => ALL GREEN`.

- [ ] **Step 5: Determinism check** — re-emit and diff to prove §10 determinism:

```bash
python3 -m vakedc parse vaked/examples/primitives/wavefront.vaked --print | diff - tests/spec/golden/wavefront.graph.json && echo DETERMINISTIC
```

Expected: `DETERMINISTIC` (no diff).

- [ ] **Step 6: Commit**

```bash
git add tests/spec/test_vakedc.py tests/spec/golden/*.graph.json
git commit -m "test(graph): goldens for lifecycle/capability-graph/wavefront overlays"
```

- [ ] **Step 7: Final review** — dispatch a full code-reviewer over the branch diff (`git diff main...lang/execution-semantics`); confirm: spec §4 schema, §5 schedule, §6 invariants (C2 state-machine well-formedness; C3 cap closure), §7 P1/P2/P3 each map to code + a test. Fix any gaps.

---

## Self-Review

**1. Spec coverage:**
- §4 IR schema → Tasks 3 (lifecycle-state/transition + controls/enabled-in/results-in), 4 (grant/holds), 5 (depends-on/level/checkpoint/boundary-for/rewind-to). ✓
- §5 scheduling algorithm → Task 2 (`compute_schedule`). ✓
- §6 invariants: C1 schedule soundness (levels, Task 5) ✓; C2 control validity (Task 6 bad-transition) ✓; C3 capability closure (Task 8) ✓; C4 checkpoint placement (Task 5; rewind-to) ✓; C5 determinism (Task 10 Step 5) ✓.
- §7 P1 (Task 2 cycle/levels), P2 (Task 8 cap refs), P3 (Task 9 oracle). ✓
- §8 checker codes: all four `E-EXEC-*` (Tasks 6,7) + `E-CAP-*` extension (Task 8). ✓
- `delegates` edge (§4): **mesh `route` edges already exist as `routes_to`; explicit `delegates` modeling is deferred** — note for a follow-up; not blocking v0 (no example exercises delegation). Flag in Task 10 review.

**2. Placeholder scan:** Three steps contain a "confirm by reading" instruction (Task 3 Step 4 attribute names; Task 8 signature; Task 10 Step 2 golden flag/filename). These point at exact, named referents in existing files — not vague TODOs — and are cheap to verify; acceptable. No `TBD`/`implement later`.

**3. Type consistency:** `compute_schedule`/`FiberIO`/`Schedule`/`fiber_ios`/`member_names` names are identical across Tasks 2,5,7. `_emit(diags, code, file, span, decl, message)` matches the explored signature. `node_id(basename, chain)` / `GraphNode`/`GraphEdge`/`Provenance`/`Span` match `graph.py`. Edge labels (`controls`/`enabled-in`/`results-in`/`holds`/`depends-on`/`boundary-for`/`rewind-to`) match spec §4 and are used identically in overlay + oracle.

**Gap fixed inline:** `delegates` flagged as deferred above (no v0 example) rather than left as a silent omission.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-14-inline-arp-compiled-execution.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec → quality) between tasks, parallel fan-out across streams A/B/C.
2. **Inline Execution** — execute tasks in this session via executing-plans, batch with checkpoints.
