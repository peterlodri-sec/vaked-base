#!/usr/bin/env bash
# deploy-llm-mesh.sh — deploy the LLM proxy mesh on local M1 + dev-cx53.
#
# Sets up:
#   M1/M3 local:  Ollama + LiteLLM proxy (port 4000)
#   dev-cx53:     LiteLLM proxy + GPU models via OpenRouter
#   Both synced via Redis over Tailscale
#
# Usage:
#   bash deploy/llmproxy/deploy-llm-mesh.sh           # deploy both
#   bash deploy/llmproxy/deploy-llm-mesh.sh local     # local only
#   bash deploy/llmproxy/deploy-llm-mesh.sh remote    # dev-cx53 only
set -euo pipefail

MODE="${1:-both}"
CONFIG="deploy/llmproxy/proxy-mesh.yaml"

echo "=== LLM proxy mesh deploy ==="

deploy_local() {
  echo "--- Local: Ollama + LiteLLM ---"
  
  # Install Ollama if missing
  if ! command -v ollama &>/dev/null; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | bash
  fi
  
  # Pull models
  for model in qwen2.5-coder:7b llama3.2:3b; do
    ollama pull "$model" 2>&1 | tail -1
  done
  
  # Start Ollama service
  ollama serve &
  
  # Start LiteLLM proxy
  echo "Starting LiteLLM proxy on port 4000..."
  litellm --config "$CONFIG" --port 4000 --drop_params &
  
  echo "  Local proxy: http://localhost:4000"
  echo "  Models: local/qwen2.5-coder, local/llama-3.2"
}

deploy_remote() {
  echo "--- Remote dev-cx53: LiteLLM + GPU models ---"
  
  ssh dev@dev-cx53 bash -c "'
    # Pull the latest config
    cd /home/dev/vaked-base-mlir
    git pull
    
    # Start LiteLLM proxy with mesh config
    echo \"Starting LiteLLM proxy on port 4000...\"
    litellm --config deploy/llmproxy/proxy-mesh.yaml --port 4000 --drop_params &
    
    echo \"  Remote proxy: http://dev-cx53:4000\"
    echo \"  Models: remote/deepseek-coder, remote/qwen2.5-72b\"
    echo \"  Cloud fallbacks: cloud/deepseek-v4-flash, cloud/claude-opus-4\"
  '"
}

case "$MODE" in
  both)
    deploy_local
    deploy_remote
    echo ""
    echo "=== Mesh deployed ==="
    echo "  Local:  http://localhost:4000 → Ollama models"
    echo "  Remote: http://dev-cx53:4000  → GPU models"
    echo "  Cloud:  OpenRouter fallback"
    echo "  Cache:  Redis sync via Tailscale"
    ;;
  local)
    deploy_local
    ;;
  remote)
    deploy_remote
    ;;
  *)
    echo "Usage: $0 [local|remote|both]"
    exit 1
    ;;
esac
