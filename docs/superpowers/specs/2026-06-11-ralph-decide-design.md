# ralph — a budget MoE decision/strategy loop with supervisor + eye dashboard (design)

## Status

Design (approved brainstorm, 2026-06-11). **Tooling**, not the Vaked language —
no grammar/issue gate. Owner-approved scope.

## Purpose

An always-on "Ralph loop" that keeps **at least one** decision agent running,
**round-robining** across the fleet's repos. Each iteration reads a repo's
current state + its prior decisions, surfaces (or advances) the single most
important open **strategic decision** for that repo, and appends a structured,
dated entry to that repo's **advisory** decisions log (human-ratified). It runs
on cheap MoE models via OpenRouter, and an **eye dashboard** (terminal live
view) shows what's running, what it decided, and what it has spent.

> "Ralph" = re-invoke an agent with a fixed task on a loop, persisting state
> (the decisions log) between iterations so it makes incremental progress.

## Targets (config-driven, extensible)

A repo list — start with three, add agentfield components one by one later:

| name | path | gh repo |
|------|------|---------|
| `vaked-base` | `~/workspace/peterlodri-sec/vaked-base` | `peterlodri-sec/vaked-base` |
| `crabcc` | `~/workspace/peterlodri-sec/crabcc` | `crabcc-labs/crabcc` |
| `agentfield-stack` | `~/workspace/peterlodri-sec/agentfield-stack` | `peterlodri-sec/agentfield-stack` |

Config lives in `tools/ralph/repos.json` (name, path, gh, optional `subdir` for
later per-agent/module targets). Adding a target = one JSON entry.

## Non-goals

- **Not** a code-writing agent. Read-only on all target repos except *appending*
  to decision logs (which live in the **home** repo, see State).
- **Not** a Claude Code loop — standalone, talks to OpenRouter directly.
- No tool-calling, no git writes, no network beyond OpenRouter (+ local
  `gh`/`git`/file *reads* per target).

## Components

One stdlib-only script, `tools/ralph/ralph.py` (no pip deps; `urllib` for HTTP),
with three subcommands — each a small, independently-testable unit:

