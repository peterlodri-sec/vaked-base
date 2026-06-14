# VAKED_AGENTS — the Vaked agent fleet

Index of the automated agents that run *on* this repo. Two archetypes:

- **Python cron loop** (`tools/<name>/`, stdlib-first) — scheduled, append-only
  ledgers, self-pacing. Prototype: **ralph**.
- **adk-rust event agent** (`vaked-agents/ci/<name>/`) — PR/comment/webhook
  triggered, MCP tools, guardrails, prebuilt rolling release. Prototype:
  **pr-review**.

Shared conventions: all credentials live in the **`ci` GitHub Environment**
(`environment: ci`); agents **guard on secrets** and no-op cleanly when unset; they
are **advisory / never block** a merge; failures route to **Telegram**; LLM-driven
runs trace to **Langfuse**. New agents follow design→plan→implement (`CLAUDE.md`).
**CI details:** [`docs/agents/ci.md`](docs/agents/ci.md). **Fleet backlog:**
[`vaked-agents/BACKLOG.md`](vaked-agents/BACKLOG.md).

## Active agents

| Agent | Kind | Trigger | Lives in | Model | Does |
|-------|------|---------|----------|-------|------|
| **ralph** | Python cron loop | cron 3h + 23:00 UTC, dispatch | `tools/ralph/` ([README](tools/ralph/README.md)) | per-track ([`tools/ralph/tracks.json`](tools/ralph/tracks.json)) | Surfaces the most important open decision per track into a hash-chained, human-ratified ledger; announces + daily recap to Mastodon. |
| **pr-review** | adk-rust event | `pull_request` | `vaked-agents/ci/pr-review/` ([README](vaked-agents/ci/pr-review/README.md)) | `deepseek/deepseek-v4-flash` | Advisory diff review: 7-hat council, crabcc/MCP + RTK, structured findings, inline ```suggestion``` autofixes, cost + runtime footer; never fails the check. |
| **@vaked-ci** | adk-rust event (same binary, `--respond`) | `issue_comment` mentioning `@vaked-ci` | `vaked-agents/ci/pr-review/` | `deepseek/deepseek-v4-flash` | Replies to maintainer comments: answer a question about the diff, or `review`/`re-review`. Gated to non-bot OWNER/MEMBER/COLLABORATOR. |
| **doc-keeper** | Python checker | doc/protocol pushes, PRs, weekly cron | `tools/dockeeper/` ([README](tools/dockeeper/README.md)) | — (deterministic) | Gates doc/spec/RFC drift: RFC cross-refs resolve, backticked repo-path refs resolve, stub-README freshness. |
| **yardmaster** | Python cron loop | cron hourly, PRs, dispatch | `tools/yardmaster/` ([README](tools/yardmaster/README.md)) | — (deterministic) | Merge-train conductor for the fan-out fleet: builds the open-PR dependency DAG (catches stacked PRs), topo-orders the train, and **acts** (merge / update-branch / block-conflict / hold) on opt-in `train:auto` PRs onto an `eventd` ledger — never auto-resolving conflicts. Broadcasts every run as `yardmaster:<repo>` to Mastodon (infographic picture) + Telegram (emoji report). |
| **vaked-telebot** | Python long-poll daemon | Telegram getUpdates (crabcc.app) | `tools/telebot/` ([README](tools/telebot/README.md)) | `deepseek/deepseek-v4-flash` (free-form ask) | Interactive control surface in the `vaked` group: a `/menu` of scenarios (merge train · CI & PRs · trigger workflow · fleet & decisions) plus natural-language ask. Acting (workflow dispatch) gated to `TELEGRAM_ADMIN_IDS`; actions ledgered to `eventd`. |
| **label-tagger** | adk-rust event | `pull_request`, `issues`, push to main, dispatch | [`vaked-agents/ci/label-tagger/`](vaked-agents/ci/label-tagger/) | `deepseek/deepseek-v4-flash` | Doc-grounded triage: labels PRs/issues from the live `.github/labels.yml` taxonomy, syncs GitHub milestones to GOALS.md phases, generates Keep-a-Changelog entries on push-to-main, optionally tags. Opt-out `no-auto-label`. |
| **provost** | adk-rust scheduled | cron daily 06:00 UTC, dispatch | `vaked-agents/ci/provost/` ([README](vaked-agents/ci/provost/README.md)) | `deepseek/deepseek-v4-flash` | Product-owner / coordination: reconciles the project graph — derives epics from GOALS.md + specs and links child issues (native sub-issues), keeps the RFC index honest, backfills labels, assigns existing milestones. Advisory + safe-sync; new epics/issues/RFC stubs land in ONE coordination issue + PR. Opt-out `no-auto-coordinate`. |
| **swe-af** | adk-rust event | `issues` labeled `agent` (owner-gated), dispatch | [`vaked-agents/ci/swe-af/`](vaked-agents/ci/swe-af/README.md) | `deepseek/deepseek-v4-flash` (`SWE_AF_CODE_MODEL` overridable) | Runs the lowered `workflow swe_af` (plan→code→review→publish) on GitHub Actions: the agent authors a plan + full-file changes (read-only, no GH token), the shell commits a `swe-af/issue-<n>` branch, the **pr-review** agent reviews, and the broker opens an advisory PR. Every node testified to an `eventd` hash chain. **Never auto-merges.** |
| **vaked-optitron** | Go (Eino) cron + gated dispatch | cron daily 05:33 UTC; `workflow_dispatch` (double-confirm) | `tools/optitron/` ([README](tools/optitron/README.md)) · skill [`.claude/skills/vaked-optitron/`](.claude/skills/vaked-optitron/SKILL.md) | `gpt-5.5:online` (crawl) · `claude-opus-4.8` (verify/adjudicate) · `claude-fable-5` (bench) | Abstain-by-default optimization crawler: surfaces **one** novel, proven, independently-confirmed compiler/allocator/zig/rust/vaked optimization through a fail-closed gate (≥2 independent sources + repo/ledger novelty + a *reproduced* micro-benchmark + confidence ≥0.80), then opens an `agent`-labelled issue (the `swe_af` trigger) + announces to Mastodon/Telegram. Concurrent Go pipeline (crawl fan-out + bounded candidate worker-pool); single-writer hash-chained findings ledger; $4/run cap. Manual runs gated behind a GitHub Environment required-reviewer approval. |
| **fleet-introspect** | Go (Eino) cron + gated dispatch | cron daily 06:00 UTC; `workflow_dispatch` (double-confirm) | `tools/optitron/` (`cmd/introspect`) ([README](tools/optitron/README.md)) | `deepseek-v4-flash` (detect) · `claude-opus-4.8` (ideate/review) | Fleet self-improvement loop — a second binary in the optitron module (reuses `internal/ledger` + `internal/llm`). Reads the fleet's OWN Langfuse traces (+ the hash-chained ledgers; **ralph's is read-only**) over the last ≤2 days, auto-detects the most salient finding, ideates **one** novel solution, **always reviews** it (fail-closed gate), and hands a survivor to swe_af via an `agent`-labelled issue. Reports the fleet economy (real spend → normal day/week/month projection). Abstains by default; $3/run cap; manual runs gated behind a required-reviewer Environment approval. |
| **nocturne** | Python cron loop + Vast.ai GPU | cron nightly 02:00 UTC; `workflow_dispatch` (double-confirm) | `tools/nocturne/` ([README](tools/nocturne/README.md)) | `deepseek/deepseek-chat` (mutation, overridable) | Abstain-by-default **empirical** researcher: rents a single GPU nightly, runs Karpathy's `autoresearch` mutate→train 5min→read `val_bpb`→keep/discard loop under a `$/hr` cap + `watch-and-destroy` self-destruct, **always** tears down. Escalates **only** a re-run-confirmed, novel BPB win — opens an `agent` issue and `workflow_dispatch`es swe_af — else silent. Hash-chained results ledger; version-controlled `train.py` baseline. The GHA side never trains (the box does). Manual runs gated behind the `nocturne-manual` Environment approval; first manual dispatch defaults to a no-spend dry run. |

