# vaked-pr-review

An advisory CI **PR-review agent** built on [adk-rust]. It reads a pull
request's diff via `gh`, reviews it with a cost-effective **OpenRouter** model
(DeepSeek V4 Flash by default — cheap, 1M context, no Codex-style usage/credit
limits), and posts **one structured, advisory-only review comment**. It never
blocks a merge: any failure logs and exits 0.

This is the first inhabitant of `vaked-agents/` — the home for the Vaked agent
fleet. `ci/` is the CI-bot subtree. **Backlog / roadmap:** [`../BACKLOG.md`](../BACKLOG.md).

## What makes it good, not sloppy

- **Seven-hat council** in the system prompt — PL researcher · nix/zig/rust/python
  · systems architect · security & capability auditor · compiler/type-systems ·
  OTP/BEAM supervision · protocol/wire-format — each lens tuned to the Vaked stack.
- **Caveman output contract** — verdict line + grouped findings (`Blocking /
  Major / Minor / Nit`), each `path:line — problem; fix`, no preamble, no praise,
  no hedging. Clean diff ⇒ `**Verdict:** No blocking issues.` and nothing else.
- **crabcc over MCP** — the repo's own symbol index ([crabcc-labs/crabcc]) is
  wired in as an adk-rust `McpToolset` (`crabcc --mcp`), so the model resolves
  definitions/references beyond the diff. The on-disk `.crabcc/` index is reused
  (refreshed, not rebuilt) and cached across CI runs.
- **RTK token-killer** — when [rtk-ai/rtk] is present, the single-pass diff is
  fetched condensed (`rtk git diff base...head`, 60–90% fewer tokens); falls back
  to plain unified diff / `gh pr diff`.
- **High reasoning** — the model runs at `effort: high` (best lens for catching
  logic/edge/security bugs), wired through the OpenRouter extension on
  `GenerateContentConfig`. Overridable via `PR_REVIEW_REASONING_EFFORT`.
- **Map-reduce for large PRs (parallel)** — above `PR_REVIEW_MAPREDUCE_LINES`
  (default 600) changed lines, each file is reviewed independently —
  `PR_REVIEW_CONCURRENCY` (default 6) at a time — then a synthesis pass dedupes
  and groups into the final review. Set `PR_REVIEW_PARALLEL_AGENT` to instead use
  the adk `ParallelAgent`/`SequentialAgent` pipeline (opt-in until validated live;
  falls back to map-reduce on error).
- **Tiered reasoning** — per-file passes run at `effort: medium` (mechanical),
  the final/synthesis pass at `high` — large-PR speed without losing the deep pass.
- **Structured output + caveman prose** — the final pass returns strict JSON
  (`verdict` / `findings[]` / `prose` / `exceptions`) rendered to markdown: exact
  finding counts for the status, blunt prose for humans. Falls back to raw text if
  a provider returns non-conforming output. Disable with `PR_REVIEW_NO_STRUCTURED`.
