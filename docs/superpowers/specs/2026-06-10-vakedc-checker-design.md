# vakedc checker (0011 stages 3–4) — design

- **Date:** 2026-06-10
- **Status:** Approved (brainstorm) → implementing via subagent-driven execution
- **Goal:** make "validate before generating" executable — 0011 pipeline stages 3 (elaborate) + 4 (check) on the vakedc LPG.

## Decisions

1. **Catalog form — dogfood.** The built-in schema catalog + capability taxonomy is encoded AS Vaked source: `vaked/schema/builtins.vaked` (v0.3 `schema`/`capability` syntax). vakedc parses it with its own parser; the checker reads schemas/taxonomy from the resulting LPG. `vaked/schema/parallel-types.md` remains the normative prose; a spec test guards builtins ↔ md coverage (every kind and every capability domain in the md exists in the builtins graph).
2. **Scope — full stage 3–4 incl. generics.** Conformance (0011 §1.1 five-clause rule) + closed constraint semantics (§3) + capability checks (§4: valid refs, use ⊆ granted, delegation/routing only attenuates — POLA via per-domain partial-order transitive closure) + generics consistency (§5: `catalog.from : Index<T>` ⇒ same `T`; `Fiber<I,O>` in/out agreement).

## Architecture

- **`vakedc/check.py`** — Stage 3 *elaborate*: bind every node to its kind-schema (builtins graph + in-file user `schema`/`capability` decls extending the catalog). Stage 4 *check*: conformance, constraints, capabilities, generics. Pure function of (LPG + builtins LPG) → diagnostics list; no IO besides reading builtins.
- **Diagnostics** — 0011 error codes (`E-CONFORM-*`, `E-CONSTRAINT-*`, `E-CAP-*`, `E-GENERIC-*`), each `{code, message, file, line, col, span, decl}` sourced from node provenance; deterministic ordering (by file, byteStart, code); human-readable text + `--json`.
- **CLI** — `python3 -m vakedc check <file.vaked> [--json] [--builtins PATH]` → parse → resolve → check; exit 0 clean / 1 with diagnostics / 2 usage. `parse` subcommand unchanged.
- **Constraint semantics** are exactly 0011 §3 (closed set: `oneof`, cmp/range, required/optional, nonempty, `matches` within the bounded regex dialect, `default`). No general predicates.
- **Capability semantics** exactly 0011 §4: attenuation order per domain from `order` chains (acyclic ⇒ partial order; reflexive-transitive closure); `requires_capability`/grants checked; mesh `routes_to` delegation must not escalate.

## Tests (tests/spec, wired into run_all → CI)

1. `builtins.vaked` parses and self-checks clean.
2. Catalog coverage: every kind + capability domain in `parallel-types.md` present in the builtins graph (names + field coverage; spot constraint checks).
3. `vaked/examples/types/conformant.vaked` → 0 diagnostics.
4. `vaked/examples/types/rejected.vaked` → EXACTLY its three documented codes: `E-CAP-ATTENUATION`, `E-CONSTRAINT-RANGE`, `E-CONFORM-UNKNOWN-FIELD` (golden diagnostics snapshot, byte-compared via `--json`).
5. All 15 examples check clean (schemas were widened to real usage in Goal 2 — any failure = catalog drift).
6. Determinism: identical diagnostics JSON across runs.

Tag `v0.5.0` after green.

## Deferred

Lowering execution; runtime enforcement (membranes/revocation); cross-file import resolution (imports remain external stubs; checking is per-file + builtins); incremental checking.
