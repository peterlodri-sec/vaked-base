# vaked-optitron — the optimization crawler

A daily, **abstain-by-default** crawler that surfaces **one** novel, proven,
independently-confirmed **compiler / allocator / Zig / Rust / Vaked** optimization — or
nothing. On a finding it opens a GitHub issue labelled **`agent`** (the `swe_af` workflow
trigger) and announces to Mastodon + Telegram. Declarative spec:
[`.claude/skills/vaked-optitron/SKILL.md`](../../.claude/skills/vaked-optitron/SKILL.md)
(the binary loads it as its system prompt).

Runtime: a **Go binary built on [Eino](https://github.com/cloudwego/eino)** (CloudWeGo's
Go-native LLM framework) — Eino's OpenRouter chat-model component provides the model client,
strict `json_schema` structured output, and reasoning-effort control; the orchestration is
idiomatic Go. Advisory: guards on the API key and any failure logs + exits 0.

## Concurrency (goroutines)
- **Crawl fan-out** — one concurrent crawl call per source family (arXiv · LLVM/Cranelift ·
  Zig · Rust · allocators); candidates are merged + de-duped. Broader recall, one budget.
- **Candidate worker-pool** — surviving candidates run verify→bench→adjudicate in a bounded
  `errgroup` pool; the **first to clear the gate wins**, acts, and cancels the rest (the
  "one finding per run" rule, parallelized instead of sequential).
- **Single-writer ledger** — the hash chain requires one writer, so all appends serialize
  through a mutex-guarded `ledger.Writer`, keeping the chain valid under concurrency.

