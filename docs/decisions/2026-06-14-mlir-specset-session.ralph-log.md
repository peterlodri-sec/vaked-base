# Session log — MLIR spec set + Stage-1 scaffold + session-scribe (2026-06-14)

Scope: vaked-base deliverables from the 2026-06-14 working session. Harness/environment
tuning done the same session is intentionally **not** recorded here (out of repo scope).

## MLIR specification set (`docs/language/0013`–`0024`)

Split the single MLIR design note into a Stage-1-implementable, coherence-gated RFC series.

- `0013` rewritten as the RFC **umbrella/index** (abstract, terminology, staged-adoption verdict,
  unified pipeline, parts index, security, open questions). Status: Review.
- `0019` **vaked dialect** — ops (`agent`, `yield`, `execute_step`, `consume`, `execute_with_dep`),
  types (`state_hash`, `agent_id`, `state<S>`), SSA semantics, verifier rules, invalid examples.
- `0020` **hcp dialect** — WAL/registration ops, cross-linked to the multi-agent state-dependency RFC.
- `0021` **Pass 1** — topology analysis (cycle detection, critical path, depth bound); diagnostics
  reconciled with the already-shipped cycle diagnostic.
- `0022` **Pass 2** — WAL injection lowering (`vaked.consume` → hcp registration sequence).
- `0023` **Pass 3** — AOT supervisor-index generation.
- `0024` — `vaked→hcp→LLVM` lowering contract + staged adoption + reference-semantics contract.

Indexed in the language README + reference map. Numbering contiguous (no drift-gate gap); inbound
links to `0013` preserved.

**Principle:** Stage 0 (the shipped LPG passes in `vakedc`) is the executable oracle; Stage 1 is the
MLIR-shaped reproduction whose verifiers/passes must match it.

## `vaked-mlir` Stage-1 scaffold

C++/TableGen project translating `0019`/`0020` to code (specs were authored TableGen-ready for this):

- vaked + hcp dialects (TableGen + C++ dialect classes)
- op verifiers enforcing every `0019` constraint
- Pass 1 (DFS cycle detect + topo-sort/DP critical path), Pass 2 (WAL-injection ConversionPattern),
  Pass 3 (AOT index JSON)
- LLVM-lowering skeleton, round-trip Stage-0↔Stage-1 validator, opt-style tool, integration test

**Not compiled** — the project-wide "never build on the dev machine" rule was honored; build/test is
deferred to the remote builder / CI.

## session-scribe (PR #190, merged)

Command + skill + doc to export a session as a PII-scrubbed, enriched `USER:SYSTEM` reasoning
transcript with a hard zero-leak audit gate. See `docs/agents/session-scribe.md`.

## Deferred

- coherence-hunter extension — tool source absent (only bytecode cache present); flagged, not built.
- vaked-mlir Pass 2 / LLVM lowering — skeletons; need full implementation + a remote build to validate.
