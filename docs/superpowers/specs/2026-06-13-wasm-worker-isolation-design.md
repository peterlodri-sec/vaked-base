# WASM worker isolation — a sandboxd backend (design)

## Status

Design (2026-06-13). Issue [#50](https://github.com/peterlodri-sec/vaked-base/issues/50),
triaged in [0016](../../language/0016-substrate-candidates.md). Decisions taken
with the owner (2026-06-13). Convention: subsystem = design → plan → impl; this
is the design. Composes shipped foundations (eventd oracle, RFC 0004, the
otp.supervision worker contract) plus two pending ones (the #16 arena, the Zig
daemon roster).

## Purpose

Run a fiber/agent worker as a **WebAssembly component under Wasmtime** — a
language-agnostic, snapshotable, instruction-metered sandbox — as **one of
`sandboxd`'s isolation backends**, not a new daemon. WASM buys two properties
that map exactly onto foundations the runtime already commits to:

- **instant linear-memory snapshots** ↔ the arena's content-addressed
  checkpoints (#16) and eventd's rewind substrate (RFC 0004 §3.3);
- **instruction metering** (Wasmtime fuel / epoch interruption) ↔ the `budget`
  schema (#28) — a *mathematical* compute bound rather than broker policy
  (the owner's "flat-cost economic bound").

## Where it lives: a sandboxd backend (decision)

`sandboxd` already owns the **process** and **filesystem** membranes
([runtime roster](../../runtime/README.md)). WASM isolation is a third entry on
its existing isolation axis, not a peer daemon:

```
sandboxd isolation backend ∈ { native-exec, oci, wasm }
```

This keeps the roster small (CLAUDE.md: "small enough to implement and
remember") and gives the three backends one supervision/eventing path. The
otp.supervision worker contract (`vaked_fiber_worker` → port) gains a `wasm`
backend alongside the eventual native Zig-daemon port; **distroless Nix OCI**
(0016) is the conservative `oci` backend bundled in the same axis.

## How a worker selects the wasm backend (open, grammar-first)

**Lean: the backend follows the engine, not a new language field.** A fiber
already names an `engine` that determines its built artifact (today
`zig.build` → a native daemon). A WASM-component engine (e.g.
`wasm.component { … }`) ⇒ a wasm worker — the language stays small and the
selection is a property of the artifact, not a separate knob. A `backend =`
field on `fiber` would be the alternative; it is **not** proposed here.
Grammar-first decision deferred to its own issue if the engine-typing route
proves insufficient (e.g. one engine, two isolation targets).

## Snapshots: raw → arena (decision, two phases)

A WASM worker's whole state is its linear memory + a small amount of host
state (table, globals, fuel remaining). A checkpoint is a snapshot of that.

- **v0 — raw blob.** The snapshot is a raw linear-memory blob, written to the
  content-addressed arena and **referenced by `NodeId` from an eventd entry**
  (never inlined — the RFC 0004 §1 rule: payloads reference arena `NodeId`s).
  Simple and correct; a `RewindEvent` (RFC 0004 §3.3) to step N restores the
  worker to its byte-exact image as of N, *complementing* cold-start
  verification (§6): the supervisor restores the snapshot, then re-verifies
  dependency anchors.
- **follow-up — content-addressed pages.** Page the linear memory and store
  pages as arena nodes (#16). Identical pages dedupe across snapshots and
  across sibling workers (structural sharing — the same refcount discipline as
  the GC floor); a rewind shares unchanged pages with the live image. This is
  the WASM analogue of the arena's graph-node sharing; it lands with the arena.

Both phases keep the **single source of truth** intact: the snapshot is
content in the arena, the *when* is the eventd entry. No second store.

## Metering: `budget.fuel` (decision — concrete schema slice)

The `budget` schema (#28) gains:

```vaked
field fuel : Int { optional > 0 }   # Wasmtime instruction units
```

`fuel` is the instruction ceiling a wasm worker runs under; Wasmtime's
fuel-exhaustion trap (or epoch interruption) is the enforcement point — the
bound is checked by the substrate, not estimated by the broker. It composes
with the existing `tokens`/`wallClock`/`toolCalls` (different axes: fuel meters
the *worker's own compute*, tokens/toolCalls meter its *model/tool calls*).
Lands now (schema ahead of runtime, the #28 pattern); enforced when the wasm
backend ships.

## Component-Model interface ↔ the config contract (open)

A fiber's worker config lowers today to `gen/zig/<fiber>.json` (0012 §5.2). A
WASM component declares its imports/exports as **Component-Model interface
types** (WIT). Open question: is the config-contract one IDL (WIT generated
from, or generating, the gen config) or two parallel descriptions? Decide at
the daemon-spec phase, alongside the otp.supervision worker-port question.

## What is deliberately NOT here

- No new daemon (sandboxd backend, by decision).
- No new top-level Vaked kind (backend follows the engine).
- No hashing on the substrate — snapshots are arena content; the canonical
  hash stays the eventd oracle's (the supervisord-design rule).
- No second event store — NATS/distribution (#52) is a separate slot.

## Verification posture

CI has no Wasmtime; like the OTP tree, runnability is a devshell gate:
- `task wasm-smoke` (future): compile a trivial component, run it under the
  wasm backend, snapshot → rewind → assert byte-exact memory restore +
  fuel-exhaustion trap on an over-budget run.
- the `budget.fuel` schema slice is CI-covered now (builtins self-check +
  catalog coverage + a range-rejection probe).

## Plan

1. *(now)* `budget.fuel` schema slice (this round).
2. `sandboxd` daemon spec gains the isolation-backend axis + the wasm backend
   contract (with the daemon roster work).
3. WIT ↔ gen-config decision + the wasm worker port (with the Zig-port era).
4. Arena-paged snapshots (with #16).

## Open

- engine-typed backend vs a `fiber.backend` field (grammar-first, above).
- WIT/gen-config IDL unification (above).
- fuel ↔ wallClock interaction for a worker that sleeps (fuel doesn't advance
  while suspended — does a sleeping worker hold its snapshot or release it?).
