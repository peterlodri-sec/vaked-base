# RFC 0008 — End-to-End Workflow Orchestration over Litany

- **Status:** Draft
- **Created:** 2026-06-14
- **Track:** Protocol

## Abstract

RFCs 0001–0007 define *what* an HCP message is (`0001`), its schema language
and canonical encoding (`0002`), how bytes are framed on Litany Wire (`0003`),
how consumers durably anchor on producer state (`0004`), the control-plane
verbs that drive a running runtime (`0005`), inter-host identity and
distribution (`0006`), and post-quantum confidentiality (`0007`). What none of
them states is how a **whole declared workflow** — a Vaked `workflow` graph of
agent steps, with budgets and scheduling classes — becomes a *normative
sequence* of Votive Frames on the wire.

This RFC closes that gap. It specifies the **lowering contract** from a Vaked
capability graph (`mesh` + `workflow` + `budget` + `runclass`) to the frames of
RFCs 0004 and 0005, defines the lifecycle of a **workflow run**, and gives a
frame-by-frame worked trace of an end-to-end agentic development loop —
*brainstorm → subagent-driven development → time-boxed deep-research →
PR-babysit*. It is the protocol-layer companion to the language-layer note
[`hcp-litany-dev-loop-design`](../../docs/superpowers/specs/2026-06-14-hcp-litany-dev-loop-design.md)
and to [0015-workflow](../../docs/language/0015-workflow.md), and it advances
WP3 ([#165](https://github.com/peterlodri-sec/vaked-base/issues/165)).

No new wire encoding is introduced. One new control frame (`DeadlineExpiry`) is
*proposed* to make wall-clock budgets enforceable on the wire; until it is
accepted, expiry is realized by a supervisor-initiated `PauseControl` (§5).

## Terminology

Reuses the vocabulary of RFCs 0002–0005 unchanged (Votive Frame, Litany Wire,
`hcpbin`, `DependencyRegistration`, `ConsumerCheckpoint`, `RewindEvent`,
topology epoch, GC floor, `PauseControl`/`ResumeControl`/`StepControl`/
`SetIntervalControl`/`RewindControl`, `control_action`). It adds:

| Term | Meaning |
|------|---------|
| Workflow run | A single end-to-end traversal of a lowered Vaked `workflow`, instantiated by `agent-supervisord` under one topology epoch. The DAG is static; a run is one execution of it. |
| Step activation | The supervisor admitting a workflow step to `RUNNING`, after its inbound `DependencyRegistration`s are logged and cold-start anchor verification (0004 §6) passes. |
| Lowering contract | The normative correspondence (this RFC, §2) between a Vaked construct and the frame(s) / mechanism that realize it on Litany. |
| `DeadlineExpiry` | *Proposed* (§5) event frame, recorded to `eventd`, marking a step's wall-clock budget exhausted — the missing dual of a declared `budget.wallClock`. |

## 1. Scope and relationship to the series

`vakedc lower` already emits, for a runtime, a `gen/workflow/<name>.json`
artifact bound to a hash-chained `eventd` log. That artifact is the *static*
graph. This RFC governs its *dynamic* realization: which frames `agent-supervisord`
exchanges to execute it, and the invariants those frames must uphold.

- Authority (mesh `operator -> X` delegations) is **not** a wire concern: it is
  checked at compile time (0011 §4.4) and never travels as a frame.
- Ordering (workflow edges `a -> b`) **is** a wire concern: each edge lowers to
  a state-dependency anchor (RFC 0004).
- Bounds and scheduling (`budget`, `runclass`) lower to control-plane frames
  (RFC 0005), with one declared bound (`wallClock`) currently lacking a wire
  dual — see §5.

A workflow run is scoped to a chapter (RFC 0003 §session); its frames carry the
run's `topology_epoch` so that a mid-run topology change fences cleanly (0004 §7).

## 2. The lowering contract (normative)

For a lowered `workflow`, an implementation MUST realize each construct as
follows. This is the protocol-binding form of the language-layer mapping table.

| Vaked construct | Lowers to | RFC |
|---|---|---|
| workflow edge `a -> b` | `DependencyRegistration` — consumer `b` write-ahead pins producer `a`'s `{step, hash, topology_epoch}` **before** consuming | 0004 §3 |
| step `input = artifacts.X` folded | `ConsumerCheckpoint{ min_required_step }` after the input is committed into `b`'s state | 0004 §4 |
| step `output` produced + committed | a producer step appended to `eventd`; pinned by downstream `ConsumerCheckpoint.min_required_step` | 0004 §4 |
| `runclass.<c>.interval = T` on a step | `SetIntervalControl{ interval_ms: T }` on that step's target | 0005 §1, §4.3 |
| `budget.<b>.wallClock = D` expiry | `DeadlineExpiry` (proposed, §5) → `PauseControl`; today: supervisor-initiated `PauseControl` | 0005 §2.1 |
| operator resumes a paused step | `ResumeControl` | 0005 §1 |
| single-tick inspection of a paused step | `StepControl` (one tick, returns to paused) | 0005 §2.2 |
| undo a bad step output | `RewindControl` (req) → supervisor composes `RewindEvent` | 0005 §3 / 0004 §3.3 |
| `budget.approvals = "never"` | `preceptord` policy denies any approval-soliciting frame; none are emitted | 0005 §2.3 |
| mesh delegation `operator -> X` | *(none — compile-time attenuation)* | 0011 §4.4 |
| build-time mesh+workflow topology | `topology_epoch` stamped on every dependency artifact and control frame | 0004 §7 |

**Write-ahead rule (normative).** Every `DependencyRegistration` MUST be logged
to `eventd` before the consuming fetch; every applied control frame MUST be
logged as `control_action` before its effect (0005). A run that consumes before
registering, or effects before logging, is non-conformant.

## 3. Workflow run lifecycle

1. **Instantiation.** `agent-supervisord` reads `gen/workflow/<name>.json`,
   stamps the current `topology_epoch`, and opens a chapter.
2. **Step activation.** A step becomes `RUNNING` only after (a) all inbound edge
   `DependencyRegistration`s are logged, and (b) cold-start anchor verification
   (0004 §6) confirms each pinned producer `{step, hash}` is live (not rewound,
   not below the GC floor). Otherwise the step parks `PAUSED(stale_dependency)`.
3. **Production.** On completing work, the step appends its `output` step to
   `eventd` and emits the downstream `ConsumerCheckpoint`(s).
4. **Completion.** The run completes when the DAG's sink steps have committed.
   `maxDepth` bounds the critical path (`E-WORKFLOW-DEPTH`, checked at compile
   time) so a run's frame sequence is finite by construction.

A run carries no cycles: `retries` and `runclass.interval` re-enter the *same*
step in place (§6, §7); neither is a back-edge (which would trip
`E-WORKFLOW-CYCLE`).

## 4. Worked end-to-end trace

The dev loop `brainstorm -> implement -> research -> babysit`
([`hcp-litany-dev-loop.vaked`](../../vaked/examples/hcp-litany-dev-loop.vaked)),
one run, abbreviated to the load-bearing frames. `E = topology_epoch`.

```text
# brainstorm (producer of artifacts.ideas)
→ brainstorm appends step b@1 to eventd                       (output committed)

# implement consumes brainstorm
→ DependencyRegistration{ consumer: implement, producer: brainstorm,
                          producer_step: 1, producer_step_hash: H(b@1), epoch: E }   (RFC 0004 §3)
   … cold-start verify H(b@1) live → implement RUNNING                              (§3.2)
→ implement appends step i@1 (artifacts.patch)
→ ConsumerCheckpoint{ consumer: implement, producer: brainstorm, min_required_step: 1 }

# research is time-boxed (budget.research.wallClock = 15m)
→ DependencyRegistration{ consumer: research, producer: implement, step: 1, … }
→ research RUNNING
   … 15m wall-clock elapses with no commit …
→ DeadlineExpiry{ target: research, epoch: E }      (proposed §5; today: supervisor PauseControl)
→ PauseControl{ scope: agent, target: research, epoch: E } → ControlAck{ applied: true }

# babysit recurs every 2m (runclass.babysit_loop.interval = 2m), retries ≤ 30
→ SetIntervalControl{ target: babysit, interval_ms: 120000, epoch: E } → ControlAck
→ DependencyRegistration{ consumer: babysit, producer: research, step: 1, … }
   tick 1: cold-start verify → RUNNING → resolve conflicts, push → CI red → no green
   tick 2: cold-start verify → RUNNING → push → CI green → commit babysit@1
→ ConsumerCheckpoint{ consumer: babysit, producer: research, min_required_step: 1 }
   # budget.babysit.approvals = "never": no approval frame is ever emitted (preceptord denies)
```

If a babysit tick must undo a bad merge:

```text
→ RewindControl{ producer: babysit, rewind_to_step: N, rewind_to_hash: H, epoch: E }
→ RewindEvent{ producer: babysit, rewind_to_step: N, … }   (downstream re-verify, 0004 §3.3)
```

## 5. Time-boxed steps and the deadline gap

A `budget.wallClock = D` on a step declares a wall-clock cap. RFC 0005 has verbs
to *pause* a step but no frame that means **"this step's deadline is reached."**
Two conformance levels:

- **Level 0 (today, REQUIRED).** The supervisor tracks the step's wall clock and,
  on expiry, emits a `PauseControl` against the step. The pause is logged as
  `control_action`; the cause (budget expiry vs. operator action) is *not*
  distinguishable on the wire.
- **Level 1 (proposed, OPTIONAL until accepted).** A new event frame
  `DeadlineExpiry{ target, epoch, budget_kind, limit }` is appended to `eventd`
  *before* the consequent `PauseControl`, making the cause first-class and
  auditable. This requires a coordinated addition to RFC 0005's frame catalog;
  this RFC does not modify 0005 unilaterally (see Open questions).

Implementations MUST achieve Level 0. Level 1 is the recommended target once the
frame is ratified.

## 6. Recurring steps

`runclass.<c>.interval = T` makes a step recur. Per the convergent industry
idiom (Temporal Schedules, Argo `CronWorkflow`, Dagster `@schedule`, Step
Functions/EventBridge, GitHub `cron`), recurrence is a **scheduling property**,
not graph topology: the step appears in the DAG exactly once, and the supervisor
re-enters it each tick via `SetIntervalControl`. Each tick is a fresh step
activation (§3.2) and therefore re-runs cold-start anchor verification — so a
recurring step is *safe to restart*: it parks `PAUSED(stale_dependency)` rather
than acting on a rewound or compacted producer.

## 7. Bounded revision loops

`retries = N` on a step bounds in-place re-execution (e.g. conflict → push → CI
→ retry). It is **not** a back-edge. When a step also recurs (`interval`),
`retries` bounds revisions *within* a tick and the interval bounds ticks; an
implementation SHOULD additionally bound the step by `budget.wallClock` so a
flaky step cannot exhaust the run budget (Temporal's attempt-cap-plus-deadline
pattern). The total work of a step is therefore bounded by
`min(retries × per-attempt, wallClock)` per tick.

## 8. Authority and the no-comment property

`budget.approvals = "never"` lowers to a `preceptord` policy that denies any
approval-soliciting frame from the step's principal; conformantly, none are
emitted. Separately, the mesh attenuates `mcp.github_write` to exactly the
publish chokepoint (`babysitter`/`operator`). Note the current `mcp` grant
lattice (`none < github_read < github_write < broker_admin`) is too coarse to
*prove* "merge yes, comment no" — that property rests on broker policy, not on a
compile-time capability proof (Open questions).

## Security considerations

- **Write-ahead or it didn't happen.** Both dependency anchors and control
  effects are logged before effect; replay of the `eventd` chain reconstructs the
  exact run, and any byte-level tampering breaks the hash chain (RFC 0001).
- **Epoch fencing.** Every run frame carries `topology_epoch`; a stale-epoch
  frame is refused (`ControlRefusal.stale_epoch`, 0005), so a topology change can
  never silently re-bind a step to the wrong producer.
- **Cold-start before RUNNING.** No step acts on unverified producer state; a
  rewound or GC'd dependency parks the consumer rather than corrupting it.
- **Least authority per step.** Each step runs under its mesh node's attenuated
  grant; `preceptord` evaluates authority per frame, per target. A compromised
  step cannot exceed its delegated capabilities.

## Open questions

1. **Ratify `DeadlineExpiry` (§5).** Add it to RFC 0005's catalog as a first-class
   event, or keep budget expiry indistinguishable from operator pause? A
   coordinated 0005 revision (not a silent rewrite) is required either way.
2. **Do `retries` and `interval` compose by spec or by convention (§7)?** The
   `min(retries×attempt, wallClock)` bound should be normative if relied upon.
3. **Finer `mcp` capability lattice (§8).** Split `github_write` into
   `github_merge` vs. `github_comment` so the checker can *prove* the no-comment
   property — a capability-taxonomy follow-up (relates to grammar/schema, not the
   wire).
4. **`runclass` lowering.** `vakedc lower` carries `budget` into the workflow
   artifact but not yet `runclass` (OTP `SupFlags`/worker-arg wiring is the
   tracked follow-up, #28); until then `SetIntervalControl` is *declared and
   checked* but not *emitted*.
5. **Conflict-avoidance as a distinct axis.** GitHub-style `concurrency`
   (avoidance) differs from `retries` (recovery); whether Vaked needs a separate
   scheduling axis for it is unresolved.
</content>
