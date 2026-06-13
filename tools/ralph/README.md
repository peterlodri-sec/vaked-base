# ralph — autonomous concept-track decision loop

`ralph` is a self-pacing, **controllable** strategy agent. It continuously
surfaces the single most important open **decision** for each of Vaked's hard
design areas — one cheap OpenRouter model pinned per area — and records it to an
**immutable, human-ratified** decision log, so the project's direction is
reasoned about every day, for pennies, without burning a human's attention or an
LLM context window.

It is also the **dogfood**: the loop embodies Vaked's three core theories before
they land in the language — **parallel** (round-robins independent tracks),
**immutable** (append-only, hash-chained event log as the state-of-record), and
**control** (stop / slow / step at runtime). See [`PURPOSE.md`](PURPOSE.md) for
the research goal and metrics.

> Design: [`docs/superpowers/specs/2026-06-12-ralph-tracks-design.md`](../../docs/superpowers/specs/2026-06-12-ralph-tracks-design.md) ·
> Plan: [`docs/superpowers/plans/2026-06-12-ralph-tracks.md`](../../docs/superpowers/plans/2026-06-12-ralph-tracks.md) ·
> Tracking: issue #34

## Tracks

A **track** is a concept area inside `vaked-base`, pinned to one model — so the
model is the experiment variable (which model advances which class of design
problem well enough to ratify?). Configured in [`tracks.json`](tracks.json):

| track | label | model | focus |
|-------|-------|-------|-------|
| `base-language-spec` | `track:language` | `qwen/qwen3-235b-a22b-thinking-2507` | grammar, schema, examples, core design (anchor/control model) |
| `graph-concept` | `track:graph` | `deepseek/deepseek-v4-flash` | the typed semantic graph — LPG, type system, lowering |
| `mlir-topology` | `track:mlir` | `xiaomi/mimo-v2.5` | MLIR topology-compilation dialects (0013) + memory primitive (0014) |
| `hcp-litany` | `track:protocol` | `tencent/hy3-preview` | the HCP / Litany wire protocol (RFCs) |

Each iteration is **two-stage, one model**: stage 1 ranks candidate decisions
(reasoning + JSON), stage 2 writes the chosen decision entry. Context is scoped
to the track — label-filtered home-repo issues, the track's doc globs, and a
path-scoped `git log`.

## Commands

Stdlib-only; no install needed to run locally.

```bash
# One decision for a named track (writes docs/decisions/<track>.ralph-log.md)
python3 tools/ralph/ralph.py decide --track graph-concept

# One decision for the NEXT track (rotation derived from the event ledger) —
# this is what the CI host calls each tick
python3 tools/ralph/ralph.py decide --next-track

# Build prompts + a cost estimate without any network/key
python3 tools/ralph/ralph.py decide --track base-language-spec --dry-run

# Long-running supervisor: round-robin all tracks, budget-capped
python3 tools/ralph/ralph.py run --interval 900 --budget-total 2.00

# Live terminal dashboard (reads status.json) — what's running, decided, spent
python3 tools/ralph/ralph.py watch

# Verify the event chain / replay reconstructed state
python3 tools/ralph/ralph.py events --replay

# Human ratify status: per-track decisions, verdicts, ratify-rate, backlog
python3 tools/ralph/ralph.py ratify
```

`run` is track-mode by default; `--repo-mode` selects the deprecated whole-repo
round-robin. Live control while `run` is going: write `state/control.json`
(`{"paused": true}`, `{"interval": 60}`, or `{"paused": true, "step": true}` for
a one-shot tick).

## State

| File | Role | Committed? |
|------|------|-----------|
| `state/events.jsonl` | **state-of-record** — append-only, hash-chained event ledger (rotation pointer + cumulative spend + audit trail) | **yes** |
| `state/status.json` | derived live cache the dashboard reads | no (gitignored) |
| `docs/decisions/<track>.ralph-log.md` | per-track advisory decision log (appended, never rewritten) | yes |
| `docs/decisions/<track>.ratify-log.md` | per-track **human** verdicts (one append per decision) | yes |

The ledger is authoritative: a fresh/stateless run reconciles its rotation
pointer and cumulative spend from `events.jsonl`, so it resumes correctly even
when `status.json` is missing or stale.

## Budget & safety

- **Non-bypassable backstops:** a cumulative USD cap (`--budget-total`, default
  `$2.00`) is checked before every call; optional `--max-iters`. Per-iteration
  cost is ~$0.002–0.005, so the cap is the real ceiling.
- **Read-only** on all inputs; the only writes are appends to the decision logs
  and `events.jsonl`.
- **Keys** from env only (`OPENROUTER_API_KEY`, or `RALPH_API_KEY`), never logged.

## Endpoint / privacy

