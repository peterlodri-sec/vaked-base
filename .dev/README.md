# .dev — Vaked ultimate dev environment

One-command bootstrap from any MacBook (M1/M3) to a full dev shell on
dev-cx53 with LLM proxy, CodeWhale, MCPs, memory, and all tooling.

## Quick start

```bash
bash .dev/bootstrap.sh --shell
```

## Test the LLM proxy

After bootstrap, from anywhere with Tailscale:

```bash
curl http://dev-cx53:4000/v1/chat/completions \
  -H "Authorization: Bearer $VAKED_PROXY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
# → {"choices":[{"message":{"content":"Hello! How can I assist you today?"}}]}
```

## What's included

| Component | Detail |
|-----------|--------|
| **SSH** | `dev@dev-cx53`, fresh checkout in `/home/dev/vaked-dev` |
| **LLM proxy** | port 4000, OpenRouter + Ollama models, 40+ models available |
| **API key** | set via `VAKED_PROXY_KEY` env var (never committed; rotate the leaked key) |
| **Memory** | 3 layers: MemPalace + CodeWhale builtin + codebase-memory-mcp |
| **MCPs** | GitHub, workspace-fs, codebase-memory |
| **CLIs** | `vaked-cli` (mlir/seal/proxy), `codewhale`, `rtk`, `jq`, `rg`, `gh` |
| **Models** | `openai/gpt-4o-mini`, `cloud/deepseek-v4-flash`, `ollama/qwen2.5-coder` |

## Memory three-layer stack

1. **MemPalace** — session memory, background-mined via Stop hook
   - Config: `$HOME/.mempalace`
   - Mined from every session transcript
   - Runs as detached background process (non-blocking)
2. **CodeWhale builtin** — automatic session context, no config needed
3. **codebase-memory-mcp** — GitHub-aware repository memory
   - Uses `@deusdata/codebase-memory-mcp` via npx
   - Stores results in workspace `.codebase-memory/`

## Commands

```bash
# Quick test
curl -s http://dev-cx53:4000/v1/chat/completions \
  -H "Authorization: Bearer $VAKED_PROXY_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'

# Run CodeWhale
codewhale run "check the MLIR pass pipeline"

# Build tooling
nix build .#vaked-cli
python3 -m vakedc passes tests/corpus/0024-differential/fixtures/diamond.vaked --json

# AI toolkit
rtk

# Memory exploration
ls ~/.mempalace/
ls .codebase-memory/
```

## Remote infrastructure on dev-cx53

| Service | Port | Runtime |
|---------|------|---------|
| LiteLLM proxy | 4000 | Docker (`crabcc-ollama-stack`) |
| Ollama | 11434 | Docker (CPU, 30.6GiB RAM) |
| Langfuse | 3000 | Docker (observability) |
| ChromaDB | 8001 | Docker (vector store) |
| PostgreSQL | 5432-5433 | Docker (LiteLLM + AgentField) |