## PentestGPT lineage
Inspired by [GreyDGL/PentestGPT](https://github.com/GreyDGL/PentestGPT)'s split of a
monolithic LLM call into cooperating modules (pattern only — no code vendored):
- **Generator** = `internal/llm` crawl + bench codegen.
- **Reasoner** = the skeptical cross-check + adjudication (with reasoning effort).
- **Parser** = `internal/gate`, the deterministic verdict logic.
- **Persistent memory** = the hash-chained ledger (cross-run novelty); **bounded iteration**
  = one finding per run + the budget cap.

## The strict gate (every stage must pass; else discard, post nothing)
1. **Crawl** real sources (web-enabled model) → in-scope candidates with quoted sources.
2. **Novelty** — reject if already in the repo (`git grep` the candidate's `signature`) or
   in the ledger.
3. **Independent cross-check** — ≥2 authoritative sources from distinct origins (no
   citation-chains).
4. **Benchmark** — compile + run a self-contained micro-bench (`rustc -O` / `cc -O2`); it
   must print `OPTITRON_BENCH baseline=<ns> optimized=<ns>` and beat the delta threshold.
5. **Certainty** — adjudicated `confidence ≥ 0.80`, `novel`, hallucination-risk ≠ high.

## Build / commands
```bash
cd tools/optitron
go build ./cmd/optitron                       # or: go run ./cmd/optitron <cmd>
go test ./...                                  # ledger, gate, bench (real compile) unit tests

./optitron crawl --dry-run                     # build prompts + cost estimate, no network
./optitron crawl --once --budget-total 4       # one real cycle (needs OPENROUTER_API_KEY)
./optitron events --replay                     # verify the hash-chain + list findings
```
Set `OPTITRON_DRY_ACT=1` to run the full pipeline but **not** create the issue / stage toots
(safe live test). `OPTITRON_RUN_BENCH=0` disables benchmark execution (then nothing can pass
the gate — by design).

## Config / env
- `tools/optitron/sources.json` — crawl source hint + thresholds (`min_sources`,
  `min_confidence`, `min_bench_delta`).
- Models (override; **June-2026 defaults**): `OPTITRON_CRAWL_MODEL`
  (`openai/gpt-5.5:online`), `OPTITRON_VERIFY_MODEL` (`anthropic/claude-opus-4.8` — the
  frontier reasoner on the anti-hallucination gate), `OPTITRON_BENCH_MODEL`
  (`deepseek/deepseek-v4-flash`; swap to `anthropic/claude-fable-5` for stronger codegen).
- `OPTITRON_BASE_URL` (OpenRouter v1 root), `OPTITRON_BUDGET` / `--budget-total`,
  `OPTITRON_REPO` (repo-root override; otherwise auto-detected by walking up to `.git`).
- Secrets (in the `ci` GitHub Environment): `OPENROUTER_API_KEY` (required), `LANGFUSE_*`
  (optional tracing), `GH_TOKEN` (issue creation); Mastodon/Telegram handled by the
  social-post / telegram-post workflows.

## Manual trigger — double confirmation (gated, DX-preserving)
The daily `schedule` runs automatically. A **manual** run via `workflow_dispatch` requires
**two independent confirmations**, with no extra infra:
1. **Typed gate** — you must enter `confirm: RUN` when dispatching the workflow.
2. **Environment approval** — the run pauses on the protected **`optitron-manual`** GitHub
   Environment until a **required reviewer** approves it (a second human click), *before* any
   model spend. The crawl itself then runs in the `ci` Environment (where the secrets live).

**One-time owner setup:** GitHub → *Settings → Environments → New environment* →
`optitron-manual` → enable **Required reviewers** (add yourself); optionally add a wait timer
for a cooldown. (No secrets needed on this environment — it's purely the approval gate.)

## Daily cost (pessimistic over-estimate)
Bounded by a non-bypassable `--budget-total` cap (**default $4.00/run**, checked before every
call across all goroutines). Realistic ~$1–3/day; **over-guess ceiling ≤ ~$4/day** (the cap);
**$0** when the API key is absent (guard no-op) or nothing crawls.

## State
- `state/events.jsonl` — append-only, **hash-chained**, committed (the findings memory +
  audit trail; events: `crawl`, `rejected{reason}`, `found{issue,confidence,delta}`, `none`,
  `error`). `events --replay` verifies the chain.
- `state/status.json` — derived cache (gitignored).

## Layout
```
tools/optitron/
  cmd/optitron/         CLI entrypoint (crawl, events)
  internal/ledger/      single-writer hash-chained ledger (+ tests)
  internal/gate/        pure deterministic gate: scope, independence, bench parse, pass/reject (+ tests)
  internal/llm/         Eino OpenRouter wrapper, strict schemas, prompt builders
  internal/run/         orchestration: config, budget guard, novelty, bench runner, act, pipeline (+ tests)
  cmd/introspect/       fleet-introspect — sibling agent (reuses internal/ledger + internal/llm)
  internal/introspect/  langfuse query, telemetry digest + economy, detect→ideate→review loop (+ tests)
  sources.json · PURPOSE.md · state/{events,introspect}.jsonl
```

Scheduled / gated by [`.github/workflows/optitron-crawl.yml`](../../.github/workflows/optitron-crawl.yml).

## Sibling agent — `cmd/introspect` (fleet-introspect)

This module also hosts **fleet-introspect**, a daily self-improvement loop that **reuses this
core** (`internal/ledger` + `internal/llm`). It mines the fleet's own Langfuse telemetry (+ the
hash-chained ledgers — **ralph's is read-only**) over the last ≤2 days, auto-detects the most
salient finding, ideates one novel solution, **always reviews** it behind a fail-closed gate, hands
a survivor to swe_af via an `agent` issue, and reports the fleet **economy** (real spend → normal
day/week/month projection). Own ledger: `state/introspect.jsonl`. Design:
[`docs/superpowers/specs/2026-06-14-fleet-introspect-design.md`](../../docs/superpowers/specs/2026-06-14-fleet-introspect-design.md).

```bash
go run ./cmd/introspect run --dry-run          # build the telemetry digest + economy, no model calls
go run ./cmd/introspect run --once --budget-total 3 [--focus "..."]
go run ./cmd/introspect events --replay        # verify the introspect ledger chain
```
Models (env-overridable): `INTROSPECT_DETECT_MODEL` (deepseek-v4-flash), `INTROSPECT_{IDEATE,REVIEW}_MODEL`
(claude-opus-4.8). Gated daily by [`.github/workflows/fleet-introspect.yml`](../../.github/workflows/fleet-introspect.yml)
(daily schedule + a double-confirmed manual dispatch via the `introspect-manual` Environment).
