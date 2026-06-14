# ralph-introspect — a daily, gated fleet self-improvement loop over Langfuse telemetry (design)

## Status

Design + shipped (2026-06-14). **Tooling**, not the Vaked language — no grammar gate.
Owner-approved scope. A new **mode of ralph** (`ralph introspect`), reusing the ralph harness
(`openrouter_call` w/ Langfuse spans, the hash-chained `append_event`, the cost cap, `gh`) — the
deltas are a Langfuse **query** client, a telemetry **digest**, the 3-stage loop, and a gated workflow.

## Why

Every CI bot emits Langfuse traces, but **nothing reads them back** — the fleet's own observability
never feeds improvement. ralph-introspect closes that loop: once a day it ingests the last ≤2 days
of the fleet's Langfuse traces (+ ledgers + CI), **auto-detects the most salient finding**, ideates
**one** novel solution, **always reviews** it (fail-closed), and hands a survivor to **swe_af**. It
also surfaces the **fleet economy** — real spend projected to a normal day/week/month — so cost
creep stays visible.

## The loop (`ralph introspect` — one daily run; abstain by default)

1. **Ingest (no LLM).** `_langfuse_query()` (stdlib urllib, HTTP Basic from
   `LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY` against `LANGFUSE_HOST`) pages
   `GET /api/public/observations?type=GENERATION&fromStartTime=…&toStartTime=…`. Real (OTel)
   observations name the span `gen_ai.generate`, so we **group by `model`** (always present) and
   **compute cost client-side from tokens × price** (server cost is usually absent); span names are
   summarised separately. Plus the ralph + optitron **ledgers** and recent `gh run list` outcomes.
2. **Economy roll-up.** Sum the per-model cost over the window → real spend; project linearly
   (`/day`, `×7`, `×30.4`) — *normal, non-optimistic*. Emitted in the digest, CI summary, ledger
   event, and issue body.
3. **Detect** (`deepseek-v4-flash`, span `ralph.introspect.detect`) — pick the single most salient
   finding, grounded in exact digest numbers. `--focus` overrides.
4. **Ideate** (`claude-opus-4.8`, span `ralph.introspect.ideate`) — ONE novel solution: mechanism,
   novelty rationale, target files, grep-able signature, confidence.
5. **Review — always** (`claude-opus-4.8`, span `ralph.introspect.review`) — skeptical adjudication:
   `approved && novel && grounded && actionable && confidence ≥ 0.75`. Plus deterministic novelty
   (`git grep` the signature + ledger title dedupe). Fail-closed.
6. **Act (survivor only).** Open an `agent`-labelled issue (the swe_af trigger) with finding +
   evidence + idea + economy; append an `introspect_found` event; stage a Carcin toot + Telegram.
   Nothing survives ⇒ `introspect_none`, CI log only.

## Files

- **`tools/ralph/ralph.py`** — `cmd_introspect` + the `introspect` subparser, `_langfuse_query`,
  `_introspect_digest`, `_ledger_stats`/`_ci_stats`, `_known_in_repo`, the issue/announce/summary
  helpers. Reuses `openrouter_call`, `append_event`, `_parse_json_obj`, `_gh_json`, `_run`.
- **`tools/ralph/introspectcore.py`** — pure logic: `aggregate_observations(cost_fn)` (by model),
  `span_counts`, `economy_projection`, `build_digest`, the 3 strict json_schemas, `passes_gate`,
  `prior_introspect_titles`, prompt builders. Stdlib-only, fully unit-tested offline.
- **`tools/ralph/introspect_purpose.md`** — the mission preamble (system prompt).
- **`tools/ralph/test_introspect.py`** — offline tests (digest aggregation incl. client-side cost,
  economy math, the gate's reject paths, dedupe); wired into `spec-tests.yml`'s `python-spec` job.
- **`.github/workflows/ralph-introspect.yml`** — daily `schedule` + gated `workflow_dispatch`:
  `approve` job on the protected **`introspect-manual`** Environment (required reviewers, confirm #2)
  gated on typed `confirm == 'RUN'` (confirm #1); `introspect` job (`needs: approve`,
  `environment: ci`) runs the loop. **`concurrency.group: ralph-tracks`** (shared) — critical:
  introspect appends to ralph's single-writer `events.jsonl`, so it must serialize against ralph ticks.
- **Docs/registry** — `VAKED_AGENTS.md`, `docs/agents/ci.md`, this spec, a `tools/ralph/README.md` note.

## Models (June-2026 defaults; env-overridable, budget-capped)
detect `RALPH_INTROSPECT_DETECT_MODEL=deepseek/deepseek-v4-flash` · ideate/review
`RALPH_INTROSPECT_{IDEATE,REVIEW}_MODEL=anthropic/claude-opus-4.8`. Non-bypassable `--budget-total`
(default **$3.00/run**); `$0` with no key.

## Economy (own cost — measured at first dry-run)
3 calls/run (~$0.20–0.45 normal; ceiling = the $3 cap). The fleet projection is computed live from
real Langfuse cost — at design time the measured 2-day fleet spend was ~$0.34 → **~$5/month**.

## Anti-hallucination
Abstain by default; the review stage + deterministic novelty + a hard grounding requirement (the
idea must quote real digest numbers) gate every output. Most days yield nothing — the correct outcome.

## One-time owner setup
GitHub → Settings → Environments → create **`introspect-manual`** → add yourself as a Required
reviewer (the manual-run approval gate). No secrets on it — the loop runs in `ci`.

## Verification
`python3 tools/ralph/ralph.py introspect --dry-run` (digest + prompts + cost/economy, no model
calls) · `python3 tools/ralph/test_introspect.py` · `… introspect --once` with
`RALPH_INTROSPECT_DRY_ACT=1` (full loop, issue/toot only drafted) · `… events --replay` (shared
chain still verifies) · dispatch with `confirm=RUN` ⇒ pauses on the `introspect-manual` approval.
