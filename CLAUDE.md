# CLAUDE.md — vaked-base

Foundation monorepo for **Vaked** agentic-runtime ecosystem.

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

## What this is

Vaked = flake-native **capability-graph language**. Vaked declaration compiles to typed semantic graph, then to artifacts: `flake.nix` / NixOS modules, Zig daemon configs, eBPF policy manifests, OTel config, CrabCC indexes, docs. Artifacts run on NixOS host under OTP supervision plane. Plane orchestrates single-purpose Zig enforcement daemons. eBPF = evidence layer. Operator surfaces on top.

Repo currently **scaffold**: language track = real design content. Runtime + protocol = indexed stubs. See `README.md` for full repo map, `docs/context/PROJECT_CONTEXT.md` for canonical overview.

## Structure

| Path | Purpose |
|------|---------|
| `vaked/` | Language — `grammar/vaked-v0-plus.ebnf`, `schema/`, `examples/` |
| `docs/language/` | Design series `0001…0010` + `references/` |
| `docs/context/` | `PROJECT_CONTEXT.md` (canonical overview) |
| `docs/runtime/`, `daemons/` | Runtime daemon roster (OTP + Zig) — stub |
| `docs/protocol/`, `protocol/` | HCP / Litany protocol + RFCs — stub |
| `prompts/` | `dedicated-language-session.md` kickoff prompt |
| `flake.nix` | Dev shell (Zig, BEAM/OTP, Rust for CrabCC, tooling) |
| `.mcp.json` | Project MCP servers |
| `.claude/skills/` | `vaked-language-author`, `hcp-rfc-author` |

## Conventions

- **Grammar before code.** New Vaked constructs go in EBNF + example first. Use `vaked-language-author` skill.
- **Protocol decisions live in RFCs** under `protocol/rfcs/`, not in prose. Use `hcp-rfc-author` skill.
- **Each subsystem (language impl, each daemon, wire protocol) gets own design → plan → implementation cycle.** Don't implement daemon inline; scaffold its spec first.
- **Dev shell:** `nix develop` provides toolchains. Zig/Erlang/Elixir not assumed globally installed.

## Security / Snyk

**Snyk OFF for this project.** Global "Snyk at inception" directive does **not** apply here (explicit owner decision, 2026-06-08). Do **not** run `snyk_code_scan` in this repo. If decision reversed, remove this section.

## MCP servers (`.mcp.json`)

`crabcc` (symbol index), `github`, `context7` (Nix/Zig/eBPF/MCP docs), `repowise` (codebase graph — consult before refactors), `workspace-fs` (sandboxed repo FS only), `playwright`. Changes to `.mcp.json` require Claude Code reload to take effect.

---

## 🩺 Patch-doctor — environment patches & drift recovery

Session applied environment patches **outside this repo** that can **drift** (revert on tool/plugin update). If something below misbehaves, re-apply.

### 1. MemPalace async stop/precompact hooks
- **What:** MemPalace Stop + PreCompact hooks rewritten to mine session transcript **async in background** and `exit 0` immediately (non-blocking), instead of emitting model-directed reminder that blocked every turn (`mempalace_*` MCP tools not connected).
- **Where:** `~/.claude-cabotage/plugins/cache/mempalace/mempalace/<VERSION>/hooks/mempal-stop-hook.sh` and `mempal-precompact-hook.sh` (patched at **3.3.6**).
- **Drift signal:** blocking `"AUTO-SAVE checkpoint (MemPalace)"` message reappears, **or** `<VERSION>` dir changes after plugin update.
- **Fix:** re-apply async wrappers — each: read stdin → extract `transcript_path` → `nohup mempalace mine "$(dirname "$transcript")" --mode convos --agent claude-code >>"$TMPDIR/mempalace-*.log" 2>&1 &` → `exit 0`. Stop hook throttled to 10 min via `$TMPDIR/mempalace-stop.stamp` file.
- **Verify:** `printf '{"transcript_path":"<a .jsonl>"}' | bash <stop-hook>` returns in <1s, exit 0, `pgrep -fl "mempalace mine"` shows detached process.

### 2. CrabCC (private tool)
- **What:** `crabcc` (symbol index for AI agents) updated to latest tag from **private** repo `crabcc-labs/crabcc` (moved from `peterlodri-sec/crabcc` on 2026-05-28; invite-only).
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