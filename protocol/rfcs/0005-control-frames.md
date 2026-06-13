# RFC 0005 — Control-Plane Frames (pause / resume / slow / step / rewind)

- **Status:** Draft
- **Created:** 2026-06-12
- **Track:** Protocol
- **Numbering note:** design sessions *prior to* 2026-06-12 used "RFC 0005"
  as a working label for the multi-agent state-dependency RFC — that is
  [RFC 0004](./0004-multi-agent-state-dependency.md) (see its alias note).
  This RFC is unrelated to that label.

## Abstract

This RFC catalogs the frames through which an operator (or a supervising
driver) exercises the Track D verbs — pause, resume, slow, step, rewind —
against a running Vaked runtime
([control-plane design](../../docs/superpowers/specs/2026-06-12-control-plane-design.md),
epic #17 acceptance 3; the design's "stop" verb is realized as the
pause/resume pair). The frames are Votive Frames of class **`request`**
(RFC 0002 §4.3 binds `call` to request/response; the `control` Votive class
remains connection/session lifecycle — "control plane" here names the
*destination*, `agent-supervisord`
([runtime roster](../../docs/runtime/README.md)), not the frame class).
Authority is a `preceptord` policy decision, and **every applied control
action is itself an eventd entry**, so replaying the log reproduces the
operator's time travel along with everything else. A `RewindControl` frame
*requests* a rewind — the supervisor *performs* it by composing RFC 0004
machinery; this RFC never introduces a second rewind mechanism.

## Terminology