- **Inline autofix suggestions** — for `Nit`/`Minor` findings with a mechanical
  one-/few-line fix, the model emits an exact `suggestion`, posted as a GitHub
  ```` ```suggestion ```` block on the diff line so the author can click *Commit
  suggestion*. Only lines present in the **current** diff get a comment (stale /
  off-diff findings are dropped, also avoiding 422s); `Major`/`Blocking` stay
  summary-only. Prior suggestions (marked `<!-- vaked-autofix -->`) are deleted
  each run, so re-reviews don't pile up stale comments. On by default; disable with
  `PR_REVIEW_NO_AUTOFIX`.
- **`@vaked-ci` interactive responder** — mention `@vaked-ci` in a PR comment and
  the agent replies (in `--respond` mode, same binary): a free-form question about
  the diff gets a caveman answer (with crabcc/`read_lines` to verify); `review` /
  `re-review` triggers a fresh full review. Advisory only — it posts a comment,
  never changes code. Driven by [`vaked-ci-respond.yml`](../../../.github/workflows/vaked-ci-respond.yml),
  gated to comments from `OWNER`/`MEMBER`/`COLLABORATOR` (non-bot) to bound cost
  and prevent loops; replies are marked `<!-- vaked-ci-reply -->` and form a thread
  (never auto-deleted).
- **Cost estimate** — the footer shows `cost ~$X` from token usage × a blended
  `$/Mtok` rate (`PR_REVIEW_USD_PER_MTOK`, default 0.3).
- **Prompt caching** — a stable cache key + a byte-identical system-prompt prefix
  (no per-PR values baked in) let the provider cache the prefix; cached tokens are
  recorded in usage / Langfuse. The big win is the map-reduce path, where every
  per-file pass re-sends the same prefix — DeepSeek's automatic prefix caching (and
  Anthropic/Gemini explicit caching) reuses it. Cross-PR hits are rare (cache TTL),
  so keep the prefix stable and prefer a caching-friendly model.
- **Restraint + calibration** — tuned from real runs (the reviewer was padding to
  the cap with fabricated/subjective nits): findings are capped low (10), the prompt
  forbids non-diff-visible nits (EOF newline, file length, naming taste) and requires
  an exact `+`-line citation per finding (omit rather than guess), and cosmetics are
  capped at Nit severity.
- **Secret redaction (pre-send guardrail)** — likely credentials are scrubbed
  from the diff before it ever reaches the model.
- **`read_lines` tool** — a native read-only Rust `FunctionTool` so the model can
  pull exact surrounding context crabcc's symbol index doesn't cover.
- **Noise filtering** — lockfiles, generated, and binary paths are excluded from
  the diff (git pathspec + post-filter) before the model ever sees them.
- **Language-conditional checklists** — Nix/Zig/Rust/Python/EBNF/OTP checklists
  injected only for the file types actually in the diff.
- **Replace, don't stack** — each run deletes its prior `<!-- vaked-pr-review -->`
  comment and posts one fresh review; an **advisory commit status** carries the
  finding count (never fails the check).
- **Langfuse tracing** — OTLP/HTTP spans per run, with `changed_lines`, `mode`,
  `total_tokens`, `thinking_tokens`, and `findings` recorded as span attributes.
- **Eval harness** — `--eval <dir>` scores the reviewer against `*.diff`/`*.expect`
  fixtures (see `evals/`).
- **Resilience** — OpenRouter provider fallback (`allow_fallbacks`), bounded tool
  retries, and a supply-chain audit (`cargo-deny`/`cargo-audit`) that runs only on
  agent **version bumps** (`pr-review-audit.yml`).
- Bounded tool loop (`PR_REVIEW_MAX_ITERS`, 60s tool timeout) + 25-min CI cap,
  low temperature + fixed seed, opt-out label, and empty-diff skip.

## Cold start (baking)

`pr-review-build.yml` compiles the release binary once on `main` and publishes it
as a rolling GitHub Release asset (`pr-review-bin`). `pr-review.yml` downloads
that prebuilt binary per PR instead of compiling adk-rust (~2 min) every time. If
the asset is missing — or the PR changes the agent's own source — it builds from
source as a fallback (dogfooding stays honest), accelerated by `sccache` + the
`mold` linker (swap to `wild` by changing the setup action + `-fuse-ld`). The
release profile (thin-LTO, `strip`, `panic=abort`) + rustls (no system OpenSSL)
keep the baked binary ~10 MB; the agent runs on the **mimalloc** global allocator.

## Secrets (repo → Settings → Secrets → Actions)

| Secret | Required | Purpose |
|--------|----------|---------|
| `OPENROUTER_API_KEY` | yes | OpenRouter API key (the model call) |
| `LANGFUSE_URL` | optional | Self-hosted Langfuse base, e.g. `https://langfuse.internal` |
| `LANGFUSE_API_KEY` | optional | OTLP Basic token: **base64 of `<public_key>:<secret_key>`** |
| `CRABCC_INSTALL_TOKEN` | optional | PAT with `crabcc-labs/crabcc` read access (CI installs crabcc) |

Missing optional secrets degrade gracefully: no Langfuse ⇒ untraced; no crabcc ⇒
diff-only review.

## Env / overrides

