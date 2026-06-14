# CLAUDE.md — vaked-base

Foundation monorepo for the **Vaked** agentic-runtime ecosystem.

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

## What this is

Vaked is a flake-native **capability-graph language**. A Vaked declaration compiles to a typed semantic graph, then to artifacts: `flake.nix` / NixOS modules, Zig daemon configs, eBPF policy manifests, OTel config, CrabCC indexes, and docs. Those run on a NixOS host under an OTP supervision plane that orchestrates single-purpose Zig enforcement daemons, with eBPF as the evidence layer and operator surfaces on top.

Language + compiler are **done**. Protocol has 7 RFCs. Two runtime reference daemons exist. See `README.md` for the full repo map and `docs/context/PROJECT_CONTEXT.md` for the canonical overview.

## Structure

| Path | Purpose |
|------|---------|
| `vaked/` | The language — `grammar/vaked-v0-plus.ebnf`, `schema/`, `examples/` |
| `vakedc/` | Python prototype front-end — parse → check → lower (stages 1–4) |
| `vakedz/` | Zig production front-end — cache-native port of vakedc; min Zig 0.16 |
| `docs/language/` | Design series `0001…0018` + `references/` |
| `docs/context/` | `PROJECT_CONTEXT.md` (canonical overview) |
| `docs/runtime/`, `daemons/` | Runtime daemon roster (OTP + Zig) |
| `docs/protocol/`, `protocol/` | HCP / Litany protocol + RFCs 0001–0007 |
| `vaked-agents/` | Agent fleet — pr-review, swe_af, provost, ralph, docs-keeper, merge-train |
| `tools/ralph/` | Autonomous track decision loop — commits ledger entry, announces |
| `agent_guardd/` | Reference daemon — network/eBPF membrane (deny-by-default egress) |
| `eventd/` | Reference daemon — append-only hash-chained event log |
| `prompts/` | `dedicated-language-session.md` kickoff prompt |
| `hosts/` | `vakedos` bare-metal NixOS host — the materialization target (EPYC 4345P); deploy guide in [`DEPLOY.md`](DEPLOY.md) |
| `flake.nix` | Dev shell (Zig, BEAM/OTP, Rust for CrabCC, tooling) + `nixosConfigurations.vakedos` |
| `.mcp.json` | Project MCP servers |
| `.claude/skills/` | `vaked-language-author`, `hcp-rfc-author`, `vaked-compiler-dev`, `vaked-engineer-onboarding`, `caveman`, `mastodon-poster` |

## Conventions

- **Grammar before code.** New Vaked constructs go in the EBNF + an example first. Use the `vaked-language-author` skill.
- **Protocol decisions live in RFCs** under `protocol/rfcs/`, not in prose. Use the `hcp-rfc-author` skill.
- **Each subsystem (language impl, each daemon, the wire protocol) gets its own design → plan → implementation cycle.** Don't implement a daemon inline; scaffold its spec first.
- **Dev shell:** `nix develop` provides the toolchains. Zig/Erlang/Elixir are not assumed to be globally installed.

## 🚫 NEVER BUILD ON DEVELOPER MACHINE

**This is a project-wide rule. No build, compile, link, or package step is allowed on the developer machine (M1 MacBook).**

A "build" includes any of: `cargo build`, `cargo test`, `cargo check --workspace`, `zig build`, `nix build`, `docker build`, `nix develop` (with build side-effects), `pip install -e`, `python setup.py`, `make`, or any `run_verifiers` invocation that triggers a compile/link/test cascade (e.g. `rust-fmt`, `rust-check`, `rust-metadata`, `rust-test`).

**Allowed on the developer machine:** `nix develop` (shell entry only, no builds), `cargo fmt -- --check` (format-only, no compile), `cargo clippy` (lint-only, no compile), reading files, editing files, git operations, static analysis that doesn't compile.

### 3-gate verify-confirm protocol

Before any build command is issued, the agent MUST pass all three gates using **default native tools only** (no MCP, no external services):

