# Design note — the agentic dev loop, expressed grammatically (HCP/Litany)

Date: 2026-06-14 · Tracks issue [#165](https://github.com/peterlodri-sec/vaked-base/issues/165) (WP3 HCP wire protocol) · Artifact: [`vaked/examples/hcp-litany-dev-loop.vaked`](../../../vaked/examples/hcp-litany-dev-loop.vaked)

## Context

We drive development through a repeatable chain of agent activities:

> **brainstorm → subagent-driven development → deep-research (≤15 min) → PR-babysit (every ~2 min: resolve conflicts, drive CI to all-green, post no comments).**

The open question from the request was: *"the wire — HCP and Litany — is a bit on a different layer, but it would be ideal if we could express something like this grammatically."* This note shows that we **can** — using only existing Vaked constructs (no new grammar) — and documents exactly how each construct **lowers onto** the HCP/Litany protocol layer (RFCs 0001–0007). The companion artifact parses, type-checks, and lowers cleanly through `vakedc` (see [Verification](#verification)).

## The two-graph discipline

The dev loop is expressed with the same spine as `agentfield-swe.vaked`, per [0015-workflow](../../language/0015-workflow.md):

- **`mesh field`** — the *authority* axis. Agents are declared once with attenuated capabilities; `operator -> X` edges are delegations checked under POLA (0011 §4.4).
- **`workflow dev_loop`** — the *ordering* axis. Steps are a checked DAG (`E-WORKFLOW-CYCLE`, `E-WORKFLOW-DEPTH`); each step names its executing mesh agent and threads typed artifacts forward.
- **`budget` / `runclass`** — *bounds* and *scheduling* threaded onto individual steps.

## How the three request constraints map to grammar

| Request phrase | Vaked construct | Why this construct |
|---|---|---|
| "deep-research, **max 15 min**" | `budget research { wallClock = 15m }` on the `research` step | A time-box is a per-step resource bound, not a graph node. |
| "pr-babysit, **every 2 min**" | `runclass babysit_loop { interval = 2m }` on the `babysit` step | Recurrence is a *scheduling-class* property; the step appears in the DAG exactly once. |
| "**resolve conflicts** / drive green" | `retries = 30` on the `babysit` step | A bounded revision loop — explicitly *not* a back-edge (a `babysit -> babysit` edge would trip `E-WORKFLOW-CYCLE`). |
| "**no comments** on the PR" | `budget babysit { approvals = "never" }` | Encodes the autonomous stance: the babysit step prompts for nothing. |

## The mesh (capability separation)

Static, compile-time guarantees from attenuated delegation:

| node | role | capabilities | guarantee |
|---|---|---|---|
| `operator` | control-plane | `fs.repo_rw, process.spawn, mcp.github_write, mem.admin, network.egress` | holds the maximal grant in each delegated domain so every edge attenuates |
| `brainstormer` | brainstorm | `fs.repo_ro, mem.recall` | reads only; cannot mutate or reach the network |
| `implementer` | implement | `fs.repo_rw, process.spawn_sandboxed, mem.recall` | the only writer of code; **cannot** self-publish (no `mcp.github_write`) |
| `researcher` | deep-research | `fs.repo_ro, network.egress, mem.append` | the **only** node that reaches the internet; cannot touch code or ship |
| `babysitter` | pr-babysit | `fs.repo_rw, mcp.github_write, mem.recall` | resolves conflicts and merges; the publish chokepoint |

Note the attenuation consequence: because `researcher` needs `network.egress`, the `operator` must also hold `network.egress` (delegation only flows to `≤` in each domain). This is the one capability the canonical `agentfield-swe.vaked` did not need.

## HCP / Litany lowering map

The wire protocol is a lower layer; the workflow **lowers onto** it. Concretely, `vakedc lower` already emits `gen/workflow/dev_loop.json` bound to an append-only `eventd` log (`var/lib/hcp-litany-dev-loop/eventd/log.jsonl`) — the same hash-chained substrate the protocol's state-dependency layer rides on. The construct → frame correspondence:

| Vaked construct | Lowers to (frame / mechanism) | RFC |
|---|---|---|
| workflow edge `a -> b` (ordering) | `DependencyRegistration` — consumer `b` write-ahead pins producer `a`'s step+hash+epoch | 0004 §3 |
| step `input = artifacts.X` consumed | `DependencyRegistration` before fetch; `ConsumerCheckpoint` after fold | 0004 §3–4 |
| step `output` produced + committed | producer step on `eventd`; pinned by downstream `ConsumerCheckpoint.min_required_step` | 0004 §4 |
| `runclass.babysit_loop.interval = 2m` | `SetIntervalControl{ interval_ms: 120000 }` on the babysit target | 0005 §1, §4.3 |
| `budget.research.wallClock = 15m` expiry | supervisor-initiated `PauseControl` on the research target when the wall-clock budget is spent | 0005 §2.1 |
| operator resumes a paused step | `ResumeControl` | 0005 §1 |
| single-tick debugging of a paused step | `StepControl` (one tick, returns to paused) | 0005 §2.2 |
| babysit needs to undo a bad merge | `RewindControl` (req) → supervisor composes `RewindEvent` | 0005 §3 / 0004 §3.3 |
| `budget.approvals = "never"` (no comments) | `preceptord` policy + broker autonomy; no approval frames emitted | 0005 §2.3 |
| mesh delegation `operator -> X` | **not** a wire frame — attenuation checked at compile time | 0011 §4.4 |
| build-time mesh+workflow topology | `topology_epoch` stamped on every dependency artifact | 0004 §7 |

Every frame above is a **Votive Frame** carried over **Litany Wire** (RFC 0003) in canonical `hcpbin` (RFC 0002). The recurring babysit step is *safe to restart* because of RFC 0004 §6 cold-start: each cycle re-verifies its anchor on `artifacts.findings` before going RUNNING, and parks `PAUSED(stale_dependency)` rather than driving CI against a rewound/compacted producer.

## Open design tensions (honest gaps)

1. **Recurrence is invisible in the static graph.** `babysit` appears once; its repetition lives in the supervisor tick + `SetIntervalControl`, not in the DAG. Correct, but counter-intuitive. Adding a back-edge would (rightly) fail the cycle check.
2. **`retries` only approximates an open-ended loop.** PR-babysitting is genuinely open-ended (conflict → push → CI → maybe new conflict). The truer model is interval-driven re-entry where each tick is a fresh attempt and `retries` bounds in-tick revision; whether `retries` and `interval` *compose* (revisions-per-tick × ticks-until-green) deserves a decision.
3. **`wallClock` has no first-class expiry frame.** The 15-min cap is a declared budget, but RFC 0005 has no "deadline reached" frame — expiry is realized as a supervisor `PauseControl`. There is a gap between *declaring* a wall-clock budget and a wire mechanism that *enforces* it.
4. **"No comments" is a policy, not a graph property.** Vaked can attenuate `mcp.github_write` but the `mcp` domain (`none < github_read < github_write < broker_admin`) is too coarse to say "merge yes, comment no". A finer grant (`mcp.github_merge` vs `mcp.github_comment`) would let the checker *prove* the no-comment property instead of leaving it to broker policy. Candidate follow-up capability-taxonomy refinement.
5. **`runclass` lowering is a #28 follow-up.** `vakedc lower` currently carries `budget` into `gen/workflow/dev_loop.json` but not `runclass` (OTP-supervision wiring of worker args + `SupFlags` is the documented follow-up in `builtins.vaked`). So the 2-min interval is declared and checked today, but not yet emitted — tracked alongside #28.

## Prior art

Industry orchestration DSLs validate the modeling choices — time-box as a per-step *timeout property*, recurrence as a *scheduling property* separate from the step graph, and bounded *retry policies* for conflict loops. A time-boxed deep-research pass surveyed six systems:

| System | Time-box (wall-clock cap) | Recurrence (interval) | Retry / conflict-loop |
|---|---|---|---|
| **Temporal** | `StartToCloseTimeout` per activity; `WorkflowRunTimeout` per run | Schedules (external) + `ContinueAsNew` | `RetryPolicy` w/ `MaximumAttempts`, backoff |
| **Argo Workflows** | `activeDeadlineSeconds` | `CronWorkflow` (separate resource kind) | `retryStrategy` w/ `limit`, `backoff` |
| **Dagster** | `max_runtime` tag / `run_monitoring` | `@schedule` (cron), `@sensor` — separate objects | `RetryPolicy(max_retries=…)` |
| **AWS Step Functions** | `TimeoutSeconds` per state; `Wait` for delays | EventBridge Scheduler (external) | `Retry` (`MaxAttempts`, `BackoffRate`) + `Catch` |
| **GitHub Actions** | `timeout-minutes` per job/step | `on: schedule: cron` trigger | no native step-retry; `concurrency` for conflict avoidance |
| **BPMN** | timer boundary event on an activity | timer `timeCycle` event node | sequence-flow back-edge through a gateway |

**Convergent idiom (Temporal, Argo, Dagster, Step Functions, GitHub Actions).** Recurrence is a first-class scheduling object *separate* from the step graph (Argo's `CronWorkflow` is a distinct resource that instantiates a `Workflow`; Dagster `@schedule` targets a job; GitHub's `cron` is a trigger header) — the recurring step appears in the graph **once** and the scheduler re-instantiates it. Time-boxes are *scalar attributes hung on a step* (`StartToCloseTimeout`, `activeDeadlineSeconds`, `TimeoutSeconds`, `timeout-minutes`) — not nodes. Retry loops are bounded by an *attempt cap plus backoff* (`MaximumAttempts`, `retryStrategy.limit`, `MaxAttempts`), re-executing the same node in place rather than threading a back-edge. This is exactly the Vaked tri-axis: time-box → `budget.wallClock`, recurrence → `runclass.interval` (one DAG appearance), conflict-loop → step `retries`.

**Counter-evidence — BPMN** is the genuine dissent: it models all three as graph topology (retry = sequence-flow back-edge through a gateway; time-box = boundary timer event attached to an activity; recurrence = `timeCycle` timer node). BPMN's lineage is visual process modeling / temporal-logic verification, where time as a first-class graph citizen is the point. It is a coherent road Vaked consciously *does not* take. (Minor wrinkles: Step Functions `Map`/`Wait` *are* graph states, but `Map` is bounded fan-out over a known list and `Wait` is sequencing, not a cap; GitHub `concurrency` is conflict *avoidance*, a distinct axis from retry.)

**Recommended refinement (Temporal's pattern):** bound `retries` by *both* attempt count and `budget.wallClock`, so a flaky babysit step can't burn the whole run budget — which the artifact already does (`budget babysit { wallClock = 5m }` + `retries = 30`). Separately, conflict-*avoidance* (à la GitHub `concurrency`) may deserve an axis distinct from retry; noted as future work.

Selected sources: Temporal [retry-policies](https://docs.temporal.io/encyclopedia/retry-policies) · Argo [Cron Workflows](https://argo-workflows.readthedocs.io/en/latest/cron-workflows/) · Dagster [run-retries](https://docs.dagster.io/deployment/execution/run-retries) · Step Functions [error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html) · GitHub Actions [workflow syntax](https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions) · BPMN [Camunda timer events](https://docs.camunda.io/docs/components/modeler/bpmn/timer-events/).

## Verification

```
$ python3 -m vakedc check vaked/examples/hcp-litany-dev-loop.vaked
vakedc: vaked/examples/hcp-litany-dev-loop.vaked — no diagnostics   # exit 0

$ python3 -m vakedc lower vaked/examples/hcp-litany-dev-loop.vaked --out /tmp/devloop-out
vakedc: lowered … → /tmp/devloop-out (5 files)                       # exit 0
#   flake.nix · gen/RUNTIME.md · gen/eventd.json · gen/workflow/dev_loop.json · provenance.json
```

`gen/workflow/dev_loop.json` shows the 4-step DAG, `depth = 4 ≤ maxDepth = 6`, and the `eventd` log binding — i.e. the dev loop is a typed, checked, lowerable capability graph that sits directly on the HCP/Litany evidence substrate.
