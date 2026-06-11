# ralph-decide — a budget MoE decision/strategy loop (design)

## Status

Design (approved brainstorm, 2026-06-11). This is **tooling**, not the Vaked
language — no grammar/issue gate (cf. `tools/vaked-run`). Owner-approved.

## Purpose

A small autonomous "Ralph loop": each iteration reads the project's current
state and the prior decisions, surfaces (or materially advances) the single most
important open **strategic decision**, and appends a structured, dated entry to
an **advisory** decisions log that a human ratifies. It runs on cheap MoE models
via OpenRouter so it can be run often for ~pennies.

> "Ralph" = re-invoke an agent with a fixed task on a loop, persisting state
> between iterations so it makes incremental progress. Here the persisted state
> is the decisions log itself.

## Non-goals

- **Not** a code-writing agent. Read-only except *appending* to the log.
- **Not** a Claude Code loop — standalone, talks to OpenRouter directly.
- No tool-calling, no repo mutation, no git writes, no network beyond OpenRouter
  (+ local `gh`/`git` *reads* for context).

## Run model

**Bounded batch + budget cap.** A standalone, **stdlib-only** Python script
(`tools/ralph-decide.py`, no pip deps — matches the `vakedc` ethos, `urllib` for
HTTP). `OPENROUTER_API_KEY` is read from the environment. It runs `--max-iters`
iterations (default 6) then stops, or stops earlier when cumulative cost reaches
`--budget` (default $0.25). Re-run on demand; wrap in `cron`/`while` for
continuous operation.

## Iteration — two stages, two models

Each iteration makes **two** OpenRouter chat-completions calls.

### Stage 1 — surface & rank  (`qwen/qwen3-235b-a22b-thinking-2507`)

Reads a **compact** project state (open-issue titles+bodies, recent `git log`,
short digests of key docs, and the **titles** of prior log entries) and returns a
ranked list of candidate decisions. The thinking MoE is used here because ranking
"what matters most right now" is the reasoning-heavy step.

Request body (per the OpenRouter param surface):

- `model`, `messages`
- `reasoning`: `{ "enabled": true, "effort": "medium" }` (thinking tokens on)
- `response_format`: JSON schema →
  `{ "candidates": [ { "title": str, "why_now": str, "urgency": int (1-5), "addressed": bool } ] }`
- `temperature`: 0.4, `top_p`: 0.95
- `seed`: `--seed` (default fixed, e.g. 42) for reproducible runs
- `max_tokens`: ~2000 (response) + the reasoning budget

**Selection (deterministic, in-script):** pick the highest-`urgency`
`addressed=false` candidate (ties → first in list). If every candidate is
`addressed=true`, pick the highest-`urgency` one to *advance* with new info.

### Stage 2 — deep-dive  (`deepseek/deepseek-v4-flash`, 1M ctx)

Given the chosen candidate **plus the full project context** — its 1M window
holds everything: full issue bodies, the full `git log` window, full doc text,
and the **entire** prior log — it writes the detailed decision entry.

Request body:

- `model`, `messages`
- `temperature`: 0.3, `top_p`: 0.95
- `max_tokens`: ~1800
- (no `reasoning` — stage 2 is synthesis/writing, not ranking; no `tools`)

Output: the structured markdown entry (below).

## Decision log

`docs/decisions/ralph-log.md`. A header (committed on first run) marks it
**machine-generated / advisory**; entries are **appended, never rewritten**.
Continuity: prior entry *titles* feed Stage 1 (avoid repeats); the *full* log
feeds Stage 2.

Entry format:

```
## 2026-06-11 — Decision #N: <title>
- **Models:** stage1 qwen3-235b-a22b-thinking · stage2 deepseek-v4-flash
- **Context snapshot:** HEAD <sha>, <K> open issues
- **Decision / question:** …
- **Options:** …
- **Recommendation:** …
- **Risks:** …
- **Next actions:** …
- **Confidence:** low | med | high
```

## Budget & accounting

Each response carries `usage` (prompt/completion tokens). Cost per call =
`prompt_tokens × in_price + completion_tokens × out_price`, per-model
(defaults: qwen `$0.10/$0.10`, deepseek-v4-flash `$0.098/$0.197` per 1M —
pulled from the live OpenRouter `/models` endpoint at startup, falling back to
these hardcoded values with a "refresh me" note). Maintain a cumulative total;
**before each call**, if cumulative ≥ `--budget`, stop. Print a per-iteration and
final cost summary.

## CLI

```
tools/ralph-decide.py
  [--max-iters 6] [--budget 0.25]
  [--stage1-model qwen/qwen3-235b-a22b-thinking-2507]
  [--stage2-model deepseek/deepseek-v4-flash]
  [--log docs/decisions/ralph-log.md]
  [--seed 42]
  [--git-log-window 30]      # commits of context
  [--dry-run]                # build + print both prompts and a cost ESTIMATE; no API calls
```

## Safety

- Read-only except **append** to the log. No `exec`, no git writes, no edits.
- API key from env only; never logged or echoed.
- The iter + budget caps are non-bypassable backstops (checked before every call).
- Network: only `https://openrouter.ai`; context comes from local `gh`/`git`/file reads.

## Error handling

- Missing `OPENROUTER_API_KEY` → clear error, exit non-zero.
- OpenRouter non-200 / rate-limit → bounded retry with backoff (e.g. 3 tries),
  then **skip that iteration** (log a one-line note to stderr) rather than crash.
- Stage-1 JSON parse failure → one "reformat as valid JSON" retry; if still bad,
  skip the iteration with a warning (no log entry written).
- `gh`/`git` unavailable → degrade gracefully: skip that context source, note it
  in the prompt ("(issues unavailable)") rather than failing.

## Testing

- **`--dry-run` smoke** (no network): builds both prompts, prints a cost
  estimate, writes nothing to the log. Exit 0.
- **Selection unit test**: feed a fixed Stage-1 JSON fixture →
  assert the highest-urgency `addressed=false` candidate is chosen (and the
  all-addressed fallback).
- **Budget-cap test**: `--budget 0` → zero API calls, clean exit, no log write.
- **Cost-math test**: a known `usage` + price → expected USD (pure function).

(The two network stages are not unit-tested against the live API; the pure
pieces — selection, cost math, prompt building, log append — are.)

## Files

| File | Role |
|------|------|
| `tools/ralph-decide.py` | the script (stdlib-only) |
| `docs/decisions/ralph-log.md` | the advisory decisions log (header committed; entries appended) |
| `tests/` | selection + cost-math + dry-run smoke |

## Cost envelope (sanity)

At ~10–20k input + ~3k output tokens/iteration across both models, an iteration
is roughly **$0.002–0.005**; the default 6-iteration / $0.25 run is comfortably
bounded (the budget cap, not the iteration count, is the real ceiling).
