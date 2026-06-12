# ralph tracks — per-model concept loops, CI-cron host, Langfuse, ratify workflow (design)

## Status

Design (brainstorm, 2026-06-12). **Tooling**, not the Vaked language — no
grammar gate. Owner-approved scope. Evolves the approved ralph design
(`2026-06-11-ralph-decide-design.md`) and reuses its implementation
(`tools/ralph/`) almost entirely; this doc records only the deltas.

## Why

The shipped ralph round-robins **repos** (`vaked-base`, `crabcc`,
`agentfield-stack`) through one supervisor, with a fixed two-model pipeline
(qwen-thinking ranks → deepseek deep-dives). The new goal flips the axis to
**concept tracks** — continuous strategic pressure on the design areas that
are under-attended precisely because they're hard — with **one model pinned
per track**, so model becomes the experiment variable. This sharpens the
research bet already in `PURPOSE.md` (can a budget loop produce a stream a
human mostly *ratifies*?) into a per-model, per-topic question: *which model
advances which class of design problem well enough to ratify?*

## What changes (the deltas, nothing more)

1. **`tracks.json` replaces `repos.json`** as the round-robin target list. A
   track is a concept area inside `vaked-base`, not a whole repo.
2. **One model per track**, running **both** stages (rank → deep-dive). The
   track's model *is* the track's identity. `--stage1-model/--stage2-model`
   become per-track config, not global flags.
3. **Context is scoped to the track** (doc globs + label-filtered issues +
   path-scoped git log), not a whole-repo dump.
4. **CI cron is the host.** A scheduled workflow runs one `decide` per tick and
   commits the appended decision log + the new `events.jsonl` entry. No
   long-lived daemon; the committed, hash-chained event log *is* the rotation
   pointer and the audit trail.
5. **Langfuse** (self-hosted) wraps each model call as a span — **optional
   import**, so the stdlib-only core still runs with zero deps; under `uv` with
   the dep present it emits traces. Managed via `uv` (`pyproject.toml`).
6. **A ratify workflow** (`docs/decisions/RATIFY.md` + an append-only
   ratification convention) so a daily ~1h human pass is contributor-friendly,
   and ratify-rate feeds back to Langfuse as a score.

Non-goals unchanged: read-only on all inputs except *appending* to the
decision/ratify/event logs; not a code-writing agent; no tool-calling; network
only to the configured endpoint.

## Tracks (config) — `tools/ralph/tracks.json`

```json
{
  "tracks": [
    {
      "name": "base-language-spec",
      "topic": "the Vaked base language specification (grammar, schema, examples, core design)",
      "model": "qwen/qwen3-235b-a22b-thinking-2507",
      "label": "track:language",
      "context": {
        "docs": ["vaked/grammar/**", "vaked/schema/**", "vaked/examples/**",
                  "docs/language/0001-*.md", "docs/language/0003-*.md",
                  "docs/language/0008-*.md", "docs/language/0011-*.md",
                  "docs/language/0012-*.md"],
        "paths": ["vaked/", "vakedc/"]
      }
    },
    {
      "name": "graph-concept",
      "topic": "Vaked's typed semantic graph — the Labeled Property Graph, type system, and lowering to artifacts",
      "model": "deepseek/deepseek-v4-flash",
      "label": "track:graph",
      "context": {
        "docs": ["docs/language/0011-*.md", "docs/language/0012-*.md",
                  "docs/language/0013-*.md", "docs/language/0014-*.md"],
        "paths": ["vakedc/"]
      }
    },
    {
      "name": "mlir-topology",
      "topic": "the MLIR topology-compilation dialects (0013) and the memory primitive (0014)",
      "model": "xiaomi/mimo-v2.5",
      "label": "track:mlir",
      "context": {
        "docs": ["docs/language/0013-*.md", "docs/language/0014-*.md"],
        "paths": []
      }
    },
    {
      "name": "hcp-litany",
      "topic": "the HCP / Litany wire protocol — Litany Wire, Votive Frames, .hcplang, hcpbin (RFCs)",
      "model": "tencent/hy3-preview",
      "label": "track:protocol",
      "context": {
        "docs": ["protocol/**", "docs/protocol/**"],
        "paths": ["protocol/"]
      }
    }
  ]
}
```

