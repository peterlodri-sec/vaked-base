# MCP fleet — vaked-oracle

Fleet MCPs / observability for the reverser team. **`.mcp.json` changes need a Claude Code
reload to take effect**, and the cloud ones need keys (operator secrets). Status below.

## Wired into `.mcp.json`

### Serena (✅ added)
LSP-based semantic-code MCP — 40+ languages incl **C++ via clangd**: `find_symbol`,
`find_referencing_symbols`, token-efficient symbolic edits. **Source-code only (not
binaries).** Two roles here: (1) the agent-facing C++ tool that complements the in-loop
ctags provider (crabcc is C-only); (2) token-efficient editing of our own Python/Zig source.

- Entry: `uvx --from git+https://github.com/oraios/serena serena-mcp-server --context ide-assistant`.
- **Do NOT install via an MCP marketplace** (their README — marketplace commands are stale);
  the canonical uvx-from-git form above is correct. Needs `uv` + first-run network fetch.
- Reload Claude Code after the `.mcp.json` change for it to start.

## OpenRouter key (diverse panel) — stored for reuse

The OpenRouter API key (for `feketecs` deepseek-v4-flash + `anstetten` deepseek-v4-pro) is
stored secured (chmod 600), never committed:
- **M3:** `~/.config/oracle/openrouter.key`
- **dev-cx53 (revdev):** `~/.config/oracle/openrouter.env` (`export OPENROUTER_API_KEY=…`)

`task -d tools/oracle team` auto-sources the box env (no-op if absent), so diverse-panel
runs are keyed automatically. Keyless-local runs use `PANEL=tools/oracle/panel.local.json`
(no secret). Rotate by overwriting both files.

## Observability — Langfuse (push, not MCP)

Langfuse (`langfuse.crabcc.app`) is **observability via SDK push**, not an MCP query server:
the team sends spans/costs TO Langfuse; you read them in the dashboard. So it is **not** an
`.mcp.json` entry — it's an optional instrumentation of `panel.OpenAIChatClient`.

- Follow-up (small): wrap each `OpenAIChatClient.__call__` to emit a Langfuse span
  (model, tokens, cost, latency) when `LANGFUSE_HOST=https://langfuse.crabcc.app` +
  `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` are set; no-op otherwise (keyless stays clean).
- Payoff: real per-model token/cost/quality replaces the `COST_ANALYSIS.md` estimates, and
  the debate panel becomes observable (which model wins, where spend goes).

## Deferred

### Frida-MCP (→ slice 5)
From `darbra/awesome-ai-reverse` — drive Frida dynamic instrumentation over MCP. Natural
complement to the oracle's dynamic-evidence layer (Frida + eBPF watcher). Wire when the
dynamic layer gets its multi-agent pass.

### GhidraMCP (not now)
Considered; dropped for this round (pyghidra already covers decompilation in-loop; the
community Ghidra MCP needs a running Ghidra+plugin — heavy on the headless box). Revisit if
agents need live, interactive decompiler queries.

## Outside-model prompt dogfeed (zero-infra transparency)

The oracle's non-hosted (OpenRouter) calls are surfaced to ONE rolling GitHub issue
("oracle: outside-model prompt dogfeed") — a human-visible cost/prompt audit that complements
the Langfuse SDK push. A team run with `ORACLE_DOGFEED_LOG=<path>` set makes the panel sink
(`panel.OpenAIChatClient._dogfeed`) append one JSONL record per outside-model call (model,
prompt sha + first line, completion tokens, cost — **no full prompt/response, no key**; keyless
local models are never logged). Then, from where `gh` is authed (M3): `task -d tools/oracle
dogfeed` (or `DRY=1 ... dogfeed` to preview) find-or-creates the issue and appends the run's
summary. Posting is a deliberate step, never in a run's hot path.

**CI auto-post (fire-and-forget from the box).** For runs on dev-cx53 (no `gh` auth there),
point the sink at the staging file and push it: `ORACLE_DOGFEED_LOG=.github/dogfeed/outside-model.jsonl`
(truncate per run), `git commit && git push`. The `dogfeed` workflow (`.github/workflows/dogfeed.yml`)
fires on that path and posts to the rolling issue via the built-in `GITHUB_TOKEN` (`issues: write`)
— the token never leaves the runner. Empty staging file = no-op; clear it after CI confirms (the
social-post protocol). See `.github/dogfeed/README.md`.