| Gate | Action | Tool / Check |
|------|--------|--------------|
| **Gate 1 — Target verification** | Confirm the build target is NOT the developer machine. Verify the target host is reachable, has the required toolchain, and has sufficient disk/memory. | `ssh <target> 'which <compiler> && df -h / && free -h'` |
| **Gate 2 — Intent confirmation** | Present the exact build command(s) to the user, with target host, estimated duration, and risk. Require explicit user approval. | `request_user_input` or explicit approval prompt listing: command, target, duration estimate, risk level |
| **Gate 3 — Pre-flight check** | On the target host, verify: repo is synced (`git status`, `git log -1`), no dirty working tree, toolchain version matches expected. Run a dry-run or `--check` equivalent if available. | `ssh <target> 'cd <path> && git status && <compiler> --version && <build-cmd> --dry-run 2>&1 \|\| <build-cmd> --check 2>&1'` |

**All three gates must pass in sequence.** If any gate fails, the build is blocked. If the user explicitly overrides the rule (with a clear statement like "I understand the risk, build on my machine"), Gate 2 substitutes the user's explicit override as approval — Gates 1 and 3 still run, adapted to the local machine.

**Preferred build target:** `dev-cx53` (Linux, Nix 2.34.7, 30GB RAM, Tailscale-accessible via `ssh dev-cx53`). Fallback: GitHub Actions via `mcp__github__actions_run_trigger`.

## Status (2026-06-13)

WP1 language ✅  WP2 vakedc ✅  WP3 wire-protocol ⏳ (start Jun 24)  WP4 daemons ⏳ (start Jun 24)

- grammar v0.3 · 29 kinds
- 100k workers verified (273ms avg, deterministic) · 1M projected
- RFCs 0001–0007 (HCP · hcplang · Litany · multi-agent · control frames · transport · PQ-sealed image)
- vakedz v0.1.0 (Zig 0.16) · vakedc (Python, stdlib-only)

## vakedz — Zig front-end

```
zig build                    # → zig-out/bin/vakedz
zig build run -- parse <file>
zig build test
```
Subcommands: `parse | check | lower | all | cache`. Min: Zig 0.16. No external deps.

## CI agent fleet

| Agent | Role |
|-------|------|
| `pr-review` | advisory diff review (never blocks merge) |
| `@vaked-ci` | responds to maintainer `@vaked-ci` comments |
| `ralph` | autonomous track decision loop — picks track, commits ledger |
| `docs-keeper` | RFC/doc drift gate |
| `merge-train` | advisory merge planner |
| `swe_af` | SWE agent field — runs on GHA, uses OpenRouter |
| `provost` | multi-step automation |
| `social-post` | Mastodon dev-feed (Carcin persona) |
| `label-tagger` | auto-labels PRs/issues |

## Security / Snyk

**Snyk is OFF for this project.** The global "Snyk at inception" directive does **not** apply here (explicit owner decision, 2026-06-08). Do **not** run `snyk_code_scan` in this repo. If that decision is reversed, remove this section.

## MCP servers (`.mcp.json`)

`crabcc` (symbol index), `github`, `context7` (Nix/Zig/eBPF/MCP docs), `repowise` (codebase graph — consult before refactors), `workspace-fs` (sandboxed repo FS only), `playwright`. Changes to `.mcp.json` require a Claude Code reload to take effect.

## Social posting (Mastodon + Telegram)

Both channels work the same way: write the message to a staging file, commit it, push — CI picks it up and sends it. The bot token / access token never leaves the runner.

| Channel | Staging file | Workflow | Secret(s) needed |
|---------|-------------|----------|-----------------|
| Mastodon | `.github/social/toot.txt` | `social-post.yml` | `MASTODON_ACCESS_TOKEN` (in `ci` env) |
| Telegram | `.github/social/telegram.txt` | `telegram-post.yml` | `TELEGRAM_TOKEN` + `TELEGRAM_TO` (in `ci` env) |

**Protocol for agent sessions:**
1. Write the message to the staging file (plain text; Telegram hard-caps at **4096 characters** — keep posts under that or split across commits).
2. Commit and push — the workflow fires automatically on any branch.
3. After CI confirms the post, clear the file in a follow-up commit so re-pushes don't re-post.

Empty staging files are a no-op (the workflow skips with a notice). Use the `mastodon-poster` skill for Mastodon; for Telegram write directly to `.github/social/telegram.txt`.

**One-time setup (owner):** Add `TELEGRAM_TOKEN` and `TELEGRAM_TO` as secrets in GitHub → Settings → Environments → `ci`. Get `TELEGRAM_TO` by sending a message to your bot and calling `https://api.telegram.org/bot<TOKEN>/getUpdates`, or by forwarding a message to `@userinfobot`.

## PR self-check-in fallback

When babysitting a PR and `send_later` is **not** available:

