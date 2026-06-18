# Agent CI — how the fleet runs

How the [Vaked agent fleet](../../VAKED_AGENTS.md) is wired into GitHub Actions:
triggers, the shared `ci` environment, secrets, the build pipeline, and the
conventions every agent workflow follows. All workflows live in
[`.github/workflows/`](../../.github/workflows).

## The `ci` GitHub Environment
Every credential lives in **one** GitHub Environment named `ci` (Settings →
Environments → ci). A job reads it by declaring `environment: ci`; without that the
`${{ secrets.* }}` references resolve empty (this exact omission once made every
`pr-review` run a green no-op). Agents **guard on the secret** and no-op cleanly
when it's unset, so the workflows are safe to merge before secrets exist and on
fork PRs (which get no secrets).

| Secret | Used by | Optional? |
|--------|---------|-----------|
| `OPENROUTER_API_KEY` | all agents (pr-review, @vaked-ci, ralph, orcli, @vaked/openrouter-ts) | required for LLM runs |
| `LANGFUSE_HOST` (or `LANGFUSE_BASE_URL`), `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | all agents (pr-review, ralph, @vaked/openrouter-ts) | optional (tracing). @vaked/openrouter-ts uses the Langfuse v3 SDK directly; pr-review builds the OTLP Basic token from the key pair; legacy `LANGFUSE_URL`/`LANGFUSE_API_KEY` still accepted |
| `LANGFUSE_PROJECT_ID` | pr-review | optional (enables comment→trace deep-link) |
| `MASTODON_ACCESS_TOKEN` | ralph announce/digest, social-post | optional |
| `CONTEXT7_API_KEY` | @vaked/openrouter-ts | **NEW — add to CI secrets.** Get at [context7.com/dashboard](https://context7.com/dashboard). Keys start with `ctx7sk-`. Optional — agent tools return error messages when unset, never crash. |
| `CRABCC_INSTALL_TOKEN` | pr-review, @vaked-ci | optional (private crabcc) |
| `RALPH_API_KEY`, `RALPH_BASE_URL` | ralph | optional (self-hosted endpoint) |
| `TELEGRAM_TOKEN`, `TELEGRAM_TO` | all (failure-notify) | optional |

Config (non-secret) is passed via env vars (e.g. `PR_REVIEW_MODEL`,
`PR_REVIEW_USD_PER_MTOK`, `RALPH_WRITER_MODEL`, `MASTODON_VISIBILITY`) — see each
agent's README.

## Workflow inventory

| Workflow | Trigger | Agentic? | Purpose |
|----------|---------|----------|---------|
| [`ralph-tracks.yml`](../../.github/workflows/ralph-tracks.yml) | cron 3h + 23:00 UTC, dispatch | LLM | decide one track → commit ledger → announce/recap to Mastodon |
| [`optitron-crawl.yml`](../../.github/workflows/optitron-crawl.yml) | daily cron 05:33 UTC; **double-confirmed** dispatch | LLM (Go/Eino) | concurrent crawl→verify→bench→adjudicate for ONE proven optimization → open `agent` issue (swe_af) + announce; else abstain. Manual runs gated by `confirm: RUN` + the `optitron-manual` Environment required-reviewer approval |
| [`fleet-introspect.yml`](../../.github/workflows/fleet-introspect.yml) | cron daily 06:00 UTC; **double-confirmed** dispatch | LLM (Go/Eino) | mine the fleet's own Langfuse traces (≤2d) → detect→ideate→**review** one novel improvement → `agent` issue (swe_af) + economy report; else abstain. Reads ralph's live loop read-only. Manual runs gated by `confirm: RUN` + the `introspect-manual` Environment approval |
| [`nocturne.yml`](../../.github/workflows/nocturne.yml) | cron nightly 02:00 UTC; **double-confirmed** dispatch | LLM (Python) + Vast.ai GPU | rent a GPU → mutate→train 5min→read `val_bpb`→keep/discard → confirm on seeds → **always teardown** → gate → `workflow_dispatch` swe_af on a confirmed novel win + inline announce; else abstain. The GHA side never trains. Manual runs gated by `confirm: RUN` + the `nocturne-manual` Environment approval; first manual dispatch defaults to a no-spend dry run |
| [`pr-review.yml`](../../.github/workflows/pr-review.yml) | `pull_request` | LLM | advisory diff review (prebuilt binary; from-source fallback) |
| [`vaked-ci-respond.yml`](../../.github/workflows/vaked-ci-respond.yml) | `issue_comment` w/ `@vaked-ci` | LLM | answer maintainer questions / `re-review` |
| [`pr-review-build.yml`](../../.github/workflows/pr-review-build.yml) | push to `main` (agent crate) | CI | compile + publish the rolling `pr-review-bin` release |
| [`pr-review-audit.yml`](../../.github/workflows/pr-review-audit.yml) | agent version bump | CI | `cargo-deny` + `cargo-audit` |
| [`cleanup.yml`](../../.github/workflows/cleanup.yml) | daily cron, dispatch | bot | sweep bot-noise + duplicate review comments across open PRs (`--cleanup`) |
| [`docs-keeper.yml`](../../.github/workflows/docs-keeper.yml) | doc/protocol push, PR, weekly cron | checker | doc/spec/RFC drift gate |
| [`spec-tests.yml`](../../.github/workflows/spec-tests.yml) | push/tag/PR | CI | grammar/examples/lowering harness + nix-parse |
| [`social-post.yml`](../../.github/workflows/social-post.yml) | `.github/social/toot.txt` change | — | post a toot to Mastodon |

## Triggers in use
- **`pull_request`** — pr-review (per push to a PR).
- **`issue_comment`** — @vaked-ci. Runs from the **default branch** with repo
  secrets regardless of who commented, so it's gated on
  `author_association ∈ {OWNER, MEMBER, COLLABORATOR}` + non-bot + the `@vaked-ci`
  mention — the key control against cost-abuse and self-trigger loops.
- **`push` + `paths`** — pr-review-build (agent crate), docs-keeper (docs/protocol).
- **`schedule`** (cron) — ralph (decision cadence), docs-keeper (weekly sweep).
- **`workflow_dispatch`** — manual runs.

## Build / deploy pattern (adk-rust agents)
Cold-start is avoided by a **rolling prebuilt binary**:
[`pr-review-build.yml`](../../.github/workflows/pr-review-build.yml) compiles the
crate on `main` and uploads `vaked-pr-review-linux-x86_64` to the `pr-review-bin`
release. pr-review and @vaked-ci **download** it; if the asset is missing (or the
agent source changed in the PR — dogfooding), they **build from source** with
`sccache` + a linker probe (`cc -fuse-ld=` is validated by a test link, preferring
wild → lld → mold; gcc rejects an unknown `-fuse-ld=wild`). The same binary serves
both review and `--respond` modes.

## Conventions for a new agent workflow
- `environment: ci`; reference secrets via `${{ secrets.* }}`; **guard** so a
  missing key is a clean no-op.
- **Advisory / never block:** the agent exits 0 even on error; CI failure is for
  genuine checker drift (doc-keeper) or infra breakage, not model opinions.
- **Telegram failure-notify** step (`if: failure()`) — shared across workflows.
- **`concurrency`** group (per PR / per loop) to serialize writes (ledgers) and
  cancel superseded PR runs.
- **Commit before side effects** (ralph commits the decision before announcing);
  **append-only ledgers** over growing context.
- LLM agents trace to **Langfuse** (lazy/no-op when unset) and surface
  **tokens · runtime · cost** in their output footer.

See the prototypes: [ralph](../../tools/ralph/README.md) (Python loop) and
[pr-review](../../vaked-agents/ci/pr-review/README.md) (adk-rust event).
