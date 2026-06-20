# .dev — Vaked ultimate dev environment
#
# One-command bootstrap from any MacBook (M1/M3) to a full dev shell on
# dev-cx53 with LLM proxy, CodeWhale, and all tooling configured.

## Quick start

```bash
# From repo root:
bash .dev/bootstrap.sh --shell
```

This connects to dev-cx53, clones/updates vaked-dev, sets up env vars,
configures CodeWhale MCPs, and opens an SSH shell with everything loaded.

## What's included

| Component | Detail |
|-----------|--------|
| SSH to dev-cx53 | `dev@dev-cx53`, fresh checkout in `/home/dev/vaked-dev` |
| Env setup | `.dev/env.sh` — LLM proxy, model routing, git identity, paths |
| LLM proxy | `cloud/deepseek-v4-flash`, `cloud/claude-opus-4`, `remote/deepseek-coder` |
| CodeWhale | `codewhale` CLI — MCPs: github, workspace-fs (no CrabCC, no Playwright) |
| vaked-cli | Go CLI for mlir/seal/proxy subcommands |
| Models | Request model `local/qwen2.5-coder` for Ollama, or `cloud/*` for API |

## Manual steps

```bash
# Clone + env
ssh dev@dev-cx53
cd /home/dev && git clone https://github.com/peterlodri-sec/vaked-base vaked-dev
cd vaked-dev && source .dev/env.sh

# Build tooling
nix build .#vaked-cli
python3 -m vakedc passes tests/corpus/0024-differential/fixtures/diamond.vaked --json

# CodeWhale
codewhale run "check the MLIR pass pipeline"
```

## Remote data

| Service | Location | Notes |
|---------|----------|-------|
| Ollama models | `/root/.ollama/models/` | GPU-backed, runs in Docker |
| LiteLLM proxy | port 4000 | Postgres-backed, Docker container |
| vaked-dev | `/home/dev/vaked-dev/` | Fresh checkout per session |
