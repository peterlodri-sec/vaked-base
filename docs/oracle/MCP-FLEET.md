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
