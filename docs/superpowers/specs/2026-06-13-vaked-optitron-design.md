# vaked-optitron — a daily, abstain-by-default optimization crawler (design)

## Status

Design (2026-06-13). **Tooling**, not the Vaked language — no grammar gate.
Owner-approved scope. New agent in the **Python cron-loop** archetype; reuses the
ralph idioms (hash-chained ledger, OpenRouter-via-urllib, optional Langfuse, guard +
advisory) almost entirely — this doc records the deltas.

## Why

The fleet decides (ralph), reviews (pr-review), and merges (yardmaster) but never
**hunts for concrete engineering wins**. optitron fills that gap with a single, narrow
mandate: each day, surface **one** novel, proven, independently-confirmed optimization
in the stack's hot path — **compiler / allocator / Zig / Rust / Vaked** — or nothing.
The hard part is not finding ideas; it's *not* shipping hallucinated or already-known
ones. So the whole design is a **fail-closed gate**, and **abstaining is the intended
outcome** on the vast majority of runs.

## What it is

A singularity-native crawler **declared** in `.claude/skills/vaked-optitron/SKILL.md`
(the 3D-agnostic source of truth) and **projected** into one concrete runtime,
`tools/optitron/` (Python), which loads the skill as its system prompt. Any future
runtime can reuse the declaration unchanged.

## Pipeline (each stage gates the next; budget-capped before every model call)

1. **Crawl** — a web-enabled OpenRouter model returns in-scope candidates with quoted,
   real sources + a grep-able `signature`. No real find ⇒ nothing.
2. **Novelty** — deterministic: `git grep` the `signature` (reject if already applied)
   and ledger dedupe (reject if already found). Plus source-independence: ≥2 distinct
   registrable domains *and* orgs (kills citation-chains).
3. **Cross-check** — a skeptical reasoning model confirms ≥2 independent sources each
   support the claim via exact quotes.
4. **Benchmark** — a coder model emits a self-contained micro-bench (`rustc -O`/`cc -O2`)
   printing `OPTITRON_BENCH baseline=<ns> optimized=<ns>`; the harness **compiles + runs**
   it and requires a measured delta ≥ threshold. No green run ⇒ discard.
5. **Adjudicate** — `confidence ∈ [0,1]`; only `≥ 0.80`, `novel`, risk ≠ `high` survives.

## On a survivor — hand off, don't implement

Open a GitHub issue labelled **`agent`** — the documented `swe_af` trigger
(`vaked/examples/agentfield-swe.vaked`: `on = "github.issue.labeled:agent"`) — with the
mechanism, independent sources + quotes, reproduced numbers, and target files. swe_af
(plan → code → review → publish) implements. Announce to Mastodon + Telegram via the
`.github/social/*` staging files. Nothing found ⇒ CI log only.

## State & cost

Append-only hash-chained ledger `tools/optitron/state/events.jsonl` (findings memory +
tamper-evidence; `crawl`/`rejected`/`found`/`none`/`error`). Non-bypassable
`--budget-total` cap (default **$4.00/run**), checked before each call — pessimistic daily
ceiling ≤ ~$4, realistic ~$1–3, $0 when the key is absent.

## Files

`.claude/skills/vaked-optitron/SKILL.md` · `tools/optitron/{optitron.py,optitroncore.py,
sources.json,PURPOSE.md,README.md,state/}` · `.github/workflows/optitron-crawl.yml`.

## Open questions

- Tune `min_bench_delta` / `min_confidence` from real runs (start strict: 10% / 0.80).
- A second, formal-proof path for optimizations that resist micro-benchmarking.
- Whether to also project the skill onto a headless-agent runtime later (the declaration
  already supports it).
