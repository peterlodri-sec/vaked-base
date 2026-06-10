# vakedc lower (0012 emitters) — design

- **Date:** 2026-06-10
- **Status:** Approved (brainstorm) → implementing via subagent-driven execution
- **Goal:** make lowering executable — the 0012 emitter framework + the Nix spine + the three exemplar emitters, completing the pipeline: parse → resolve → check → **lower**.

## Decisions

1. **Goldens = the existing fixtures.** `vakedc lower vaked/examples/operator-field.vaked` must reproduce `vaked/examples/lowering/` **byte-for-byte** (flake.nix, gen/RUNTIME.md, gen/zig/mediaCompress.json, gen/catalog/zigCorpus.jsonl, provenance.json) — except:
2. **`inputsHash` becomes real**: sha256 over the canonical JSON of the projection's resolved inputs (per-projection keying per 0012 §6.2). The fixture set is regenerated ONCE for the new hash values; the diff is reviewed (only inputsHash values may change); README disclosures updated (the nixpkgs placeholder rev remains disclosed).
3. **Lower only after check** (0012 §1): the CLI runs parse → resolve → check; any diagnostic ⇒ exit 1, nothing emitted.
4. **Output layout = the fixture tree**: `--out DIR` writes `flake.nix`, `gen/…`, `provenance.json` at DIR root (matching the fixtures). 0012's `.vaked/provenance.json` wording is reconciled with one erratum line: the manifest lands at `<out>/provenance.json`; lowering in-place into a repo uses `<out> = .vaked/`. Default out: `.vaked/lower/`.

## Architecture

- **`vakedc/lower.py`** — the framework: `Emitter = (graph, nodes) -> (files, provenance_entries)` (pure: no IO, no clock, no randomness; constraints per 0012 §3.2); registry mapping target → emitter; Nix-spine emitter always runs; direct emitters selected per `emit` targets / fiber presence (0012 §3.3 as implemented by the fixtures). Deferred targets (eBPF/OTel/systemd/surface-launcher) = registry slots that emit nothing (surface lands in the spine as the §7 deferred no-op stub, exactly as the fixture shows).
- **Emitters:** `nix.spine` (flake.nix incl. pinned inputs from `trust = pinned{…}`, packages/devShells/apps, the deferred-launcher stub), `docs.runtime` (RUNTIME.md §5.1 section order), `zig.daemoncfg` (per-fiber JSON, §5.2 canonical key order, `_generated` first), `crabcc.index` (the derivation lives in the spine; provenance entry), `catalog.jsonl` (§5.3b header + rows).
- **Provenance manifest** — §6.2 exactly: artifacts map lexicographic by path; spans from node provenance (already byte-exact in the LPG); `inputsHash = "sha256-" + hex(sha256(canonical_projection_json))` — projection = the emitter's resolved inputs for that region (e.g. the fiber node's props for the fiber-config region; the resolved engine ref + pin for an engine-package region).
- **CLI** — `python3 -m vakedc lower <file.vaked> [--out DIR] [--builtins PATH]`; exit 0 emitted / 1 diagnostics-or-error / 2 usage. `parse`/`check` unchanged.

## Tests (tests/spec/test_vakedc_lower.py, in run_all → CI)

1. **Golden tree:** lower operator-field into a temp dir → byte-compare every file against `vaked/examples/lowering/` (the regenerated fixtures).
2. **Refuses invalid:** lower `rejected.vaked` → exit-equivalent failure, no files emitted.
3. **Determinism:** two runs → identical trees (hash included).
4. **Provenance integrity:** emitted manifest validates against the schema checks already in `test_lowering_fixtures.py` (which keeps running against the same fixtures — both suites must agree).
5. All existing modules stay green. Tag **`v0.6.0`** on green.

## Deferred

Concrete eBPF/OTel/systemd/surface-launcher mappings; `catalog.sqlite` emitter (fixture set has jsonl only); incremental lowering; running `nix build` on the emitted spine.
