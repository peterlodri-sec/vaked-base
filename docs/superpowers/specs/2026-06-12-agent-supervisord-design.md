# agent-supervisord — the control plane daemon (design)

## Status

Design (2026-06-12). The keystone daemon of the runtime roster
([`docs/runtime/README.md`](../../runtime/README.md)): the OTP control plane
that the whole 2026-06-12 arc converges on. Tracks C+D of the epic (#17,
issues #19/#20). Convention: daemon = design → plan → impl; this is the
design. Everything it composes is **already specified — and, for the eventd oracle and the lowered tree,
shipped** — this
document only fixes how the pieces snap together.

## Purpose

One BEAM application per host that, per runtime:

1. **boots the lowered tree** — loads `gen/otp/<slug>_sup.erl` (Track C,
   `otp.supervision`) and starts it, one placeholder worker per member until
   the Zig daemons replace them;
2. **owns the eventd writer** — the RFC 0004 single-writer discipline: every
   event (agent steps, dependency artifacts, control actions) flows through
   supervisord onto the hash-chained log at the path declared in
   `gen/eventd.json`,
   `verify_on_boot` as a hard precondition;
3. **enforces the RFC 0004 lifecycle** — workers transition
   `STOPPED → BOOT_SCANNING → DEPENDENCY_VERIFYING → RUNNING |
   PAUSED(stale_dependency)`; the cold-start verifier and GC floor are folds
   of the log it already holds (the eventd oracle defines the exact
   semantics the BEAM side must reproduce — or shell out to during the
   reference phase);
4. **serves the RFC 0005 control plane** — pause/resume/slow/step/rewind with
   preceptord authority, epoch fencing, typed refusals, and write-ahead
   `control_action` logging;
5. **runs workflows** — loads `gen/workflow/<name>.json` (the AOT spec:
   steps, edges, precomputed depth) and drives runs as step events on the
   log, retries per step, budgets per #28.

## Shape

```text
agent_supervisord (application)
├── eventd_writer     (gen_server: serializes ALL appends — the single-writer
│                      funnel; flock holder once BEAM-native, while during the
│                      reference phase the oracle takes the flock per append)
├── control_plane     (gen_server: RFC 0005 frames in, ControlAck out;
│                      scheduling state = the promoted ralph Control model)
├── workflow_engine   (owns one gen_server per active run — a dynamic
│                      supervisor over runs: walks the AOT DAG, emits step
│                      events, applies retries/budgets)
└── <runtime>_sup     (the LOWERED tree — generated code, never hand-edited)
    ├── worker 'memberA'   (vaked_fiber_worker → later: port to Zig daemon)
    └── worker 'memberB'
```

- The generated tree is a child of the daemon, not the daemon itself: the
  hand-written application supervises the machine-written supervisor. The
  generated/hand-written boundary is exactly the `gen/` boundary.
- **Reference phase bridge:** until the BEAM reimplements the fold, the
  daemon invokes the Python oracle (`python3 -m eventd
  {verify,append,state,floor,coldstart}` — frozen exit codes 0/2/3/4/5 are
  the API) via ports. This keeps the canonical-hash byte contract in exactly
  one implementation while the daemon's *shape* hardens. The BEAM-native
  fold is the port's replacement, gated by the same parity tests as the Zig
  port (#15 pattern).
- **Control intake (reference):** the ralph control-file pattern
  (`control.json` polled per tick) carries pause/interval/step locally;
  RFC 0005 frames over Litany Wire replace it when the wire lands. Both
  funnel into the same `control_plane` state — the file is a transport with
  one acknowledged delta: file-driven actions synthesize their `corr` and
  refusals are log-visible only (no `ControlAck` channel until the wire).

## What is deliberately NOT here

- No second rewind mechanism (RFC 0005 composes RFC 0004 — §2.2 there).
- No restart cascades beyond stock OTP (`one_for_one` v0; linear-chain
  `rest_for_one` + index-driven descendant restart per the otp.supervision
  design follow-up).
- No hash computation on the BEAM during the reference phase (oracle owns
  bytes).

## Verification

1. **Shape smoke (extends `task otp-smoke`):** boot the application against
   `agentfield-swe`'s lowered output; assert children alive, then drive one
   pause→step→resume cycle via the control file and observe the
   `control_action` entries via `python3 -m eventd state`.
2. **Rewind demo (the epic's acceptance 3, end-to-end):** two producers, one
   dependent; rewind producer A; assert the dependent pauses
   `stale_dependency` (cold-start refusal via oracle exit code 3) while
   producer B's worker never restarts.
3. CI remains bytes/structure (no BEAM in CI); both demos are devshell tasks
   recorded in the PR that lands them.

## Plan

1. Skeleton BEAM app (`daemons/agent-supervisord/`): application + the three
   gen_servers, oracle-port bridge, control-file intake. (impl PR 1)
2. Workflow engine: drive `gen/workflow/swe_af.json` as logged step events
   (placeholder step bodies). (impl PR 2)
3. RFC 0005 frame intake over Litany Wire; retire the control file. (with
   the wire implementation)
4. BEAM-native fold + parity gate; retire the oracle port. (with #15-era
   parity tooling)

## Open

- One daemon per host supervising many runtimes, or one per runtime?
  (Lean per-host application with one `<runtime>_sup` child per runtime —
  matches the roster's singular `agent-supervisord`.)
- Where preceptord's authority check physically runs during the reference
  phase (no preceptord exists): lean "allow-all + log the principal", with
  the deny path stubbed but wired.
- Budget enforcement point for workflow steps (engine-side vs worker-side).
