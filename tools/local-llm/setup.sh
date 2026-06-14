#!/usr/bin/env bash
# Quickstart: Ollama on M3 Pro 46GB without nix-darwin.
# Installs via Homebrew + pulls models + verifies endpoint.
set -euo pipefail

echo "==> Installing Ollama"
if ! command -v ollama &>/dev/null; then
  brew install ollama
fi

echo "==> Starting Ollama service"
brew services start ollama
sleep 3

echo "==> Pulling models (this will take a while on first run)"
ollama pull llama3.3:70b-instruct-q4_K_M   # ~40GB
ollama pull qwen2.5:14b-instruct            # ~9GB

echo "==> Verifying endpoint"
curl -s http://localhost:11434/api/tags | python3 -m json.tool | grep '"name"'

echo ""
echo "Done. Endpoint: http://localhost:11434"
echo "OpenAI-compat: http://localhost:11434/v1/chat/completions"
echo ""
echo "Bench usage:"
echo "  OLLAMA_HOST=http://localhost:11434 BENCH_MODEL=llama3.3:70b-instruct-q4_K_M \\"
echo "    python3 tools/cuc-bench/bench.py"