| Term | Definition |
|------|------------|
| Control-plane frame | A `request` frame addressed to the supervision plane (this catalog). |
| Scope | What a verb applies to: `runtime` (the whole OTP tree) or `agent` (one supervisor child). |
| Target | The **declared name** (supervisor child id, or the runtime's name) the verb applies to, resolved against the current topology epoch (§2.4). |
| `ControlAck` | The response frame: applied, or refused with a typed `ControlRefusal` reason. |
| `control_action` | The eventd payload kind recording an **applied** control frame (§3). |
| Step | One-shot: run a single tick while paused, then remain paused (the ralph `Control.step` semantics, promoted). |

Shared vocabulary lives in [`docs/protocol/README.md`](../../docs/protocol/README.md);
the rewind machinery is [RFC 0004](./0004-multi-agent-state-dependency.md) §3.3/§6.

## 1. Frame catalog (`.hcplang`)

Header fields (kind/corr/stream/seq/end) are implicit; tags begin at `@1`.

```hcplang
schema hcp.control {
  version = "0.1.0"

  /// Case 0 is the canonical omitted default (RFC 0002 §6.3) and is REFUSED:
  /// the widest blast radius must never be reachable by omission.
  enum ControlScope {
    unspecified = 0,
    runtime     = 1,
    agent       = 2,
  }

  /// Typed refusal reasons — no stringly-typed switching (cf. ErrorKind).
  enum ControlRefusal {
    unspecified      = 0,
    denied           = 1,   # preceptord refused the principal
    unknown_target   = 2,   # name does not resolve in the current epoch
    stale_epoch      = 3,   # topology_epoch is not the current epoch
    not_paused       = 4,   # step on a non-paused target (no-op)
    invalid_interval = 5,   # interval_ms = 0 (the omitted-field default)
  }

  /// Pause scheduling for the target (workers keep state; no ticks run).
  frame PauseControl request {
    scope:          ControlScope  @1
    target:         string        @2
    topology_epoch: u64           @3   # epoch fence (§2.4)
    reason:         string?       @4
  }

  /// Resume normal scheduling for the target.
  frame ResumeControl request {
    scope:          ControlScope  @1
    target:         string        @2
    topology_epoch: u64           @3
  }

  /// Slow: set the target's tick interval (the ralph `interval` semantics).
  frame SetIntervalControl request {
    scope:          ControlScope  @1
    target:         string        @2
    topology_epoch: u64           @3
    interval_ms:    u32           @4   # 0 is refused (invalid_interval)
  }

  /// One-shot step while paused; the target stays paused afterwards.
  frame StepControl request {
    scope:          ControlScope  @1
    target:         string        @2
    topology_epoch: u64           @3
  }

  /// REQUEST a producer rewind. The supervisor performs it per RFC 0004 and
  /// §2.2 below. Highest authority. `producer` is the AgentId (uuid),
  /// matching RewindEvent exactly; name→AgentId resolution is the
  /// supervisor's roster (oraclefd surface — open question).
  frame RewindControl request {
    producer:        uuid  @1
    rewind_to_step:  u64   @2
    rewind_to_hash:  hash  @3
    topology_epoch:  u64   @4
  }

  /// Terminal reply to any control-plane frame, on the same correlation id.
  frame ControlAck response {
    applied:    bool            @1
    reason:     ControlRefusal  @2 = unspecified   # meaningful when not applied
    logged_seq: u64?            @3   # eventd seq of control_action, when applied
    detail:     string?         @4   # prose for humans; never switched on
  }

  service ControlPlane {
    call pause   (PauseControl)       -> ControlAck
    call resume  (ResumeControl)      -> ControlAck
    call slow    (SetIntervalControl) -> ControlAck
    call step    (StepControl)        -> ControlAck
    call rewind  (RewindControl)      -> ControlAck
  }
}
```

## 2. Semantics

1. **pause / resume / slow / step** mutate supervisor scheduling state only —
   never the log, never worker state. They are the ralph driver's proven
   `Control` model (`paused` / `interval` / `step`) promoted to
   `agent-supervisord`, per child (`agent` scope) or per tree (`runtime`
   scope). `step` on a non-paused target is refused `not_paused` and is
   **not** logged (§3 logs applied actions only).

### 2.1 Pause semantics (provisional)

**Working decision — Graceful pause:** When a PauseControl frame is applied,
the target transitions to the **paused** scheduling state, meaning:

- **In-flight requests complete.** Any request that has been dispatched to the
  target (corr matching an outstanding call) completes its natural lifecycle
  (execution, response). The supervisor does not interrupt a running request
  mid-execution.
- **New requests are queued.** Incoming requests on the target's channel are
  buffered (up to buffering limits) and remain pending until the target resumes.
- **State does not roll back.** Pause is scheduling-only; it does not undo
  changes made by in-flight requests. Those changes are durable as of request
  completion.
- **Reason field is advisory.** The `reason` string is for operator/audit
  purposes (e.g., "GC pause", "manual operator drain") and is logged; it does
  not change the pause semantics.

Alternative designs (forcible suspension, rollback) are higher-cost and add
state-consistency complexity; graceful pause is proven in ralph and is
sufficient for the timeline-control use cases this RFC supports.

### 2.2 Step semantics & concurrent dependency updates (provisional)

**Working decision — Non-transactional step:** When a StepControl frame is
applied (target must be paused), the supervisor advances the target's scheduler
by one tick, then returns the target to paused. During the step tick:

- **One scheduler tick runs:** The OTP scheduler advances one tick for the
  target. This may result in one message being delivered from the target's
  mailbox, one work item completing, or a state update being processed.
- **Dependencies may interleave.** If the target has pending dependencies
  (RFC 0004 `DependencyRegistration` anchors), they may be resolved or
  fetched during the step — the step is **not** a serializable transaction.
  A producer's state may be written concurrently with the step.
- **No atomicity across state-consumption boundaries.** The step advances the
  target's *local* work, not a global consistent snapshot. If the target
  consumes state from a producer, the producer may advance during or after the
  step (producer and consumer are independent agents).
- **Target returns to paused.** After one tick, the target **automatically
  returns to paused** (no explicit resume needed). The operator must issue a
  `StepControl` for each tick, or a `ResumeControl` to switch to normal
  scheduling.

This is consistent with the ralph `Control.step` model (single tick) and
avoids the cost of transaction-level isolation across agents. Multi-step
atomicity (if needed) is an application-layer concern, using higher-level
synchronization (dependencies, acknowledgements, etc.).

### 2.3 Authority scoping for control verbs (provisional)

**Working decision — Per-target authority:** Authority for control frames is
scoped **per (target, verb) pair**, enforced by `preceptord` at request time:

- A principal (identified by SPIFFE ID from the Litany Wire connection, RFC 0006)
  may have authority to pause agent X but not agent Y, or to pause X but not to
  rewind it.
- Authority is checked **before** the frame is logged; a denied frame returns a
  `ControlAck{applied=false, reason=denied}` and does **not** create a
  `control_action` entry (refused frames do not pollute the log).
- **No service-level authority.** The five control verbs are not further
  subdivided at the service level. Authority is evaluated per-verb per-target,
  not per-verb globally or per-endpoint.
- Policy is `preceptord`'s concern (§3 Security). The frame format carries no
  built-in authority; it is purely a shape for expressing intent.

**Future:** RFC 0006 may define cross-host authority (can principal A from host
X control agent B on host Y?); that is a mesh/fabric concern, not a frame-level
one.

### 2.4 Targets and the epoch fence

`target` is a *declared name* — a
supervisor child id (which the `otp.supervision` lowering derives from
decl names) or the runtime's name when `scope = runtime`. Names are
unique within a topology epoch's graph, so the `(target,
topology_epoch)` pair is unambiguous across agent churn/name reuse; a
frame whose `topology_epoch` is not current is refused `stale_epoch`
(epochs are supervisor-assigned, never caller-asserted — RFC 0004 §7),
and an empty or non-resolving `target` is refused `unknown_target`.

## 2. Rewind semantics

2. **rewind** composes RFC 0004 machinery and nothing else: the supervisor
   (a) pauses every worker holding an anchor above `rewind_to_step`,
   (b) appends the `RewindEvent`, (c) restarts the producer's worker **and
   every worker paused in (a)** — each restarted worker runs cold-start
   verification (RFC 0004 §6) and either re-anchors (RUNNING) or parks as
   `PAUSED(stale_dependency)` with its `StaleDependency` record. No worker
   is left paused without a specified path forward.

## 3. Idempotency & logging

3. **Idempotency.** Frames are idempotent per correlation id: re-delivery of
   an applied frame re-acks with the original `logged_seq`; re-delivery of a
   refused frame re-acks the refusal. The corr→outcome map is rebuilt from
   the log on supervisor restart (the `control_action` payload carries
   `corr`, §3); its retention is the log's.

## 3. Visibility: applied control actions are events

Every **applied** control frame is appended to the runtime's eventd log as a
`control_action` payload —

```json
{"kind": "control_action", "v": 1, "frame": "<frame name>",
 "body": {<frame fields>}, "corr": "<correlation id>", "actor": "<principal>"}