| Var | Default | Notes |
|-----|---------|-------|
| `PR_REVIEW_MODEL` | `deepseek/deepseek-v4-flash` | any OpenRouter model id — see **Model choice** below |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | self-host / proxy |
| `PR_REVIEW_MAX_DIFF_CHARS` | `48000` | diff budget before truncation |
| `PR_REVIEW_API_KEY` | — | takes precedence over `OPENROUTER_API_KEY` |
| `CRABCC_BIN` | `crabcc` | crabcc binary path |
| `RTK_BIN` | `rtk` | rtk binary path |
| `PR_REVIEW_NO_RTK` | — | set to disable rtk diff compression |
| `BASE_SHA` / `HEAD_SHA` | — | PR base/head for the diff range (CI sets these) |
| `PR_REVIEW_REASONING_EFFORT` | `high` | OpenRouter reasoning effort (`low`/`medium`/`high`) |
| `PR_REVIEW_MAPREDUCE_LINES` | `600` | changed-line threshold to switch to map-reduce |
| `PR_REVIEW_MAX_FINDINGS` | `20` | cap on findings in the final review |
| `PR_REVIEW_CRABCC_BUDGET` | `8` | max crabcc tool calls the model may make |
| `PR_REVIEW_MAX_ITERS` | `12` | max agent tool-loop iterations |
| `PR_REVIEW_CONCURRENCY` | `6` | parallel per-file passes (map-reduce) + tool concurrency |
| `PR_REVIEW_NO_STRUCTURED` | — | set to disable structured JSON output |
| `PR_REVIEW_TRACE_PAYLOADS` | — | set to record prompt/response payloads into Langfuse spans |
| `PR_REVIEW_PARALLEL_AGENT` | — | set to use the adk `ParallelAgent`/`SequentialAgent` pipeline for large PRs instead of the default map-reduce (opt-in until validated live; falls back to map-reduce on error) |
| `PR_REVIEW_EVAL_TOLERANCE` | `0.0` | `--eval` regression tolerance: fail if `baseline − current > tolerance` on any case |
| `PR_REVIEW_NO_AUTOFIX` | — | set to disable inline ```suggestion``` comments for Nit/Minor findings |
| `PR_REVIEW_USD_PER_MTOK` | `0.3` | blended $/million-token rate for the footer cost estimate |

### Model choice
Default is **`deepseek/deepseek-v4-flash`** — cheap, 1M context, strong on code, and
automatic prefix caching that suits the map-reduce path. Swap via `PR_REVIEW_MODEL`
(bump `PR_REVIEW_USD_PER_MTOK` for pricier models):

| Want | Model | Notes |
|------|-------|-------|
| cheap default | `deepseek/deepseek-v4-flash` | best $/quality for advisory review |
| more rigor, still cheap | `deepseek/deepseek-v4-pro`, `z-ai/glm-5`, `google/gemini-3-flash` | fewer misses on subtle bugs |
| highest quality | `anthropic/claude-sonnet-4.6`, `google/gemini-3.1-pro`, `anthropic/claude-opus-4.6`, `openai/gpt-5.4` | best calibration/least over-flagging; pricier |

Rankings move fast — check OpenRouter's programming leaderboard before pinning.

## Security guardrails

The diff is **untrusted input**, so the reviewer agent runs adk guardrails
([`src/guardrails.rs`](src/guardrails.rs)):

- **Input** — secret redaction + prompt-injection defang on every agent turn
  (the system prompt also hardens against in-diff instructions).
- **Output** — a findings cap to `PR_REVIEW_MAX_FINDINGS`.

All guardrails `Transform`/`Pass` (never `Fail`), so they can't suppress the
advisory review. The parallel pipeline passes per-file diffs + PR metadata to
agents via **session state** (referenced by a single `{placeholder}` in the
instruction) — guardrails don't see instructions/state, so that text is
pre-sanitized with the same redaction/defang; routing it through state (a
single-pass, non-rescanned injection) also stops the diff's own `{...}` from being
re-templated.

## Eval

```bash
OPENROUTER_API_KEY=sk-or-... \
  cargo run --manifest-path vaked-agents/ci/pr-review/Cargo.toml -- \
  --eval vaked-agents/ci/pr-review/evals
```

Scoring uses adk-eval's `ResponseScorer` (Contains) and writes a
`.baseline.json` in the eval dir via adk-eval's `BaselineStore`; subsequent runs
**gate on regressions** (any case dropping more than `PR_REVIEW_EVAL_TOLERANCE`
below baseline fails). The baseline ratchets up only on a fully-passing,
non-regressing run.

## Local dry-run (prints the review, posts nothing)

```bash
export OPENROUTER_API_KEY=sk-or-...
cargo run --manifest-path vaked-agents/ci/pr-review/Cargo.toml -- \
  --repo peterlodri-sec/vaked-base --pr <N> --dry-run
```

Add `LANGFUSE_URL` + `LANGFUSE_API_KEY` to verify a `vaked-ci-reviewer` trace
appears in Langfuse. `gh` must be authenticated (`gh auth status`).

[adk-rust]: https://github.com/zavora-ai/adk-rust
[crabcc-labs/crabcc]: https://github.com/crabcc-labs/crabcc
[rtk-ai/rtk]: https://github.com/rtk-ai/rtk