**Model→track assignment** (the experiment variable — swappable in one JSON
field; nothing in code depends on it):

| track | model | why this pairing |
|-------|-------|------------------|
| `base-language-spec` | `qwen/qwen3-235b-a22b-thinking-2507` | the **anchor/control** — already trusted for ranking; thinking + reliable JSON on the language core |
| `graph-concept` | `deepseek/deepseek-v4-flash` | 1M context holds the whole type-system + lowering + dialect doc set at once |
| `mlir-topology` | `xiaomi/mimo-v2.5` | reasoning-focused; compiler-dialect work is reasoning-heavy |
| `hcp-litany` | `tencent/hy3-preview` | long-context across the RFC set |

Keeping qwen3-thinking as one track makes the other three legible — it's a
known-good baseline rather than four exotic models with no reference point.

## Iteration (per track) — track model does both stages

`ralph decide --track <name>` (was `--repo`):

- **Stage 1 — rank** (track model, `reasoning` enabled, JSON schema): the
  track's compact state + prior-decision titles → ranked candidates.
  Deterministic in-script `select_candidate` is unchanged.
- **Stage 2 — deep-dive** (same track model, no reasoning/schema): chosen
  candidate + the track's full context + its full prior log → the entry.

Same two-stage shape as today; the only change is both stages read
`track.model` instead of two separate `--stage*-model` flags. Models without a
usable `reasoning` field degrade gracefully (the existing `_message_content`
guard already handles thinking-only / empty responses).

## Context per track (`gather_context` generalized)

Today `gather_context` reads whole-repo issues + git log + README/CLAUDE/AGENTS.
For tracks it reads **scoped** state, all inside `vaked-base`:

- **Issues:** `gh issue list --label <track.label>` (falls back to all open
  issues if the label is absent, with a note — so it works before the labels
  exist).
- **Docs:** concatenate the files matched by `track.context.docs` globs
  (compact = head-truncated; full = whole text). The 1M-context tracks can take
  the full set.
