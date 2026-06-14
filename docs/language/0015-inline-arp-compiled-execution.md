# 0015 — Inline ARP: compiled-parallelized execution over the typed semantic graph

## §1 Status

Seed draft. Grammar: v0.4 — **no new grammar**; this note reuses `lifecycle_decl`
(0013) and the `capability` kind (0014). vakedc parser: `lifecycle` complete
(0013); no parser change. `graph.py`: **not started** — the execution overlay
specified here is new IR-construction work. `check.py`: capability validation
partial (0014); execution validation not started. Emitters (OTP, inline-compiled):
**deferred to per-projection specs**; this note defines only the IR model and the
contract those projections must honor.

## §2 Summary

The typed semantic graph is the single source of truth for parallel execution.
From the resolved declarations vakedc computes a **static parallel schedule**
(dependency DAG → wavefronts), materializes the **ARP control structure**
(lifecycle states / transitions / checkpoints, from 0013's parsed `lifecycle`
blocks) and the **capability closure** (0014) as first-class nodes and edges in
the existing Labeled Property Graph, then **two projections** consume that one
graph:

- **OTP projection** — a supervised BEAM process tree (0013's model).
- **Inline-compiled projection** — a statically scheduled, in-process executor
  ("inline / bare-metal"): one address space, no supervisor, no wire.

Execution is decided at compile time ("compiled-parallelized"). The same source
yields the same schedule, and both projections are **proved equivalent** in
observable control behavior (§7). This is the dual-projection thesis: *schedule
once, project twice, prove equal.*

## §3 Concepts

### Traversable execution = graph traversal

ARP control — the pause / resume / stop / rewind events of 0013 — is realized as
walkable graph structure, not interpreted state. A consumer at a `lifecycle-state` node finds the
`transition` nodes `enabled-in` that state, fires one, and follows `results-in` to
the next state. "What can fiber X do now?" and "what capabilities does X hold?" are
both pure traversals of the IR.

### Wavefront schedule

Within a `parallel` group, fibers form a dependency DAG (A depends on B when A's
`input` consumes B's `output` or a shared artifact). Topological **levels** define
**wavefronts**: all fibers at one level may run concurrently; level *k* begins only
after level *k−1*'s **checkpoint**. Checkpoints are the canonical halt / snapshot /
rewind points.

### Dual projection

The graph is substrate-independent. OTP and inline-compiled differ only in (a)
execution substrate (BEAM processes vs. one address space) and (b) optimization
(the inline projection may fuse intra-wavefront fibers). They do not differ in
*which* control points exist, *which* capabilities each entity holds, or the fiber
start ordering — that is the equivalence guarantee (§6, proved §7).

## §4 IR schema (`graph.py`)

Reuses the existing `GraphNode{id,kind,name,labels,props,provenance}` and
`GraphEdge{source,target,label,props}` — no new dataclasses. Synthetic nodes get
deterministic path-derived ids (so `nodes_sorted` / `edges_sorted` determinism
holds) and provenance pointing at the originating decl or `on`-clause span.

### New node kinds

| kind | one per | id | key props |
|------|---------|-----|-----------|
| `lifecycle-state` | controllable-entity state | `…#<entity>/state:<running\|paused\|stopped>` | `{terminal}` |
| `transition` | each `lifecycle` `on`-clause | `…#<entity>/transition:<event>` | `{event}` + on-clause record |
| `checkpoint` | wavefront boundary | `…#<parallel>/checkpoint:<level>` | `{level, rewindable}` |
| `grant` | each grant in a `capability` domain | `…#<domain>/grant:<name>` | `{}` |

### New edge labels

| label | from → to | meaning |
|-------|-----------|---------|
| `controls` | entity → transition | entity exposes this control point |
| `enabled-in` | transition → lifecycle-state | valid source state |
| `results-in` | transition → lifecycle-state | target state |
| `cascades-to` | entity → fiber | control cascades to child (0013) |
| `depends-on` | fiber → fiber | dependency DAG; props `{via}` |
| `boundary-for` | checkpoint → fiber | fibers the checkpoint follows |
| `rewind-to` | transition(rewind) → checkpoint | rollback target |
| `holds` | entity → grant | resolved capability (0014) |
| `delegates` | entity → entity | props `{grants}` |

### New props on existing fiber nodes

`level:int` (wavefront index), `fusion_group:str|null` (fusion hint;
the fusion itself is an emitter decision, not IR structure).

## §5 Scheduling algorithm

`compute_schedule(parallel_group) -> Schedule` is a **pure function** of the
resolved AST:

1. Collect member fibers from the group's `fibers = [...]` list.
2. Build the dependency relation: `depends-on` A→B when A's `input` references B's
   `output` or a shared artifact/stream B produces.
3. Detect cycles → hard error `E-EXEC-CYCLE` (a supervised DAG is acyclic).
4. Assign levels by longest path: `level(f) = 0` if f has no in-group dependency,
   else `1 + max(level(deps))`.
5. Wavefront *k* = `{ f : level(f) == k }`. Insert a `checkpoint` after each
   wavefront, with `boundary-for` edges to that wavefront's fibers.
6. `rewindable = true` iff every stream crossing the boundary declares `retention`
   (0013 rewind precondition); else `false`. Any `on rewind` transition gets a
   `rewind-to` edge to the nearest rewindable checkpoint, or triggers
   `E-EXEC-REWIND-NO-RETENTION`.

**Scope (v0):** dependencies are computed *within* a parallel group. Cross-group
scheduling is deferred. Determinism: fibers within a wavefront are ordered by node
id; checkpoints by level (§10).

## §6 Projection contract

Both projections consume one scheduled, checkpointed, capability-closed graph.

**Invariants (machine-checked; projections may assume them):**

- **C1 Schedule soundness** — no fiber starts before all its `depends-on` targets
  complete; wavefront *k* runs only after *k−1*'s checkpoint.
- **C2 Control validity** — every `transition` has exactly one `enabled-in` and one
  `results-in`; the state machine is reachable from `running`.
- **C3 Capability closure** — every `holds` resolves to a declared `grant`; every
  `delegates` satisfies the attenuation order (0014 zero-proof).
- **C4 Checkpoint placement** — checkpoints occur only at wavefront boundaries;
  every `rewind-to` targets a `rewindable` checkpoint.
- **C5 Determinism** — the graph is a pure function of source (0012 §6).

**Per-projection obligations:**

| | OTP projection | Inline-compiled projection |
|---|---|---|
| Wavefront | supervised process group | static schedule, one address space |
| `transition` | OTP lifecycle callback (`handle_pause/2`, …; 0013 §5) | in-process control hook |
| Control transport | MAY cross Litany Wire (RFC 0003 §6 chapter lifecycle) | in-process; **no wire** |
| `holds` set | process capability metadata | eBPF allow-list per fiber (0014 §5) |
| Fusion | not applied | MAY fuse intra-wavefront fibers with no checkpoint between |

**Equivalence guarantee:** for the same source, both projections exhibit the same
control-trace alphabet (reachable state/transition/checkpoint tuples), the same
per-fiber capability set, and the same fiber-start partial order. They differ only
in substrate and fusion. `rewind` structure is present in both; `rewind` execution
is deferred in both for v0.

## §7 Verification & proof

The design is only as strong as its proofs. Three obligations, each **executable**
— the proof is a clean `vakedc check` plus a green suite, with no separate proof
artifact (the "zero-proof" stance of 0014, generalized from capability to
execution).

- **P1 Schedule validity.** The dependency relation is acyclic (`E-EXEC-CYCLE`
  guards it) and level assignment is monotone: for every `depends-on` edge A→B,
  `level(A) > level(B)`. Monotonicity holds by construction (step 4); a
  property-based test asserts it over generated DAGs. *Proves C1.*
- **P2 Capability containment.** If `vakedc check` exits 0, every `holds` resolves
  and every `delegates` respects attenuation — so no runtime access to an
  undeclared grant is representable. The check result **is** the certificate.
  This note extends 0014's mesh-only checks to fiber `policy` and surface `input`
  contexts. *Proves C3.*
- **P3 Projection equivalence.** Define a projection-independent oracle
  `expected_behavior(graph)` = (control-trace alphabet, per-fiber capability sets,
  fiber-start partial order), computed directly from the IR. The equivalence claim
  is: each projection, driven from the same graph, reproduces `expected_behavior`
  exactly. For v0 (emitters deferred) the oracle and a reference golden are
  produced now; each future emitter spec inherits a conformance test that must
  match the oracle. *Proves the §6 equivalence guarantee.*

**Publication framing (v1.0 / arXiv):** the central claim is that a single typed
semantic graph is simultaneously (i) a compile-time capability-containment
certificate and (ii) a multi-projection parallel-execution schedule whose
projections are proved behaviorally equivalent. P1–P3 are the formal core; the
test suite is the machine-checked evidence.

## §8 Checker rules (`check.py`)

`compute_schedule` (§5) is shared: `check.py` (stage 4) calls it for diagnostics;
`graph.py` (stage 5) calls it for materialization — one implementation, no
duplication, `check.py` remains the diagnostic owner.

New error codes:

| code | condition |
|------|-----------|
| `E-EXEC-CYCLE` | dependency cycle within a parallel group (C1) |
| `E-EXEC-LIFECYCLE-CONTEXT` | `lifecycle` block outside `parallel` / `fiber` (0013 §4) |
| `E-EXEC-BAD-TRANSITION` | malformed control state machine (C2) |
| `E-EXEC-REWIND-NO-RETENTION` | `on rewind` with no rewindable checkpoint (0013 §3) |

Plus: extend the existing `E-CAP-UNKNOWN-DOMAIN` / `E-CAP-UNKNOWN-GRANT` /
`E-CAP-ATTENUATION` ref-validation from mesh contexts to fiber `policy` and surface
`input` (0014 §7 v0 item).

## §9 Output-first

| Projection | Artifact | Status |
|---|---|---|
| OTP | supervisor/worker modules + lifecycle callbacks | deferred (0013 §5 + OTP emitter spec) |
| Inline-compiled | Zig in-process executor + static schedule | deferred (inline-emitter spec) |
| Capability | `capabilities.json`, eBPF manifests, `RUNTIME.md` matrix | deferred (0014 §5) |
| Docs | wavefront + lifecycle + capability tables in `RUNTIME.md` | deferred |

This note produces **no emitter code**. It produces the IR overlay, the checker
rules, and the verification oracle that the emitter specs build on.

## §10 Determinism

`compute_schedule`, the overlay construction, and the capability closure are pure
functions of the typed semantic graph — no I/O, no environment reads. Synthetic
node ids are path-derived; ordering reuses `nodes_sorted` / `edges_sorted`. Same
source ⇒ same overlay ⇒ same `expected_behavior`. Upholds the 0012 §6 determinism
invariant.

## §11 v0 boundary

| Feature | v0 | Notes |
|---|---|---|
| Dependency DAG + levels in IR | **yes** | within-group only |
| Lifecycle states/transitions in IR | **yes** | from 0013's parsed `lifecycle` |
| Checkpoints (structure) | **yes** | wavefront boundaries |
| Capability closure in IR | **yes** | extends 0014 to fiber/surface |
| Verification oracle `expected_behavior` + golden | **yes** | P3 reference |
| `rewind` execution | **post-v0** | structure only; needs stream snapshots (0013 §7) |
| Fiber fusion | **post-v0** | IR carries `fusion_group` hint only |
| OTP / inline-compiled emitters | **post-v0** | separate specs |
| Cross-group scheduling | **post-v0** | |
| Litany Wire control integration | **post-v0** | RFC 0003 §6 |

## §12 References

- 0008 — parallel / fibers / indexes / surfaces
- 0011 — type system (`Device`, `MediaPipeline` kinds)
- 0012 — lowering (emitters, determinism §6)
- 0013 — traversable execution (`lifecycle` block, control events)
- 0014 — typed capability graph (zero-proof containment)
- RFC 0003 — Litany Wire (chapter lifecycle §6, determinism/replay §10)
