# otp.supervision — lowering `parallel` to a runnable OTP tree (design)

## Status

Design (2026-06-12). Track C of the 1.0 epic (#17), issue #19. Convention:
subsystem = design → plan → impl; this is the design. Implements the deferred
0012 §7 supervision mapping as a **new registry row** (`otp.supervision`);
the `systemd.units` slot stays deferred (host units depend on daemon
packaging, a separate concern).

## Purpose

Make the **parallel theory RUN** (epic acceptance 1): a
`parallel { fibers … supervisor = otp }` group lowers to OTP supervision
source that the devshell's Erlang can compile and run, supervising one worker
per member. Until the Zig daemons exist, workers are placeholders; the tree,
its strategy, and its restart semantics are the real deliverable.

## Artifacts

| Artifact | Content |
|----------|---------|
| `gen/otp/<runtime_slug>_sup.erl` | one supervisor module per runtime: child spec per member of each `parallel … supervisor = otp` group, in dependency order |
| `gen/otp/vaked_fiber_worker.erl` | the generic placeholder worker (gen_server): logs a heartbeat tick, carries `#{name, kind, config}`; later replaced by a port to the member's Zig daemon (`gen/zig/<fiber>.json`) |

`<runtime_slug>` = the runtime name lowered to a legal module atom
(`[a-z][a-z0-9_]*`: lowercase, non-alphanumerics → `_`, prefix `v` if needed)
— module name MUST match filename (OTP rule), so `"agent-field"` →
`agent_field_sup.erl`.

## Strategy mapping (closes the #19 "strategy enum semantics" item)

| Vaked `strategy` | OTP `SupFlags.strategy` | Rationale |
|------------------|------------------------|-----------|
| `"supervised-dag"` — **v0** | `one_for_one` | independent restarts. Blanket sibling cascades (`rest_for_one` over declaration order) would restart *unrelated* members — in `operator-field`, `mediaCompress` and `operatorMap` share no data-flow edge, yet a `mediaCompress` crash would bounce `operatorMap` purely by position. Downstream *consistency* is not the supervisor's blunt instrument anyway: it is RFC 0004's job — a restarted producer's consumers re-verify their anchors and pause as `stale_dependency` if actually affected. |
| `"supervised-dag"` — **edge-aware follow-up** | `rest_for_one` **per topologically-contiguous dependency chain** (chain = a connected component of the members' data-flow edges, children in topo order; unrelated chains under separate sub-supervisors) | the restart cascade becomes a *correct* optimization: only true downstreams restart eagerly instead of waiting to pause on a stale anchor |
| anything else (forward-compat) | `one_for_one` | independent restarts; no ordering claim |

`SupFlags`: `intensity => 3, period => 10` (v0 defaults; a future `budget`
hook may parameterize). Child specs: `restart => permanent, shutdown => 5000,
type => worker`.

## Child ordering

Child-list order is **declaration order** in v0 — purely for byte-determinism
of the emitted module; with `one_for_one` it carries **no restart-coupling
claim**. The edge-aware follow-up (0013 Pass-1 machinery reused over fiber
`input`/`output` edges; surfaces order after their stream producers) computes
the real chains, switches them to `rest_for_one`, and adds a checker WARN when
declaration order contradicts topo order.

## Selection & the golden-freeze problem

Selected by presence of any `parallel` with `supervisor = otp` — which
includes `operator-field.vaked`, whose lowering output is the **frozen golden
fixture set** (`vaked/examples/lowering/`, #15 parity contract: byte-exact
files + 15-entry manifest). Landing this emitter therefore REQUIRES a
deliberate golden extension, not a silent change:

1. Existing fixture files stay **byte-identical** (the spine derives its gen/
   listing from fibers/indexes, not from the emitted-file set — verified; the
   new artifacts are additive `gen/otp/*` files + provenance entries).
2. The fixture set gains `gen/otp/operator_field_sup.erl` +
   `gen/otp/vaked_fiber_worker.erl`; the manifest grows 15 → 17 entries.
3. The Zig-port differential harness (#15) inherits the new files as parity
   targets — coordinate the bump in the port branch (or land this before the
   port's lower phase starts; today the port is at phase 0/1, so the window
   is open).

This is the one lowering change in the series that touches the goldens; it is
called out here so the bump is an explicit, reviewed act.

## Worker contract (placeholder, v0)

`vaked_fiber_worker` is a `gen_server`:

- `start_link(#{name := Name, kind := fiber|surface, config := Path|none})`
- `init/1` logs `"vaked <kind> <name> up (placeholder; daemon port pending)"`
  and schedules a 5s tick;
- each tick logs a heartbeat. No I/O, no eventd writes — appending step
  events to the hash-chained log from Erlang would re-implement the canonical
  hashing outside the oracle (a byte-contract risk); the runtime event path
  arrives with the supervisord daemon proper, which drives the eventd writer
  (single-writer discipline, RFC 0004).

## Verification

- CI has no Erlang: the spec test asserts deterministic bytes + structure
  (one child per member, strategy mapping, module/filename agreement, header)
  — not compilation. A `task otp-smoke` devshell target (`erlc` both files,
  `erl -eval "supervisor:start_link…"` + observe N heartbeats) is the manual
  runnability gate, and becomes the epic's acceptance-1 demo.
- Determinism: two lowers ⇒ byte-identical `.erl` files (same regime as every
  emitter).
- Goldens: existing fixture files byte-identical; new fixture files reviewed
  in the PR diff.

## Plan (implementation order)

1. `_otp_slug` + `emit_otp_supervision` in `vakedc/lower.py`; registry row
   `otp.supervision`; driver gating on `parallel` with `supervisor = otp`.
2. Spec-test group (structure + determinism) + `EMITTER_REGISTRY` + 0012 §3.4
   row (§7 table gets a "superseded by otp.supervision for the OTP tree" note
   on `systemd.units`).
3. Golden fixture extension (the explicit bump above).
4. `task otp-smoke` devshell target + run it once; record output in the PR.
5. Follow-ups: edge-aware chains (`rest_for_one` per dependency chain, topo
   order, checker WARN — 0013 Pass-1 reuse), budget→SupFlags,
   worker→Zig-daemon port (with the daemons, #15-era).

## Open

- Should the supervisor also own the eventd writer process as child 0 (the
  RFC 0004 single-writer)? Lean yes — decide at daemon design, not in the
  lowering.
- Multiple `parallel` groups per runtime: one supervisor module each
  (`<slug>_<group>_sup`) vs one root supervisor with nested groups — v0 has
  single-group examples; defer until a real two-group dogfood exists.