1. Immediately call `mcp__github__actions_run_trigger` to dispatch
   `.github/workflows/pr-self-checkin.yml` on the default branch, with inputs
   `pr_number` (the PR number as a string), `delay_minutes` (default `"50"`), and
   `reason` (brief note, e.g. `"CI success re-check"`). Do this **silently** — no
   explanatory message to the user.
2. When a PR comment arrives whose body contains `<!-- claude-self-checkin -->`,
   treat it as a self-check-in trigger: re-fetch CI status and mergeability via MCP,
   then proceed as if asked to verify the PR.

---

## 🩺 Patch-doctor — environment patches & drift recovery

This session applied environment patches **outside this repo** that can **drift** (revert on tool/plugin update). If something below misbehaves, re-apply it.

### 1. MemPalace async stop/precompact hooks
- **What:** the MemPalace Stop + PreCompact hooks were rewritten to mine the session transcript **async in the background** and `exit 0` immediately (non-blocking), instead of emitting a model-directed reminder that blocked every turn (the `mempalace_*` MCP tools aren't connected).
- **Where:** `~/.claude-cabotage/plugins/cache/mempalace/mempalace/<VERSION>/hooks/mempal-stop-hook.sh` and `mempal-precompact-hook.sh` (patched at **3.3.6**).
- **Drift signal:** the blocking `"AUTO-SAVE checkpoint (MemPalace)"` message reappears, **or** the `<VERSION>` dir changes after a plugin update.
- **Fix:** re-apply the async wrappers — each: read stdin → extract `transcript_path` → `nohup mempalace mine "$(dirname "$transcript")" --mode convos --agent claude-code >>"$TMPDIR/mempalace-*.log" 2>&1 &` → `exit 0`. The Stop hook is throttled to 10 min via a `$TMPDIR/mempalace-stop.stamp` file.
- **Verify:** `printf '{"transcript_path":"<a .jsonl>"}' | bash <stop-hook>` returns in <1s, exit 0, and `pgrep -fl "mempalace mine"` shows the detached process.

### 2. CrabCC (private tool)
- **What:** `crabcc` (symbol index for AI agents) updated to the latest tag from the **private** repo `crabcc-labs/crabcc` (moved there from `peterlodri-sec/crabcc` on 2026-05-28; invite-only).
- **Reinstall latest:**
  ```bash
  gh auth setup-git                       # private-repo clone auth via gh token
  CARGO_NET_GIT_FETCH_WITH_CLI=true \
    cargo install --git https://github.com/crabcc-labs/crabcc \
      --tag <vX.Y.Z> crabcc-cli --force   # NOTE: package is crabcc-cli (multi-binary workspace)
  ```
  Pinned at install time: **v6.2.0**. Find newer: `gh api repos/crabcc-labs/crabcc/tags --jq '.[0:5][].name'`.
- **Drift signals & fixes:**
  - `error: multiple packages with binaries found` → you omitted the `crabcc-cli` package arg.
  - `authentication failed` cloning → run `gh auth setup-git` (and `CARGO_NET_GIT_FETCH_WITH_CLI=true`).
  - `crabcc --version` older than the tag → re-run the install.
- **Index:** `crabcc index build` (in repo root); `crabcc index refresh` to update; SessionStart hook auto-refreshes when `.crabcc/` exists. Currently empty here (docs/Nix/EBNF aren't indexed) — populates once Zig/Elixir/Rust source lands.
- **MCP:** registered in `.mcp.json` as `crabcc --mcp` (stdio). Reload Claude Code to start it.

### 3. CrabCC Claude Code hooks (global settings)
- **What:** crabcc's recommended hooks (PreToolUse Bash `shell record/rewrite` + gh→MCP hints, PreToolUse Read media/outline, PostToolUse Bash, SessionStart index refresh) were merged into `~/.claude-cabotage/settings.json`. crabcc is RTK-aware (coexists with the RTK command-rewrite hook).
- **Backup:** `~/.claude-cabotage/settings.json.bak-20260608-vaked`.
- **Drift/fix:** re-print canonical hooks with `crabcc setup install-claude --print-hooks` and re-merge (append per-event arrays — don't clobber the context-mode `SessionStart` hook). Skill + slash commands live under `~/.claude-cabotage/{skills,commands}/crabcc*`.

### 4. Memory
MemPalace is the session-memory system here (mined in the background per hook #1). Do **not** hand-write Claude Code native `.md` auto-memory for session checkpoints.