```

— **before** the action takes effect (the RFC 0004 §3.1 write-ahead
discipline). **The log is authoritative across crashes**: on recovery, the
supervisor re-applies logged-but-unapplied actions (they are idempotent), so
replay never asserts an intervention that didn't, in the end, happen.
Consequences: replay reproduces operator interventions in order;
`eventd state --at N` shows what was paused/rewound as of N; and a rewind's
`control_action` entry **precedes** its `RewindEvent` on the chain (the
supervisor SHOULD append the pair without interleaving, but adjacency is not
load-bearing), attributing the rewind to its principal.

## Security considerations

- **Authority is preceptord's.** Each verb is a distinct grant; `rewind` is
  the highest (it voids anchors). A refused frame is acked
  `applied = false` with its typed `reason`; the *attempt* is auditable via
  preceptord's own trail — refusals do not pollute the runtime log.
- **Epoch pinning** (§2.4) fences replayed/stale frames — scheduling verbs
  and rewinds alike — after the topology has moved.
- **Default-deny by encoding:** `ControlScope` case 0 is `unspecified` and
  refused, so the canonical omitted-field default can never address the
  whole tree.
- **Pause/step as DoS:** a flood is absorbed by idempotency; rate limiting
  beyond that is a preceptord budget concern (#28 `toolCalls`-style), not a
  frame-format concern.
- Tamper evidence of recorded actions is inherited from eventd (hash chain;
  boot-time hard verify).

## Open questions

- Should `StepControl` carry a count (`steps: u32 = 1`)?
- Cross-host control over Litany Wire: addressing a runtime on another node
  (relates to RFC 0003 transports and the #16 mesh boundary).
- A query/introspection frame (the `eventd state` verb over the wire) — or
  is that `oraclefd`'s surface? The name→AgentId roster `RewindControl`
  needs (§1) likely lives there too.
- Whether the four scheduling frames should also accept `uuid` targets for
  parity with RFC 0004, with names as an operator-CLI affordance resolved
  before the wire.
