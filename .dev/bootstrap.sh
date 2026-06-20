#!/usr/bin/env bash
# bootstrap.sh — Vaked ultimate dev shell (macOS → dev-cx53)
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'; BOLD='\033[1m'
info()  { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err()   { printf "${RED}✗${NC} %s\n" "$*"; }
header(){ printf "\n${BOLD}=== %s ===${NC}\n" "$*"; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

REMOTE_USER="${REMOTE_USER:-dev}"
REMOTE_HOST="${REMOTE_HOST:-dev-cx53}"
REMOTE_PATH="${REMOTE_PATH:-/home/dev/vaked-dev}"
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
LOCAL_PORT="${LOCAL_PORT:-4000}"

# ── Prerequisites ──────────────────────────────────────────────────────────
header "Prerequisites"
for cmd in ssh gh; do
  command -v "$cmd" &>/dev/null && info "$cmd found" || { err "$cmd not found"; missing=1; }
done
if [ "${missing:-0}" -eq 1 ]; then
  err "missing required commands (ssh, gh) — install them first"
  exit 1
fi

# ── SSH check ──────────────────────────────────────────────────────────────
header "SSH"
ssh -q "$REMOTE_USER@$REMOTE_HOST" exit 2>/dev/null \
  && info "SSH OK" \
  || { err "Cannot reach $REMOTE_USER@$REMOTE_HOST — Tailscale up?"; exit 1; }

# ── Remote workspace ───────────────────────────────────────────────────────
header "Remote workspace"
ssh "$REMOTE_USER@$REMOTE_HOST" "
  if [ -d $REMOTE_PATH ]; then cd $REMOTE_PATH && git fetch origin && git checkout $BRANCH && git pull --ff-only
  else git clone https://github.com/peterlodri-sec/vaked-base.git $REMOTE_PATH && cd $REMOTE_PATH; fi
  echo \"Checked out: \$(git log --oneline -1)\"
" 2>&1 | while read -r line; do info "$line"; done

# ── Install tools on remote ────────────────────────────────────────────────
header "Tooling"
ssh "$REMOTE_USER@$REMOTE_HOST" "
  # jq, ripgrep
  command -v jq &>/dev/null || (sudo nix-env -iA nixpkgs.jq 2>/dev/null || sudo apt-get install -y jq 2>/dev/null) && echo 'jq OK' || echo 'jq not installed'
  command -v rg &>/dev/null || (sudo nix-env -iA nixpkgs.ripgrep 2>/dev/null || sudo apt-get install -y ripgrep 2>/dev/null) && echo 'rg OK' || echo 'rg not installed'
  # gh
  command -v gh &>/dev/null && echo 'gh: \$(gh --version | head -1)' || echo 'gh not installed'
  # @usewhale/whale — DeepSeek-optimized coding agent
  command -v whale &>/dev/null || npm install -g @usewhale/whale 2>/dev/null && echo "whale: OK" || echo "whale not installed"
  # rtk — AI toolkit
  command -v rtk &>/dev/null || {
    curl -sSfL https://github.com/rtk-ai/rtk/releases/latest/download/rtk-x86_64-unknown-linux-musl.tar.gz -o /tmp/rtk.tar.gz 2>/dev/null
    tar -xzf /tmp/rtk.tar.gz -C /tmp 2>/dev/null && chmod +x /tmp/rtk 2>/dev/null
    sudo mv /tmp/rtk /usr/local/bin/rtk 2>/dev/null && echo 'rtk: OK' || echo 'rtk not installed'
  }
  " 2>&1 | while read -r line; do info "$line"; done

# ── LLM proxy check ────────────────────────────────────────────────────────
header "LLM proxy mesh"
PROXY="http://$REMOTE_HOST:4000"
API_KEY="${VAKED_PROXY_KEY:-${OPENAI_API_KEY:-}}"
if [ -z "$API_KEY" ]; then
  warn "no proxy key set — export VAKED_PROXY_KEY (or OPENAI_API_KEY) to test the proxy; skipping auth check"
else
  if curl -s -o /dev/null -w "%{http_code}" "$PROXY/v1/models" -H "Authorization: Bearer $API_KEY" --connect-timeout 3 | grep -q "200"; then
    info "Proxy live — key valid"
  else
    warn "Proxy at $PROXY not reachable"
  fi
fi

# ── Environment file ───────────────────────────────────────────────────────
header "Environment"
ssh "$REMOTE_USER@$REMOTE_HOST" "cat > $REMOTE_PATH/.dev/env.sh << 'ENVEOF'
export VAKED_PROJECT=vaked-base
export VAKED_REMOTE=$REMOTE_HOST
export VAKED_USER=$REMOTE_USER
export VAKED_BRANCH=$BRANCH
export VAKED_WORKSPACE=$REMOTE_PATH

# LLM proxy — test with:
#   curl http://$REMOTE_HOST:4000/v1/chat/completions \\
#     -H \"Authorization: Bearer $API_KEY\" \\
#     -H \"Content-Type: application/json\" \\
#     -d '{\"model\":\"openai/gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'
export OPENAI_BASE_URL=http://$REMOTE_HOST:4000/v1
export OPENAI_API_KEY=$API_KEY
export LITELLM_PROXY_URL=http://$REMOTE_HOST:4000

# Model routing
export VAKED_DEFAULT_MODEL=cloud/deepseek-v4-flash
export VAKED_CODING_MODEL=cloud/claude-opus-4
export VAKED_FAST_MODEL=remote/deepseek-coder
export VAKED_GLM5_MODEL=z-ai/glm-5
export VAKED_GLM45AIR_MODEL=z-ai/glm-4.5-air

# Memory — three layers:
# 1) CodeWhale built-in session memory (automatic)
# 2) MemPalace (local, background-mined)
# 3) codebase-memory-mcp (DeusData, GitHub-aware)
export MEMPALACE_HOME=\$HOME/.mempalace
export CODEBASE_MEMORY_PATH=\$VAKED_WORKSPACE/.codebase-memory

# Paths
export PATH=\$PATH:$REMOTE_PATH/tools/vaked-cli:/usr/local/bin
export VAKED_CLI=$REMOTE_PATH/tools/vaked-cli/vaked-cli

# Git
export GIT_AUTHOR_NAME=\"Peter Lodri\"
export GIT_AUTHOR_EMAIL=cabotage@pm.me
export GIT_COMMITTER_NAME=\"Peter Lodri\"
export GIT_COMMITTER_EMAIL=cabotage@pm.me
ENVEOF
chmod +x $REMOTE_PATH/.dev/env.sh && echo 'env.sh OK'"

# ── MCP config ─────────────────────────────────────────────────────────────
header "MCP servers"
ssh "$REMOTE_USER@$REMOTE_HOST" "cat > $REMOTE_PATH/.dev/whale-config.json" << 'MCPJSON'
{
  "mcpServers": {
    "github": {
      "command": "gh",
      "args": ["mcp", "--json"],
      "enabled": true
    },
    "workspace-fs": {
      "command": "codewhale",
      "args": ["mcp", "workspace-fs", "--path", "'"$REMOTE_PATH"'"],
      "enabled": true
    },
    "codebase-memory": {
      "command": "npx",
      "args": ["-y", "@deusdata/codebase-memory-mcp"],
      "enabled": true
    }
  },
  "llm": {
    "provider": "openai",
    "baseUrl": "http://dev-cx53:4000/v1",
    "apiKey": "'"$API_KEY"'",
    "defaultModel": "cloud/deepseek-v4-flash",
    "models": {
      "cloud/deepseek-v4-flash": {"type": "chat"},
      "cloud/claude-opus-4": {"type": "chat"},
      "openai/gpt-4o-mini": {"type": "chat"},
      "ollama/qwen2.5-coder": {"type": "chat"}
    }
  },
  "agent": {
    "name": "whale",
    "maxTurns": 50,
    "maxTokens": 8192,
    "temperature": 0.3
  },
  "memory": {
    "mempalace": true,
    "codewhaleBuiltin": true,
    "codebaseMemory": true
  }
}
MCPJSON

# ── rtk config ─────────────────────────────────────────────────────────────
ssh "$REMOTE_USER@$REMOTE_HOST" "
  if command -v rtk &>/dev/null; then
    rtk init $REMOTE_PATH 2>/dev/null || true
    echo 'rtk: initialized'
  fi
" 2>&1 | while read -r line; do info "$line"; done

# ── Summary ────────────────────────────────────────────────────────────────
header "Ready"
echo ""
echo "  ${BOLD}vaked dev shell${NC}"
echo "  Remote:  ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH} (${BRANCH})"
echo "  Proxy:   ${PROXY}"
echo "  Models:  cloud/deepseek-v4-flash  openai/gpt-4o-mini  ollama/qwen2.5-coder"
echo "  Memory:  MemPalace + CodeWhale builtin + codebase-memory-mcp"
echo "  Tools:   jq rg gh rtk codewhale vaked-cli"
echo ""
echo "  ${BOLD}Commands:${NC}"
echo "    ssh ${REMOTE_USER}@${REMOTE_HOST}"
echo "    cd ${REMOTE_PATH} && source .dev/env.sh"
echo "    nix build .#vaked-cli"
echo "    codewhale run 'your prompt'"
echo "    rtk"
echo ""

if [[ "${1:-}" == "--shell" ]]; then
  ssh -t "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_PATH && source .dev/env.sh && echo 'VAKED dev — ${REMOTE_HOST}:${REMOTE_PATH}' && exec bash -i"
fi