Workflows: [`ralph-tracks.yml`](.github/workflows/ralph-tracks.yml) ·
[`nocturne.yml`](.github/workflows/nocturne.yml) ·
[`fleet-introspect.yml`](.github/workflows/fleet-introspect.yml) ·
[`merge-train.yml`](.github/workflows/merge-train.yml) ·
[`pr-review.yml`](.github/workflows/pr-review.yml) ·
[`pr-review-build.yml`](.github/workflows/pr-review-build.yml) ·
[`pr-review-audit.yml`](.github/workflows/pr-review-audit.yml) ·
[`vaked-ci-respond.yml`](.github/workflows/vaked-ci-respond.yml) ·
[`docs-keeper.yml`](.github/workflows/docs-keeper.yml) ·
[`social-post.yml`](.github/workflows/social-post.yml) ·
[`label-tagger.yml`](.github/workflows/label-tagger.yml) ·
[`label-tagger-build.yml`](.github/workflows/label-tagger-build.yml) ·
[`provost.yml`](.github/workflows/provost.yml) ·
[`provost-build.yml`](.github/workflows/provost-build.yml) ·
[`swe-af.yml`](.github/workflows/swe-af.yml) ·
[`swe-af-build.yml`](.github/workflows/swe-af-build.yml)

## Proposed agents (roadmap)

