# CLAUDE.md — RFC Incoherence Hunter

## Mission

Find logical incoherence in the Vaked protocol RFC series **and the MLIR topology-compilation spec set** (docs 0013, 0019-0024) using three specialist personas (orchestration expert, kernel/eBPF contributor, TCS/languages prodigy) that analyze RFC 0004, related RFCs, and the MLIR dialect/pass docs in parallel, adversarially verify findings, and synthesize a coherence report.

External callers should hit `rfc-incoherence-hunter.rfc_incoherence_hunter` first.

## Architecture at a glance

- **Pattern(s):** Parallel Hunters + HUNT→PROVE + Dynamic Cross-Reference Following
- **Topology:** one AgentField node (`rfc-incoherence-hunter`) with 15 reasoners
- **Entry reasoner:** `rfc_incoherence_hunter` — ingests RFCs, orchestrates all three specialists, verifies findings, composes report
- **Internal reasoners:**
  - `section_classifier` (`.ai()`) — assigns RFC sections to each specialist dimension
  - `orchestration_expert` (orchestrator) — parallelizes protocol_contract_checker + lifecycle_checker; follows cross-refs dynamically
  - `protocol_contract_checker` (`.ai()`) — finds missing preconditions, undefined error paths, round-trip gaps
  - `lifecycle_checker` (`.ai()`) — finds dead transitions, deadlocks, unreachable agent states
  - `kernel_expert` (orchestrator) — parallelizes bpf_atomicity_checker + thread_model_checker
  - `bpf_atomicity_checker` (`.ai()`) — finds dual-writer BPF map risks, TID stability gaps
  - `thread_model_checker` (`.ai()`) — finds BEAM/OS TID mismatch, TID reuse hazards
  - `languages_expert` (orchestrator) — parallelizes formal_consistency_checker + semantic_completeness_checker + mlir_dialect_checker
  - `formal_consistency_checker` (`.ai()`) — finds circular definitions, contradictory MUSTs, temporal violations
  - `semantic_completeness_checker` (`.ai()`) — finds undefined normative terms, unnamed reachable states
  - `mlir_dialect_checker` (`.ai()`) — finds MLIR-set incoherence: SSA well-formedness, vaked/hcp op+type completeness (TableGen-readiness), pass pre/postconditions, and the hcp op ↔ RFC 0004 frame mapping (docs 0013, 0019-0024)
  - `cross_ref_follower` (`.ai()`) — conditionally called by any specialist for major/critical cross-references
  - `finding_verifier` (`.ai()`) — adversarial verifier: tries to REFUTE each non-minor finding
  - `coherence_report_composer` (`.ai()`) — synthesizes into a structured coherence report
- **Inter-reasoner traffic:** all internal calls use `app.call(f"{app.node_id}.X", ...)` or `router.call(f"{NODE_ID}.X", ...)`. Never direct HTTP.

## Why this architecture (not a chain)

The three specialist dimensions (protocol correctness, kernel behavior, formal semantics) are independent — they can and must run in parallel to fit in the sync timeout. Within each specialist, two sub-checkers run in parallel with different analytical frames, giving each specialist two chances to surface issues neither alone would catch. Dynamic cross-reference following means the call graph's shape is NOT committed upfront: a sub-checker that flags a cross-reference causes the specialist orchestrator to spawn a `cross_ref_follower` call at runtime — this path either fires or it doesn't depending on what the sub-checker found. The HUNT→PROVE verifier earns its cost because a false "incoherence finding" in a protocol RFC is expensive (it generates design discussion for a non-issue); the adversarial verifier filters before the report is composed.

## Primitive selection rules (binding)

- `.ai()` is used ONLY at gates and leaf checkers: `section_classifier`, `protocol_contract_checker`, `lifecycle_checker`, `bpf_atomicity_checker`, `thread_model_checker`, `formal_consistency_checker`, `semantic_completeness_checker`, `mlir_dialect_checker`, `cross_ref_follower`, `finding_verifier`, `coherence_report_composer`. Every `.ai()` schema here has a `confident` field and a fallback.
- Orchestrator reasoners (`orchestration_expert`, `kernel_expert`, `languages_expert`, `rfc_incoherence_hunter`) contain only Python orchestration logic (asyncio.gather, filtering, rendering) — no `.ai()` calls directly.
- `@app.skill()` is not used — all deterministic transforms (corpus building, finding rendering, deduplication) are plain Python helpers in `reasoners/helpers.py`.
- New leaf checkers default to `.ai()` with a `CandidateFinding` schema and `confident=false` fallback.

