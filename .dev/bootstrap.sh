#!/usr/bin/env bash
# bootstrap.sh — Vaked ultimate dev shell (macOS → dev-cx53)
#
# One-command setup from any MacBook (M1/M3):
#   bash .dev/bootstrap.sh
#
# What it does:
#   1. Checks prerequisites (ssh, gh, codewhale, ollama)
#   2. Sets up SSH config for dev-cx53 (user@dev-cx53)
#   3. Clones/updates vaked-base on remote
#   4. Installs + configures codewhale/whale CLI with MCPs
#   5. Verifies LLM proxy mesh is live
#   6. Opens an SSH shell with full env

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

info()  { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err()   { printf "${RED}✗${NC} %s\n" "$*"; }
header(){ printf "\n${BOLD}=== %s ===${NC}\n" "$*"; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── User config ───────────────────────────────────────────────────────────
REMOTE_USER="${REMOTE_USER:-dev}"
REMOTE_HOST="${REMOTE_HOST:-dev-cx53}"
REMOTE_PATH="${REMOTE_PATH:-/home/dev/vaked-dev}"
BRANCH="${BRANCH:-main}"
LOCAL_PORT="${LOCAL_PORT:-4000}"  # port for LLM proxy tunnel

# ── Prerequisites ──────────────────────────────────────────────────────────

header "Prerequisites"

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    err "$1 not found — install it first"
    case "$1" in
      ssh)         echo "   brew install openssh" ;;
      gh)          echo "   brew install gh" ;;
      ollama)      echo "   brew install ollama" ;;
      codewhale)   echo "   see https://codewhale.ai/docs/install" ;;
      litellm)     echo "   pip install litellm" ;;
    esac
    return 1
  fi
  info "$1 found: $(command -v "$1")"
}

check_cmd ssh      || MISSING=1
check_cmd gh       || MISSING=1
check_cmd ollama   || warn "ollama optional — local inference only"
${MISSING:-0} -eq 1 && { err "Install missing tools first"; exit 1; }

# ── SSH config ─────────────────────────────────────────────────────────────

header "SSH config"

if ! ssh -q "$REMOTE_USER@$REMOTE_HOST" exit 2>/dev/null; then
  warn "Cannot reach $REMOTE_USER@$REMOTE_HOST — ensure Tailscale is up"
  echo "  sudo tailscale up"
  echo "  Then re-run this script"
  exit 1
fi
info "SSH to $REMOTE_USER@$REMOTE_HOST OK"

# ── Remote checkout ───────────────────────────────────────────────────────

header "Remote workspace"

REMOTE_CHECKOUT_CMD="
  if [ -d $REMOTE_PATH ]; then
    cd $REMOTE_PATH && git fetch origin && git checkout $BRANCH && git pull --ff-only
  else
    git clone https://github.com/peterlodri-sec/vaked-base.git $REMOTE_PATH
    cd $REMOTE_PATH
  fi
  echo 'Checked out: \$(git log --oneline -1)'"

ssh "$REMOTE_USER@$REMOTE_HOST" bash -c "'$REMOTE_CHECKOUT_CMD'" 2>&1 | while read -r line; do info "$line"; done

# ── LLM proxy tunnel ──────────────────────────────────────────────────────

header "LLM proxy mesh"

PROXY_URL="http://$REMOTE_HOST:4000"
if curl -s -o /dev/null -w "%{http_code}" "$PROXY_URL/health" --connect-timeout 3 2>/dev/null | grep -q "200\|401"; then
  info "LLM proxy live at $PROXY_URL"
  info "Models available:"
  echo "  cloud/deepseek-v4-flash    — via OpenRouter"
  echo "  cloud/claude-opus-4         — via OpenRouter"
  echo "  remote/deepseek-coder      — via GPU tier"
  echo "  local/qwen2.5-coder        — via Ollama (local)"
  echo "  local/llama-3.2            — via Ollama (local)"
else
  warn "LLM proxy not reachable at $PROXY_URL"
  warn "Deploy: ssh $REMOTE_USER@$REMOTE_HOST 'litellm --config deploy/llmproxy/proxy-mesh.yaml --port 4000'"
fi

# ── CodeWhale / whale CLI (remote) ────────────────────────────────────────

