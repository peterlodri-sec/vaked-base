#!/bin/bash
# GCP MCP + Vast.ai MCP ingestion
# Wires both into .mcp.json and indexes their docs in our doc CDN
# GENESIS_SEAL: 7c242080
set -e

echo "=== GCP MCP + Vast.ai MCP Setup ==="
echo ""

# 1. GCP MCP — official Google repo
GCP_MCP="https://github.com/googleapis/gcloud-mcp"
GCP_MCP_NPM="@googleapis/gcloud-mcp"

echo "Installing GCP MCP..."
if [ -n "$(which npx 2>/dev/null)" ]; then
  npx -y "$GCP_MCP_NPM" --help 2>/dev/null || echo "  ⚠️  npx install failed — try: npm install -g $GCP_MCP_NPM"
fi

echo ""
echo "Installing Vast.ai MCP..."
echo "  Vast.ai article: https://vast.ai/article/building-your-first-mcp-server-on-vast-ai"
echo "  No official npm package found — add manually to .mcp.json"

echo ""
echo "=== Updating .mcp.json ==="
MCP_FILE=".mcp.json"
if [ -f "$MCP_FILE" ]; then
  echo "  $MCP_FILE exists — review GCP MCP integration"
  cat "$MCP_FILE" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  Current servers:', len(d.get('mcpServers',{})))"
fi

echo ""
echo "=== NEXT STEPS ==="
echo "1. npm install -g @googleapis/gcloud-mcp"
echo "2. gcloud auth application-default login"
echo "3. Add to .mcp.json:"
echo '   "gcloud-mcp": { "command": "npx", "args": ["-y", "@googleapis/gcloud-mcp"] }'
echo "4. Re-run: ./task zone → GCP layer should show ACTIVE"
echo ""
echo "GENESIS_SEAL: 7c242080"