By default a live iteration sends `vaked-base` content (issue bodies, docs, git
log) to **OpenRouter** — a third party. Override the endpoint to keep content
in-boundary: `--base-url` / `RALPH_BASE_URL` point at a self-hosted,
OpenAI-compatible inference host; `RALPH_API_KEY` takes precedence over
`OPENROUTER_API_KEY`. (Precedence: `--base-url` > `RALPH_BASE_URL` > OpenRouter.)

## CI host

[`.github/workflows/ralph-tracks.yml`](../../.github/workflows/ralph-tracks.yml)
runs one `decide --next-track` tick on a schedule (`0 */3 * * *`) and commits the
appended log + `events.jsonl`. It is **safe to merge before secrets exist** — a
**guard step skips the decision** (the job succeeds, doing nothing) whenever
neither `OPENROUTER_API_KEY` nor `RALPH_API_KEY` is set. Run it on demand any
time via **workflow_dispatch**.

Secrets live in the **`ci` GitHub Environment** — the job declares
`environment: ci`, which is what makes `secrets.*` resolve (environment secrets
are invisible to jobs that don't reference the environment). To enable the loop,
add `OPENROUTER_API_KEY` to that environment (and optionally
`RALPH_BASE_URL`/`RALPH_API_KEY`, `LANGFUSE_*`, `MASTODON_ACCESS_TOKEN`). If the
`ci` environment has required-reviewer protection rules, scheduled runs will wait
for approval — clear those rules for the loop to run unattended.

## Announcements (optional Mastodon)

`ralph announce` posts the latest decision to a Mastodon instance (default: the
private, self-hosted `https://social.crabcc.app`). It runs as its **own CI step
after the decision is committed**, so it can fail loudly without ever dropping a
decision.

- **Content:** a short **caveman-style** toot written by `openai/gpt-oss-120b`
  (falls back to a deterministic template if generation fails), capped at **470
  chars**, with code-controlled hashtags (`#vaked #ralph #<track>`). Only a
  summary (track, title, model, cost) — **never the full decision body**.
- **Idempotent:** one toot per decision id (`Idempotency-Key` + an `announced`
  event in the ledger), so re-runs/retries don't double-post.
- **Fail fast + loud:** a posting failure prints PII-safe debug (host, id, char
  count, visibility — never the token) **before and after**, emits a CI
  `::error::` annotation, **opens one deduped GitHub issue** (`ralph: Mastodon
  announce failing` — at most one open per repo), and exits non-zero (red CI).
  The decision is already committed, and the announcement retries each tick until
  it succeeds (then close the issue).
- **No-op** without `MASTODON_ACCESS_TOKEN`. Config: `MASTODON_BASE_URL`
  (instance), `MASTODON_VISIBILITY` (env *variable*, default `unlisted`).
  Generation uses the same OpenRouter/`--base-url` endpoint as `decide`.

## Observability (optional Langfuse tracing)

Tracing is an **optional extra** — the loop is stdlib-only and runs identically
without it. Each LLM call is wrapped in a [Langfuse](https://langfuse.com)
generation span recording the model, input, output, token usage, computed USD
cost, and latency, tagged with the track + stage. It's a no-op unless **both**
the SDK is installed (the `tracing` extra) and `LANGFUSE_PUBLIC_KEY` is set:

```bash
LANGFUSE_PUBLIC_KEY=pk-… LANGFUSE_SECRET_KEY=sk-… LANGFUSE_HOST=https://your-langfuse \
  uv run --project tools/ralph --extra tracing tools/ralph/ralph.py decide --next-track
```

In CI, set the `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`
repository secrets — the workflow then auto-enables the `tracing` extra. Tracing
failures are swallowed: observability never breaks the loop.

## Status / roadmap

- ✅ Phase 1–2: config + pure core, per-track scoped context, single-model
  two-stage `decide`, `--track`/`--next-track` rotation, supervisor + dashboard.
- ✅ Phase 3: CI cron host + these docs.
- ✅ Phase 4: optional Langfuse tracing (above).
- ✅ Phase 5: the ratify workflow — [`docs/decisions/RATIFY.md`](../../docs/decisions/RATIFY.md),
  `ralph ratify` (per-track ratify-rate + backlog), and override-reason feedback
  into stage 1.

## Ratify workflow

The model proposes; a human disposes. A few times a day the loop appends a
decision to `docs/decisions/<track>.ralph-log.md`; a human records a one-line
**ratify / override / defer** verdict in `<track>.ratify-log.md` (never editing
the decision — ratification is a separate append). Recent **override** reasons
are fed back into the next stage-1 prompt, so the stream drifts toward what the
human ratifies; `ralph ratify` tracks the **ratify-rate** (the core metric from
[`PURPOSE.md`](PURPOSE.md)). Full contributor guide:
[`docs/decisions/RATIFY.md`](../../docs/decisions/RATIFY.md).

Tests: `python3 tools/ralph/test_ralph.py` (stdlib runner; the network stages are
not unit-tested live, the pure pieces are).