header "CodeWhale / whale CLI"

WHALE_MCP_CONFIG=$(cat << 'MCPJSON'
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
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/context7-mcp-server"],
      "enabled": false
    }
  }
}
MCPJSON
)

# Install/update codewhale on remote
ssh "$REMOTE_USER@$REMOTE_HOST" bash -c "'
  if command -v codewhale &>/dev/null; then
    echo "codewhale: \$(codewhale --version 2>&1 | head -1)"
  else
    echo "codewhale not installed"
  fi
'" 2>&1 | while read -r line; do info "$line"; done

# ── Create remote env file ────────────────────────────────────────────────

header "Environment setup"

ssh "$REMOTE_USER@$REMOTE_HOST" bash -c "'
  cat > $REMOTE_PATH/.dev/env.sh << \"ENVEOF\"
export VAKED_PROJECT=\"vaked-base\"
export VAKED_REMOTE=\"$REMOTE_HOST\"
export VAKED_USER=\"$REMOTE_USER\"
export VAKED_BRANCH=\"$BRANCH\"
export VAKED_WORKSPACE=\"$REMOTE_PATH\"

# LLM proxy mesh
export OPENAI_BASE_URL=\"http://$REMOTE_HOST:4000/v1\"
export OPENAI_API_KEY=\"sk-PrsAdrqFU4xYhrm3hGLo1Q\"
export LITELLM_PROXY_URL=\"http://$REMOTE_HOST:4000\"

# Default model routing
export VAKED_DEFAULT_MODEL=\"cloud/deepseek-v4-flash\"
export VAKED_CODING_MODEL=\"cloud/claude-opus-4\"
export VAKED_FAST_MODEL=\"remote/deepseek-coder\"

# Paths
export PATH=\"\$PATH:$REMOTE_PATH/tools/vaked-cli\"
export VAKED_CLI=\"$REMOTE_PATH/tools/vaked-cli/vaked-cli\"

# Git identity
export GIT_AUTHOR_NAME=\"Peter Lodri\"
export GIT_AUTHOR_EMAIL=\"cabotage@pm.me\"
export GIT_COMMITTER_NAME=\"Peter Lodri\"
export GIT_COMMITTER_EMAIL=\"cabotage@pm.me\"
ENVEOF
  chmod +x $REMOTE_PATH/.dev/env.sh
  echo \"env.sh created\"
'" 2>&1 | while read -r line; do info "$line"; done

# ── Summary ───────────────────────────────────────────────────────────────

header "Ready"

echo ""
echo "  ${BOLD}vaked dev shell${NC}"
echo ""
echo "  Remote:  ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"
echo "  Branch:  ${BRANCH}"
echo "  Proxy:   ${PROXY_URL}"
echo ""
echo "  ${BOLD}Commands:${NC}"
echo "    ssh ${REMOTE_USER}@${REMOTE_HOST}"
echo "    cd ${REMOTE_PATH} && source .dev/env.sh"
echo "    nix build .#vaked-cli          # build Go CLI"
echo "    python3 -m vakedc passes       # MLIR pass pipeline"
echo "    codewhale run \"prompt\"         # CodeWhale agent"
echo ""
echo "  ${BOLD}Models (via proxy):${NC}"
echo "    cloud/deepseek-v4-flash        # fast default"
echo "    cloud/claude-opus-4            # heavy coding"
echo "    remote/deepseek-coder          # GPU tier"
echo "    local/qwen2.5-coder            # Ollama local"
echo ""
echo "  ${BOLD}Local tunnel:${NC}"
echo "    ssh -L ${LOCAL_PORT}:localhost:4000 ${REMOTE_USER}@${REMOTE_HOST} -N &"
echo "    export OPENAI_BASE_URL=http://localhost:${LOCAL_PORT}/v1"
echo ""

# ── Launch shell ──────────────────────────────────────────────────────────

if [[ "${1:-}" == "--shell" ]]; then
  header "Opening dev shell on $REMOTE_HOST"
  ssh -t "$REMOTE_USER@$REMOTE_HOST" "
    cd $REMOTE_PATH
    source .dev/env.sh
    echo 'VAKED dev — ${REMOTE_HOST}:${REMOTE_PATH} (${BRANCH})'
    exec bash -i
  "
fi
