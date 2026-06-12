# RFC 0005 — Control Frames (stop / slow / step / rewind)

- **Status:** Draft
- **Created:** 2026-06-12
- **Track:** Protocol

## Abstract

This RFC catalogs the HCP **control frames** through which an operator (or a
supervising driver) exercises the Track D verbs — pause, resume, slow, step,
rewind — against a running Vaked runtime
([control-plane design](../../docs/superpowers/specs/2026-06-12-control-plane-design.md),
epic #17 acceptance 3). The frames are Votive Frames of class `control`,
consumed by `agent-supervisord`; their authority is a `preceptord` policy
decision; and **every accepted control action is itself an eventd entry**, so
replaying the log reproduces the operator's time travel along with everything
else. A `RewindControl` frame *requests* a rewind — the supervisor *performs*
it by appending the RFC 0004 `RewindEvent` and restarting the producer's
worker; this RFC never introduces a second rewind mechanism.

## Terminology

| Term | Definition |
|------|------------|
| Control frame | A Votive Frame of class `control` addressed to the supervision plane (this catalog). |
| Scope | What a verb applies to: `runtime` (the whole OTP tree) or `agent` (one supervisor child). |
| `ControlAck` | The response frame: applied or refused, with the eventd seq of the logged action when applied. |
| `control_action` | The eventd payload kind recording an **accepted** control frame (§3). |
| Step | One-shot: run a single tick while paused, then remain paused (the ralph `Control.step` semantics, promoted). |

Shared vocabulary lives in [`docs/protocol/README.md`](../../docs/protocol/README.md);
the rewind machinery is [RFC 0004](./0004-multi-agent-state-dependency.md) §3.3/§6.

## 1. Frame catalog (`.hcplang`)

Header fields (kind/corr/stream/seq/end) are implicit; tags begin at `@1`.

```hcplang
schema hcp.control {
  version = "0.1.0"

  enum ControlScope {
    runtime = 0,
    agent   = 1,
  }

  /// Pause scheduling for the target (workers keep state; no ticks run).
  frame PauseControl control {
    scope:  ControlScope  @1
    target: string        @2   # runtime name | agent (child) name
    reason: string?       @3
  }

  /// Resume normal scheduling for the target.
  frame ResumeControl control {
    scope:  ControlScope  @1
    target: string        @2
  }

  /// Slow: set the target's tick interval (the ralph `interval` semantics).
  frame SetIntervalControl control {
    scope:       ControlScope  @1
    target:      string        @2
    interval_ms: u32           @3
  }

  /// One-shot step while paused; the target stays paused afterwards.
  frame StepControl control {
    scope:  ControlScope  @1
    target: string        @2
  }

  /// REQUEST a producer rewind. The supervisor performs it per RFC 0004:
  /// pause affected workers -> append RewindEvent -> restart (cold-start
  /// verification re-anchors or pauses true dependents). Highest authority.
  frame RewindControl control {
    producer:        string  @1
    rewind_to_step:  u64     @2
    rewind_to_hash:  hash    @3
    topology_epoch:  u64     @4
  }

  /// Terminal reply to any control frame, on the same correlation id.
  frame ControlAck response {
    applied:    bool    @1
    logged_seq: u64?    @2   # eventd seq of the control_action entry, when applied
    detail:     string? @3   # refusal reason (denied / unknown target / stale epoch)
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
   scope). `step` while not paused is a no-op acknowledged with
   `applied = false`.
2. **rewind** composes RFC 0004 machinery and nothing else: the supervisor
   (a) pauses workers holding anchors above `rewind_to_step`, (b) appends the
   `RewindEvent`, (c) restarts the producer's worker; dependents re-enter
   cold-start verification and pause `stale_dependency` only if actually
   affected. A `RewindControl` whose `topology_epoch` is not the current
   epoch is refused (`stale epoch`) — epochs are supervisor-assigned, never
   caller-asserted (RFC 0004 §7).
3. Frames are idempotent per correlation id; re-delivery of an applied frame
   re-acks with the original `logged_seq`.

## 3. Visibility: control actions are events

Every **accepted** control frame is appended to the runtime's eventd log as a
`control_action` payload (`{"kind": "control_action", "v": 1, "frame": <frame
name>, "body": <frame fields>, "actor": <principal>}`) **before** the action
takes effect — the same write-ahead discipline as RFC 0004 §3.1. Consequences:
replay reproduces operator interventions in order; `eventd state --at N`
shows what was paused/rewound as of N; and a rewind's `control_action` entry
immediately precedes its `RewindEvent` on the chain, attributing the rewind to
its principal.

## Security considerations

- **Authority is preceptord's.** Each verb is a distinct grant; `rewind` is
  the highest (it voids anchors). A refused frame is acked
  `applied = false` and the *attempt* is auditable via preceptord's own
  trail — refusals do not pollute the runtime log.
- **Epoch pinning** (§2.2) prevents replayed/stale `RewindControl` frames
  from acting after the topology has moved.
- **Pause/step as DoS:** a pause flood is absorbed by idempotency; rate
  limiting beyond that is a preceptord budget concern (#28 `toolCalls`-style),
  not a frame-format concern.
- Tamper evidence of the recorded actions is inherited from eventd
  (hash chain; boot-time hard verify).

## Open questions

- Should `StepControl` carry a count (`steps: u32 = 1`)?
- Cross-host control over Litany Wire: addressing a runtime on another node
  (relates to RFC 0003 transports and the #16 mesh boundary).
- A `QueryControl`/introspection frame (the `eventd state` verb over the
  wire) — or is that `oraclefd`'s surface?
- Whether `control_action` entries should carry the `ControlAck.logged_seq`
  chain backwards (action → ack correlation inside the log).