1. **`ralph decide --repo <name>`** — run **one iteration** for one repo (the
   core, two-stage; below). Pure-ish: reads state, calls OpenRouter, appends one
   log entry, returns a result record (iteration #, decision title, cost).
2. **`ralph run`** — the **supervisor**: a continuous round-robin that keeps
   exactly one loop alive at a time, cycling the repo list, pacing with
   `--interval`, and stopping only on the cumulative **budget backstop** or
   Ctrl-C. Writes `status.json` after every step.
3. **`ralph watch`** — the **eye dashboard**: a refreshing terminal table read
   from `status.json` + log tails. No browser.

## Iteration — two stages, two models (`ralph decide`)

### Stage 1 — surface & rank  (`qwen/qwen3-235b-a22b-thinking-2507`)

Reads a **compact** state for the target repo (open-issue titles+bodies, recent
`git log`, short digests of key docs, and the **titles** of that repo's prior log
entries) → a ranked candidate list. The thinking MoE does the reasoning-heavy
"what matters most now" step. Request body:

- `model`, `messages`
- `reasoning`: `{ "enabled": true, "effort": "medium" }`
- `response_format`: JSON schema →
  `{ "candidates": [ { "title", "why_now", "urgency": 1-5, "addressed": bool } ] }`
- `temperature` 0.4, `top_p` 0.95, `seed` (`--seed`, default 42), `max_tokens` ~2000

**Selection (in-script, deterministic):** highest-`urgency` `addressed=false`
(ties → first); if all addressed, highest-`urgency` to advance with new info.

### Stage 2 — deep-dive  (`deepseek/deepseek-v4-flash`, 1M ctx)

Given the chosen candidate **+ the full state for that repo** (full issue bodies,
full `git log` window, full doc text, that repo's **entire** prior log — the 1M
window holds it) → the detailed entry. `temperature` 0.3, `top_p` 0.95,
`max_tokens` ~1800. No `reasoning`/`tools`.

## State (all in the HOME repo — read-only on the others)

The tool's home is `vaked-base`. **No writes to crabcc/agentfield-stack** — their
decision logs live here:

- `docs/decisions/<repo>.ralph-log.md` — one advisory log per target repo;
  header marks it machine-generated; entries **appended, never rewritten**.
- `tools/ralph/state/status.json` — the live supervisor state the dashboard reads
  (current repo, iteration, last decision title per repo, per-repo + total spend,
  started-at, last-step-at, status, next repo).

Entry format (per log):

```
## 2026-06-11 — Decision #N: <title>
- **Repo:** crabcc · **Models:** stage1 qwen3-235b-a22b-thinking · stage2 deepseek-v4-flash
- **Context snapshot:** HEAD <sha>, <K> open issues
- **Decision / question:** …
- **Options:** …  **Recommendation:** …  **Risks:** …
- **Next actions:** …  **Confidence:** low|med|high
```

Continuity: prior entry *titles* feed Stage 1 (avoid repeats); the *full* per-repo
log feeds Stage 2.

## Supervisor (`ralph run`) — "always ≥ 1 running"

Continuous loop: pick next repo (round-robin) → `decide` one iteration → update
`status.json` → `sleep(--interval)` → repeat. Stops only on the cumulative
**budget backstop** (`--budget-total`) or SIGINT (clean shutdown writes a final
status). Pacing (`--interval`, default 900s/15min) keeps spend low and gives
humans time to ratify. Exactly one iteration runs at a time (no concurrency).

Backstops (non-bypassable, checked before each call): cumulative USD cap
(`--budget-total`, default $2.00) and an optional max-iterations
(`--max-iters`, default unbounded for `run`). On restart it resumes spend +
round-robin position from `status.json`.

## Eye dashboard (`ralph watch`)

A `watch`-style terminal view (redraw every `--refresh`, default 3s) reading
`status.json` + the tail of each log. Columns/sections:

- **Loop:** ● running / ○ idle, current repo, iteration #, seconds since last step.
- **Per repo:** last decision title, entry count, last-run time, spend.
- **Spend:** total USD vs `--budget-total` (a simple bar), today's count.
- **Recent decisions:** last ~5 titles across repos with repo + timestamp.

ASCII only (no deps). If `status.json` is missing/stale → "no supervisor running"
(this is how you see whether the "always-on" loop is actually alive).

## Budget & accounting

Each response carries `usage`. Cost/call = `prompt_tok × in_price +
completion_tok × out_price`, per-model (defaults qwen `$0.10/$0.10`,
deepseek-v4-flash `$0.098/$0.197` per 1M — fetched from OpenRouter `/models` at
startup, hardcoded fallback with a "refresh" note). Cumulative total persists in
`status.json`; checked before every call.

## CLI

```
tools/ralph/ralph.py decide --repo <name> [--seed 42] [--dry-run]
tools/ralph/ralph.py run    [--interval 900] [--budget-total 2.00]
                            [--repos repos.json] [--max-iters N]
tools/ralph/ralph.py watch  [--refresh 3]
# shared: [--stage1-model …] [--stage2-model …] [--git-log-window 30]
```

`--dry-run` (on `decide`): build + print both prompts and a cost estimate; no API
call, no log write.

## Privacy / endpoint (data governance)

A live iteration sends **private-repo content** (issue bodies, README/CLAUDE.md,
git log) to whatever endpoint is configured. By default that is **OpenRouter**, a
third party outside the trust boundary — accept this consciously, or override the
endpoint. Precedence: `--base-url` > `RALPH_BASE_URL` env > OpenRouter default;
key: `RALPH_API_KEY` > `OPENROUTER_API_KEY`. Point `--base-url` /`RALPH_BASE_URL`
at a **self-hosted, trust-boundary OpenAI-compatible endpoint** (e.g.
`agentfield-inference-host`) to keep private content local. (A future
`--titles-only` context mode could further reduce what leaves the box.)

## Safety

- Read-only on every target repo; the only writes are appends to logs +
  `status.json`, both under `vaked-base`.
- API key (`OPENROUTER_API_KEY`) from env only; never logged.
- Budget + (optional) iteration caps are non-bypassable backstops.
- Network: only `https://openrouter.ai`; context is local `gh`/`git`/file reads.
- `gh` against private repos (crabcc) uses the existing `gh` auth.

## Error handling

- Missing `OPENROUTER_API_KEY` → clear error, exit non-zero.
- OpenRouter non-200 / rate-limit → bounded retry+backoff (3 tries), then skip
  that iteration (note to status + stderr), supervisor continues to next repo.
- Stage-1 JSON parse failure → one reformat retry; else skip iteration (warn).
- A target repo path/`gh` unavailable → skip that repo this cycle, note it;
  supervisor keeps the others running ("always ≥1").
- SIGINT → finish the in-flight call's accounting, write final status, exit 0.

## Testing

- **`decide --dry-run`** smoke (no network): builds prompts, prints estimate,
  writes nothing.
- **Selection unit test**: fixed Stage-1 JSON → asserts highest-urgency-unaddressed
  pick + all-addressed fallback.
- **Cost-math test**: known `usage` + price → expected USD (pure).
- **Round-robin test**: next-repo advances and wraps; skips an unavailable repo.
- **Budget backstop test**: `--budget-total 0` → zero calls, clean exit.
- **status.json round-trip**: supervisor writes → `watch` parses (no live API).

(The two network stages aren't unit-tested live; the pure pieces are.)

## Files

| File | Role |
|------|------|
| `tools/ralph/ralph.py` | the script (decide / run / watch), stdlib-only |
| `tools/ralph/repos.json` | target repo list (extensible) |
| `tools/ralph/state/status.json` | live supervisor state (gitignored) |
| `docs/decisions/<repo>.ralph-log.md` | per-repo advisory decision logs |
| `tests/` | selection · cost-math · round-robin · dry-run · status round-trip |

## Build order (phases)

1. **`decide`** (one repo, two-stage, log append, `--dry-run`) + its unit tests.
2. **`run`** supervisor (round-robin, budget backstop, `status.json`, pacing).
3. **`watch`** dashboard.
4. Grow `repos.json` with agentfield-stack components one at a time.

## Cost envelope (sanity)

~10–20k in + ~3k out/iteration across both models ≈ **$0.002–0.005/iteration**.
At `--interval 900` (4/hr) that's well under a cent/hour per repo; the
`--budget-total` cap (default $2.00) is the real ceiling and bounds a runaway.
