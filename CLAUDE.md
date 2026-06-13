# CLAUDE.md — vaked-base

Foundation monorepo for the **Vaked** agentic-runtime ecosystem.

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

## What this is

Vaked is a flake-native **capability-graph language**. A Vaked declaration compiles to a typed semantic graph, then to artifacts: `flake.nix` / NixOS modules, Zig daemon configs, eBPF policy manifests, OTel config, CrabCC indexes, and docs. Those run on a NixOS host under an OTP supervision plane that orchestrates single-purpose Zig enforcement daemons, with eBPF as the evidence layer and operator surfaces on top.

This repo is currently a **scaffold**: the language track is real design content; runtime and protocol are indexed stubs. See `README.md` for the full repo map and `docs/context/PROJECT_CONTEXT.md` for the canonical overview.

## Structure

| Path | Purpose |
|------|---------|
| `vaked/` | The language — `grammar/vaked-v0-plus.ebnf`, `schema/`, `examples/` |
| `docs/language/` | Design series `0001…0010` + `references/` |
| `docs/context/` | `PROJECT_CONTEXT.md` (canonical overview) |
| `docs/runtime/`, `daemons/` | Runtime daemon roster (OTP + Zig) — stub |
| `docs/protocol/`, `protocol/` | HCP / Litany protocol + RFCs — stub |
| `prompts/` | `dedicated-language-session.md` kickoff prompt |
| `hosts/` | `vakedos` bare-metal NixOS host — the materialization target (EPYC 4345P); deploy guide in [`DEPLOY.md`](DEPLOY.md) |
| `flake.nix` | Dev shell (Zig, BEAM/OTP, Rust for CrabCC, tooling) + `nixosConfigurations.vakedos` |
| `.mcp.json` | Project MCP servers |
| `.claude/skills/` | `vaked-language-author`, `hcp-rfc-author` |

## Conventions

- **Grammar before code.** New Vaked constructs go in the EBNF + an example first. Use the `vaked-language-author` skill.
- **Protocol decisions live in RFCs** under `protocol/rfcs/`, not in prose. Use the `hcp-rfc-author` skill.
- **Each subsystem (language impl, each daemon, the wire protocol) gets its own design → plan → implementation cycle.** Don't implement a daemon inline; scaffold its spec first.
- **Dev shell:** `nix develop` provides the toolchains. Zig/Erlang/Elixir are not assumed to be globally installed.

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
1. Write the message to the staging file (plain text, no length limit for Telegram).
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
