# vaked-pr-review

An advisory CI **PR-review agent** built on [adk-rust]. It reads a pull
request's diff via `gh`, reviews it with a non-frontier **OpenRouter** model
(GLM-4.6 by default — no Codex-style usage/credit limits), and posts **one
structured, advisory-only review comment**. It never blocks a merge: any failure
logs and exits 0.

This is the first inhabitant of `vaked-agents/` — the home for the Vaked agent
fleet. `ci/` is the CI-bot subtree.

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
- **RTK token-killer** — when [rtk-ai/rtk] is present, the diff is fetched as a
  condensed `rtk git diff base...head` (60–90% fewer tokens → cheaper, larger
  effective budget); falls back to `gh pr diff` otherwise.
- **Langfuse tracing** — every run exports OTLP/HTTP spans to your self-hosted
  Langfuse.
- Low temperature + fixed seed, opt-out label, and empty-diff skip.

## Cold start (baking)

`pr-review-build.yml` compiles the release binary once on `main` and publishes it
as a rolling GitHub Release asset (`pr-review-bin`). `pr-review.yml` downloads
that prebuilt binary per PR instead of compiling adk-rust (~2 min) every time. If
the asset is missing — or the PR changes the agent's own source — it builds from
source as a fallback (dogfooding stays honest).

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
| `PR_REVIEW_MODEL` | `z-ai/glm-4.6` | any OpenRouter model id |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | self-host / proxy |
| `PR_REVIEW_MAX_DIFF_CHARS` | `48000` | diff budget before truncation |
| `PR_REVIEW_API_KEY` | — | takes precedence over `OPENROUTER_API_KEY` |
| `CRABCC_BIN` | `crabcc` | crabcc binary path |
| `RTK_BIN` | `rtk` | rtk binary path |
| `PR_REVIEW_NO_RTK` | — | set to disable rtk diff compression |
| `BASE_SHA` / `HEAD_SHA` | — | PR base/head for the rtk diff range (CI sets these) |

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
