#!/bin/bash
# Run in crabcc-cleanup worktree to remove stale dirs
cd ~/workspace/peterlodri-sec/crabcc-cleanup
rm -rf agents/ apps/ assets/ commands/ compact-server/ contrib/ desktop/ editors/ examples/ experiments/ extensions/ install/ internal_agents/ man/ nix/ patches/ schema/ scripts/ skill/ taskfiles/ tools/
git add -A && git commit -m "cleanup: remove stale root directories" && git push origin cleanup/trim-to-mcp
echo "✅ Done"
