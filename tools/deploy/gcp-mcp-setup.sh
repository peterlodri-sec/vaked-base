#!/bin/bash
set -e
echo "=== GCP MCP Setup ==="
echo ""
echo "The correct npm package name might be @google-cloud/gcloud-mcp or similar."
echo "Running search..."
npm search @googleapis/gcloud-mcp 2>/dev/null || echo "  Not on npm — install from source:"
echo "  git clone https://github.com/googleapis/gcloud-mcp.git"
echo "  cd gcloud-mcp && npm install && npm run build"
echo ""
echo "Meanwhile, here is the manual .mcp.json entry:"
echo ""
cat << 'MCPEOF'
{
  "mcpServers": {
    "gcloud": {
      "command": "npx",
      "args": ["-y", "@googleapis/gcloud-mcp"],
      "env": {
        "CLOUDSDK_CORE_PROJECT": "datapy-spider"
      }
    }
  }
}
MCPEOF
echo ""
echo "GENESIS_SEAL: 7c242080"
