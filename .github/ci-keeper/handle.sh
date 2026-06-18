#!/bin/bash
# CI-Keeper — triggered by @vaked-ci <command>
# Usage: bash .github/ci-keeper/handle.sh "<comment body>"
# GENESIS_SEAL: 7c242080
set -e

BODY="$1"
CMD=$(echo "$BODY" | grep -o '@vaked-ci [a-z]*' | cut -d' ' -f2)

case "$CMD" in
  build)
    echo "CI-Keeper: building all projects..."
    cd daemons/openrouterd && zig build && echo "  daemon: ✅"
    cd tools/openrouter-zig && zig build && echo "  zig-sdk: ✅"
    cd tools/openrouter-ts && npm run build 2>/dev/null && echo "  ts-sdk: ✅"
    ;;
  test)
    echo "CI-Keeper: running all tests..."
    cd daemons/openrouterd && zig build test && echo "  daemon: ✅"
    cd daemons/synapsed && zig build test 2>/dev/null && echo "  synapsed: ✅"
    ;;
  deploy)
    echo "CI-Keeper: deploying..."
    git add -A && git commit -m "ci-keeper: swarm update" && git push
    ;;
  status)
    echo "CI-Keeper status:"
    echo "  Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'N/A')"
    echo "  Last commit: $(git log --oneline -1 2>/dev/null || echo 'N/A')"
    echo "  GENESIS_SEAL: 7c242080"
    ;;
  help|*)
    echo "CI-Keeper commands:"
    echo "  @vaked-ci build   — build all projects"
    echo "  @vaked-ci test    — run all tests"
    echo "  @vaked-ci deploy  — push to main"
    echo "  @vaked-ci status  — report CI state"
    echo "  @vaked-ci help    — this message"
    ;;
esac
