# Plan — vakedz (Zig front-end) port

**Date:** 2026-06-13 · **Design:** [`../specs/2026-06-13-vakedz-zig-frontend-design.md`](../specs/2026-06-13-vakedz-zig-frontend-design.md)

Phased port of `vakedc` (`parse → check → lower`) to Zig, gated by byte-parity
against the Python reference. Each phase's "done" = the cross-verify gate green
for the goldens it adds. Gaps found while dogfooding become GitHub issues — that
stream is the live backlog.

## Phase 0 — scaffold + parity harness ✅ (this PR)
- [x] `vakedz/` package (`build.zig`, `build.zig.zon`, Zig 0.16 floor).
- [x] `json.zig` canonical writer (fixed-order wrappers + `sortRecursive` props).
- [x] `lexer.zig`, `parser.zig`, `graph.zig` — parse → LPG → canonical JSON.
- [x] `cache.zig` — the ralphloop-cache (content-addressed, hash-chained).
- [x] CLI `parse | check | lower | all | cache`; parse mediated by the cache.
- [x] Goldens from `vakedc parse`; `crossverify.sh`; `vakedz-ci.yml`; Taskfile.
- [x] Research + design + plan docs.

## Phase 1 — parse parity, green ⏳ (drive CI to green)
- [ ] First CI run is the parity gate; fix any byte diffs in `graph.zig`/`json.zig`
      against real Zig (no Zig/Nix in the authoring sandbox — CI is the oracle).
- [ ] Add goldens for more examples to widen front-end coverage:
      `vaked/examples/types/*`, `membrane/*`, `agentfield-swe.vaked`,
      `primitives/memory.vaked`, `containers/browser-pool.vaked`.
- [ ] Port the NFC (Unicode 15.1.0) gate.

## Phase 2 — check (0011) port
Port the 22-code checker (research Strand B). Suggested order:
- [ ] Builtins loader (`vaked/schema/builtins.vaked`) + schema/capability registry.
- [ ] Load-time well-formedness: `E-SCHEMA-*`, `E-CAP-ORDER-*`.
- [ ] Conformance + constraints: `E-CONFORM-*`, `E-CONSTRAINT-*`.
- [ ] Capability attenuation: `E-CAP-*` (transitive closure + POLA on mesh edges).
- [ ] Generics, ref resolution, workflow DAG, name collisions.
- [ ] `check --json` byte-parity; goldens diff vs. `vakedc check --json`.

## Phase 3 — lower (0012) first slice
- [ ] The operator-field slice (research Strand C): `nix.spine`, `docs.runtime`,
      `zig.daemoncfg`, `catalog.jsonl`, `otp.supervision` → 7 files, byte-identical
      to `vaked/examples/lowering/`.
- [ ] `inputsHash` projections + `provenance.json` parity.
- [ ] Extend to the agentfield slice (`memory.store`, `workflow.spec`,
      `eventd.config`, `colmena.hive`) and the NixOS cohort.

## Phase 4 — make vakedz first-class
- [ ] Pin Zig in `flake.nix` (kill the version-drift risk).
- [ ] Wire `vakedz` into `tools/vaked-run.sh` / the spec-test harness as a
      second oracle (Python and Zig must agree).
- [ ] Language-level `cache` construct: design (grammar + schema + lowering) per
      the tracking issue — only once a `.vaked` program needs to *declare* a cache.

## Tracking issues
Filed against `peterlodri-sec/vaked-base` with this PR (see PR body for links):
- `vakedz` subsystem tracking (the parse→check→lower backlog).
- Language-level `cache` construct (the owner's "both" follow-up).