- **Git log:** `git log --oneline -n<window> -- <track.context.paths>` (scoped
  to the track's subtree; empty `paths` → repo-wide log).

`Repo` → `Track` is a near-mechanical dataclass rename in `ralphcore`
(`name`, `model`, `topic`, `label`, `context`). The repo-keyed prompt strings
("strategy advisor for the {repo} repository") become topic-keyed ("…for
{topic}"). `next_repo` stays as-is (it round-robins names; rename to
`next_track` for clarity, keep the algorithm + tests).

## State, rotation & the CI-cron host

The committed, hash-chained `state/events.jsonl` is the **state-of-record**.
`status.json` stays a derived cache (gitignored). The rotation pointer is
**derived from the event log** — `next_track(names, last_decided_track, …)`
where `last_decided_track` is the `track` of the last `decide` event — so a
stateless CI run resumes the round-robin with zero extra state.

**Workflow** (`.github/workflows/ralph-tracks.yml`), sketch:

```yaml
on:
  schedule: [{ cron: "*/30 * * * *" }]   # tune to the ratify budget (below)
  workflow_dispatch: {}
concurrency: { group: ralph-tracks, cancel-in-progress: false }
jobs:
  decide:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }             # full history: events.jsonl chain + path-scoped git log
      - run: pipx install uv
      - run: uv run tools/ralph/ralph.py decide --next-track   # rotation from event log
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          LANGFUSE_HOST: ${{ secrets.LANGFUSE_HOST }}
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
      - run: |                                # commit log + event entry
          git config user.name  "ralph-loop"
          git config user.email "ralph@vaked.local"
          git add docs/decisions/ tools/ralph/state/events.jsonl
          git diff --cached --quiet || git commit -m "ralph(tracks): decision tick"
          git push
```

New `--next-track` flag on `decide`: resolve the next track from the event log
and run it (one tick). `concurrency` serializes ticks so two cron runs never
race the log. The append-only `events.jsonl` in git history is the immutable
ledger — `ralph events --replay` verifies the chain on any checkout.

> Privacy note carries over: `vaked-base` content (issues, docs) goes to
> OpenRouter by default. `--base-url`/`RALPH_BASE_URL` still points at a
> self-hosted endpoint to keep it in-boundary; in CI that means a secret URL.

## Langfuse (optional import, `uv`-managed)

- `tools/ralph/pyproject.toml` declares `langfuse` as the one dependency; CI and
  local use `uv run`. **`ralphcore.py` stays pure stdlib.** `ralph.py` does
  `try: import langfuse / except ImportError: langfuse = None` so the loop runs
  identically with zero deps (just no traces).
- Wrap each `openrouter_call` in a span: input = model + track + messages digest;
  output = usage, computed `cost_usd`, latency, finish reason. Trace id =
  `<track>#<N>` (the decision id), so traces ↔ log entries ↔ ratifications
  correlate.
- Ratify-rate lands as a Langfuse **score** keyed by that same id (below), giving
  you the `PURPOSE.md` metrics — ratify-rate, cost/decision, drift — as
  dashboards instead of hand-rolled `status.json` math.
- **Prices:** `FALLBACK_PRICES` only knows qwen + deepseek. Add the two new
  models, or (recommended now that there are four) implement the deferred live
  `/models` price refresh at startup so unknown-model cost isn't a guess.

## Ratify workflow (the part that decides 7 vs 8)

Daily ~1h human pass. Decision entries are **append-only, never edited**; a
ratification is therefore a *separate append*, preserving immutability.

- **`docs/decisions/RATIFY.md`** — the contributor guide. Plain-language, no
  insider context assumed (contributor-friendly though not yet OSS): what the
  loop is, how to read an entry, the three verdicts, how to record one, and
  "what's next" after ratifying.
- **Verdict convention** — append one line to
  `docs/decisions/<track>.ratify-log.md`:
  `- <track>#<N> — **ratify** | **override** | **defer** — <one-line reason> — @handle YYYY-MM-DD`
  - **ratify**: sound, adopt the recommendation / open the follow-up issue.
  - **override**: wrong; the reason line is the correction (feeds future prompts).
  - **defer**: not now; re-surfaces later.
- **Feedback loop**: ratify verdicts post to Langfuse as a 0/1 score on
  `<track>#<N>`, and the *override reasons* get folded into Stage-1 context
  (alongside prior titles) so the loop learns what the human rejects.
- **"What's next" guidance** in RATIFY.md: ratified decisions become GitHub
  issues (the loop advises; humans commit work); the daily pass is *triage*,
  not implementation.

**Cadence sizing (do not skip):** four always-on tracks can out-produce a 1h/day
reviewer. Tune the cron so daily output fits the budget — at `*/30` with four
tracks that's ~48 entries/day, **too many**. Recommend pacing to **~1–2
decisions/track/day** (cron `0 */3 * * *` → 8/day, ~7 min each to ratify). The
spec ships with a conservative schedule and a note to only tighten it once the
ratify pass demonstrably keeps up. If it can't, drop to 2 tracks — the config
makes that a one-line change.

## CLI changes

```
ralph decide --track <name> [--next-track] [--seed 42] [--dry-run]
ralph run    [--interval N] [--budget-total $] [--tracks tracks.json] [--max-iters N]
ralph watch  [--refresh 3]      # dashboard columns: track / model / n / last / cost
ralph events [--replay]         # unchanged (chain verify + replay)
```

`--repo`/`--repos` retained as **deprecated aliases** (owner decision
2026-06-12): the track path is primary, the repo round-robin keeps working with
a deprecation note for one release before removal.

## Safety (unchanged invariants)

- Read-only on all inputs; only writes are appends to `docs/decisions/*.md` and
  `state/events.jsonl` (now committed by CI), plus the gitignored `status.json`.
- Keys from env/secrets only, never logged.
- Budget + iteration caps remain non-bypassable backstops.
- Langfuse failures are swallowed (optional import; observability must never
  break the loop).

## Testing (extends `test_ralph.py`, stdlib runner)

- **`load_tracks`** — parses `tracks.json`, exposes model/topic/label/context.
- **Rotation-from-events** — given an events list, `--next-track` resolves the
  correct next track (advance + wrap + skip-on-missing-doc-set).
- **Context scoping** — glob/label/path scoping selects the right files (pure;
  fed a temp tree).
- **Per-track single-model** — `decide` uses `track.model` for both stages
  (assert on the model passed to a stubbed `openrouter_call`).
- **Ratify parse** — a `*.ratify-log.md` line → `{id, verdict, reason}` and
  maps to a 0/1 score; malformed lines ignored.
- **Langfuse-absent** — with `langfuse=None`, `decide --dry-run` still passes
  (the zero-dep invariant).
- Existing pure tests (cost, select, round-robin, format, dashboard, chain
  verify) carry over with the `Repo`→`Track` rename.

## Files

| File | Change |
|------|--------|
| `tools/ralph/tracks.json` | **new** — track list (replaces `repos.json`) |
| `tools/ralph/ralphcore.py` | `Repo`→`Track`, `load_tracks`, topic-keyed prompts, `next_track`, ratify-line parse |
| `tools/ralph/ralph.py` | per-track context scoping, single-model two-stage, `--track`/`--next-track`, optional Langfuse spans |
| `tools/ralph/pyproject.toml` | **new** — `uv`/`langfuse` dep (core stays stdlib) |
| `tools/ralph/PURPOSE.md` | update preamble: track axis + model-as-variable |
| `docs/decisions/RATIFY.md` | **new** — contributor ratify guide |
| `docs/decisions/<track>.ralph-log.md` | per-track decision logs (runtime) |
| `docs/decisions/<track>.ratify-log.md` | per-track ratification logs (human) |
| `.github/workflows/ralph-tracks.yml` | **new** — scheduled decide + commit |
| `tools/ralph/test_ralph.py` | new tests above |

## Build order (phases)

1. **Config + core rename** — `tracks.json`, `Track`, `load_tracks`,
   `next_track`, topic-keyed prompts. Pure; fully tested. (No behaviour change
   to live calls yet.)
2. **Per-track context + single-model decide** — scope `gather_context`; both
   stages use `track.model`; `--track`/`--next-track`. Dry-run + unit tests.
3. **CI workflow** — `ralph-tracks.yml`, commit of log + `events.jsonl`,
   rotation-from-events. Conservative cron.
4. **Langfuse (optional)** — `pyproject.toml`, span wrapping, price refresh.
5. **Ratify workflow** — `RATIFY.md`, ratify-line parse, override-reason
   feedback into Stage-1, Langfuse scores.

Phases 1–3 deliver the core loop; 4–5 are independently shippable.

## Resolved decisions (owner, 2026-06-12)

- **`--repo` kept deprecated.** Track path is primary; repo round-robin keeps
  working with a deprecation note for one release, then removed.
- **All 4 tracks live day one.** Cadence is the guard, not track count: pace the
  cron to ~8 total decisions/day (`0 */3 * * *` → 2/track/day), which fits the
  ~1h daily ratify budget (~7 min/entry). Only tighten the schedule once the
  ratify pass demonstrably keeps up; drop tracks if it can't (one-line config).
- **`track:*` labels created now** — `track:language`, `track:graph`,
  `track:mlir`, `track:protocol` (sharper issue scoping; `gather_context`
  filters issues by them, falling back to all-open until issues accrue).
- **Self-hosted CI endpoint: pending.** No trust-boundary inference host exists
  yet (`agentfield-inference-host` is a placeholder in the `agentfield-stack`
  stub). The `RALPH_BASE_URL`/`RALPH_API_KEY` hook is in place; until a real
  host lands, CI uses OpenRouter for this (owner-authored) design content. Wire
  the secret URL when the host is real.