## Data-flow rules

- RFC corpus is built by `helpers.py` functions (plain Python) and passed as strings to reasoners.
- Findings cross reasoner boundaries as plain dicts (cross-boundary serialization drops Pydantic type identity). Reconstruct with `Model(**dict)` only when branching on the result type.
- LLM-to-LLM handoffs use rendered prose (`render_finding`, `render_verified_findings`) — not raw JSON dicts.
- The corpus is truncated for non-RFC-0004 files (first 150 lines) to keep specialist context bounded. Exception: RFC 0004 **and** the MLIR set (`mlir-*`) are kept in full — the `hcp` op ↔ RFC 0004 frame mapping has to be checked against both whole.

## Model selection

- Default model: `openrouter/google/gemini-2.5-flash` via `AI_MODEL` env.
- The entry reasoner accepts an optional `model` parameter. When present, it propagates to all child reasoners via `app.call(..., model=model)`. Use `openrouter/anthropic/claude-3-5-sonnet-20241022` for deeper analysis.
- Provider: **OpenRouter only** (`OPENROUTER_API_KEY`). The swarm defaults to OpenRouter for all LLM calls.

## Runtime contract

- Local runtime: `docker-compose.yml` in this directory.
- Two containers: `agentfield/control-plane:latest` (port 8080) + this Python agent (port 8001).
- The vaked-base repo is mounted read-only at `/rfcs` inside the agent container. Set `VAKED_REPO_PATH` in `.env` to override the default path.
- RFC files are read from `/rfcs/protocol/rfcs/*.md`. The vocabulary doc is read from `/rfcs/docs/protocol/README.md`. The MLIR topology-compilation spec set (umbrella `0013` + parts `0019-0024`) is read from `/rfcs/docs/language/*.md` (keyed `mlir-*` in the corpus).

## Delivery contract — every change must preserve

- A runnable `docker compose up --build` (validate with `docker compose config`)
- A valid `.env.example` listing `OPENROUTER_API_KEY`, `VAKED_REPO_PATH`
- The async smoke test in README.md using `POST /api/v1/execute/async/...` + polling
- This `CLAUDE.md`

## Validation commands (run after every change)

```bash
python3 -m py_compile main.py
python3 -m py_compile reasoners/*.py
OPENROUTER_API_KEY=sk-or-v1-FAKE docker compose config > /dev/null
```

## Anti-patterns (reject these)

- Direct HTTP between reasoners. All internal traffic uses `app.call` or `router.call`.
- Passing Pydantic model instances across `app.call` boundaries (they become dicts; reconstruct explicitly or render to prose).
- Replacing the three parallel specialist calls with a sequential loop.
- Calling `app.ai()` directly inside an orchestrator reasoner body (orchestrators contain only Python + `app.call`).
- Hardcoding `node_id` in `app.call`. Always use `f"{app.node_id}.X"` in `main.py` or `f"{NODE_ID}.X"` in router files.
- Removing the `confident` field from any `.ai()` schema without replacing the fallback.
- Passing the full corpus of all four RFCs to all calls — RFC 0003 is 1200+ lines. Only RFC 0004 and the MLIR set (`mlir-*`) are passed in full; others are truncated in `build_full_corpus`.

## Extension points

- Add a new specialist dimension: create a new orchestrator reasoner + two sub-checkers in `specialists.py`, tag with `tags=["specialist"]`, and add the parallel `app.call` in `rfc_incoherence_hunter`.
- Add more RFC coverage: update `ingest_rfcs()` in `helpers.py` to read additional paths, or adjust the truncation threshold in `build_full_corpus`.
- Increase finding depth per specialist: add a third sub-checker per orchestrator (e.g., `drain_semantics_checker` for the orchestration dimension).
- Switch to a stronger model for the verifier only: pass a separate `verifier_model` kwarg to the entry reasoner and thread it to `finding_verifier` calls while other calls use the default model.

## Owner

Scaffolded by the `agentfield-multi-reasoner-builder` skill. To rebuild, run `/agentfield <same description>`. To extend, follow this CLAUDE.md.
