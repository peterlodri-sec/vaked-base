# Plan — swe_af GHA runner

**Date:** 2026-06-13 · **Design:** [`../specs/2026-06-13-swe-af-gha-runner-design.md`](../specs/2026-06-13-swe-af-gha-runner-design.md)

Materialize the lowered `workflow swe_af` as a GitHub-Actions pipeline triggered by
labeling an issue `agent`. Reuse the adk-rust/OpenRouter fleet; eventd is the audit
spine; POLA mirrors the mesh (only the broker writes to GitHub).

## Phase 0 — scaffold + agent ✅ (this PR)
- [x] `vaked-agents/ci/swe-af/` crate: `Cargo.toml`, `src/main.rs` (plan/code modes,
      read-only `read_file`/`list_dir` tools, full-file-write output), `src/guardrails.rs`,
      `README.md`, `deny.toml`. Mirrors `label-tagger` adk wiring.
- [x] `.github/workflows/swe-af.yml` — DAG (plan→code→review→publish), eventd append
      per node + final verify, safety gate, graceful degradation.
- [x] `.github/workflows/swe-af-build.yml` — rolling prebuilt `swe-af-bin`.
- [x] `.github/labels.yml` — `agent` trigger label.
- [x] `Taskfile.yml: swe-af` hermetic build+test; design + plan docs.

## Phase 1 — green the build + binary ⏳
- [ ] Merge to main so `swe-af-build.yml` publishes `swe-af-bin` (first build is the
      compile oracle — no Rust in the authoring sandbox).
- [ ] Fix any compile diffs against the adk-rust 1.0 API (the crate copies the
      label-tagger surface verbatim, so risk is low).
- [ ] Confirm `ci` env has `OPENROUTER_API_KEY` (reused from the fleet) — owner.

## Phase 2 — the first real run
- [ ] Pick a small, self-contained target issue (docs/test/tooling) to validate the
      loop safely; owner may redirect.
- [ ] Label it `agent`; watch plan→code→review→publish open a draft→ready PR.
- [ ] Verify the uploaded eventd log (`eventd verify` exit 0) and the pr-review verdict.

## Phase 3 — harden from the first run
- [ ] Tune models (`SWE_AF_CODE_MODEL` to a stronger coder), prompts, file caps from
      observed quality.
- [ ] Optional: a stronger reviewer gate (block ready on N blocking findings).
- [ ] Optional: feed memoryd/MemPalace recall into the plan node.

## Phase 4 — the box (deferred)
- [ ] `task agentfield-up` runbook: lower → colmena apply to `dev-cx53` (#51); run the
      same swe_af DAG under the OTP plane on real hardware, surfaced in the control panel.

## Tracking
- New tracking issue: "swe_af GHA runner — realize the lowered workflow" (links #27).
