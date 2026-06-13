# vaked-optitron — the optimization crawler

A daily, **abstain-by-default** crawler that surfaces **one** novel, proven,
independently-confirmed **compiler / allocator / Zig / Rust / Vaked** optimization — or
nothing. On a finding it opens a GitHub issue labelled **`agent`** (the `swe_af` workflow
trigger) and announces to Mastodon + Telegram. Declarative spec:
[`.claude/skills/vaked-optitron/SKILL.md`](../../.claude/skills/vaked-optitron/SKILL.md)
(this Python harness loads it as its system prompt).

Archetype: **Python cron loop** (prototype: [ralph](../ralph/README.md)) — stdlib-first,
append-only hash-chained ledger, guards on secrets, advisory (any failure logs and exits 0).

## The strict gate (every stage must pass; else discard, post nothing)
1. **Crawl** real sources (web-enabled model) → in-scope candidates with quoted sources.
2. **Novelty** — reject if already in the repo (`git grep` the candidate's `signature`) or
   in the ledger.
3. **Independent cross-check** — ≥2 authoritative sources from distinct origins (no
   citation-chains).
4. **Benchmark** — compile + run a self-contained micro-bench (`rustc -O` / `cc -O2`); it
   must print `OPTITRON_BENCH baseline=<ns> optimized=<ns>` and beat the delta threshold.
5. **Certainty** — adjudicated `confidence ≥ 0.80`, `novel`, hallucination-risk ≠ high.

## Commands
```bash
python3 tools/optitron/optitron.py crawl --dry-run      # build prompts + cost estimate, no network
python3 tools/optitron/optitron.py crawl --once --budget-total 4   # one real cycle (needs OPENROUTER_API_KEY)
python3 tools/optitron/optitron.py events --replay      # verify the hash-chain + list findings
```
Set `OPTITRON_DRY_ACT=1` to run the full pipeline but **not** create the issue / stage toots
(safe live test). `OPTITRON_RUN_BENCH=0` disables benchmark execution (then nothing can pass
the gate — by design).

## Config / env
- `tools/optitron/sources.json` — crawl source hint + thresholds (`min_sources`,
  `min_confidence`, `min_bench_delta`).
- Models (override): `OPTITRON_CRAWL_MODEL` (default `openai/gpt-oss-120b:online`),
  `OPTITRON_VERIFY_MODEL` (`qwen/qwen3-235b-a22b-thinking-2507`), `OPTITRON_BENCH_MODEL`
  (`deepseek/deepseek-v4-flash`).
- Secrets (in the `ci` GitHub Environment): `OPENROUTER_API_KEY` (required), `LANGFUSE_*`
  (optional tracing), `GH_TOKEN` (issue creation), Mastodon/Telegram handled by the
  social-post / telegram-post workflows.

## Daily cost (pessimistic over-estimate)
Bounded by a non-bypassable `--budget-total` cap (**default $4.00/run**, checked before every
call). Realistic ~$1–3/day; **over-guess ceiling ≤ ~$4/day** (the cap); **$0** when the API
key is absent (guard no-op) or nothing crawls.

## State
- `state/events.jsonl` — append-only, **hash-chained**, committed (the findings memory +
  audit trail; events: `crawl`, `rejected{reason}`, `found{issue,confidence,delta}`, `none`,
  `error`). `events --replay` verifies the chain.
- `state/status.json` — derived cache (gitignored).

Scheduled by [`.github/workflows/optitron-crawl.yml`](../../.github/workflows/optitron-crawl.yml).