Higher-leverage first; each graduates to a dated `docs/superpowers/specs/` design
+ a `plans/` checklist before code (see `vaked-agents/BACKLOG.md`).

| Agent | Kind | Purpose | Effort |
|-------|------|---------|--------|
| **evalsmith** | Python cron + adk-eval | Mine recent `main` diffs per language, run pr-review, curate `*.diff`/`*.expect` + baselines → PR. Auto-grows the reviewer's regression suite. | L |
| **ledger-steward** | Python cron | ralph's complement: track decided items vs issues (open/closed/deferred/unratified), nudge ratification, weekly state-of-decisions digest. | M |
| **nixwarden** | CI + cron | `nix flake check` + build `nixosConfigurations.vakedos` toplevel; LLM summarizes breakage + likely fix → issue/PR. | S→L |
| **daemonsmith** | event | On a new `docs/superpowers/specs/*daemon*` design, scaffold `daemons/<name>/` (stub + plan + Zig config schema from the lowering spec) → PR. | M |
| **release-herald** | event (tag/release) | Summarize merged PRs + ratified decisions into release notes / CHANGELOG + a Carcin toot. | M |
| **triage-bot** | event (`issues`) | Auto-label/triage new issues — classify the track, link related decisions/RFCs. | S |
| **security-sentinel** | cron | Extend supply-chain hygiene beyond Rust (`cargo-deny`/`cargo-audit`): `pip-audit` for Python tooling; eBPF policy review when policy manifests land. | M |
| **lowering-completeness** | CI check | ralph-decided #1: every grammar `kind` has an emitter / is documented meta / explicitly deferred — fail CI on drift. | S |
| **memoryd-miner** | Python/Rust | Feed the runtime `memoryd`: mine sources into capability-bound, recallable memory (BACKLOG item 6 / #24). | L |
| **CTO copilot** | adk-rust realtime | Personal voice/avatar agent: watches CI, researches, brainstorms (BACKLOG item 9 ⭐). Own spec + plan first. | XL |

## Adding an agent
1. Pick the archetype; scaffold under `tools/<name>/` or `vaked-agents/ci/<name>/`.
2. Add its workflow with `environment: ci`, a secrets-guard no-op, a Telegram
   failure-notify, and a `concurrency` group. See [`docs/agents/ci.md`](docs/agents/ci.md).
3. Keep it advisory (exit 0); trace to Langfuse if it calls a model.
4. Update this index + `vaked-agents/BACKLOG.md`.
