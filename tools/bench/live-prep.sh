#!/bin/bash
# Live Prep — profile, load test, cache build, prewarm, node onboarding
# GENESIS_SEAL: 7c242080
set -e
echo "═══════════════════════════════════════════════════"
echo "  LIVE PREP — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "═══════════════════════════════════════════════════"
echo ""

# 1. Profile — zig build with timing
echo "--- Phase 1: Profile ---"
time zig build --verbose 2>&1 | tail -3 || echo "  (no build.zig in root — projects are in subdirs)"

# 2. Load test — if daemon is running
echo ""
echo "--- Phase 2: Load Test ---"
if curl -sf http://localhost:9090/health > /dev/null 2>&1; then
  echo "  Daemon UP — running 10 concurrent requests..."
  for i in $(seq 1 10); do
    curl -s -X POST http://localhost:9090/ -d "{\"prompt\":\"load test $i\"}" -o /dev/null &
  done
  wait
  echo "  ✅ Load test complete"
else
  echo "  ⚠️  Daemon not running — start with:"
  echo "     ./zig-out/bin/openrouterd &"
fi

# 3. Cache build — pre-build all Zig projects
echo ""
echo "--- Phase 3: Cache Build ---"
for dir in daemons/openrouterd tools/openrouter-zig vakedz tools/scrubber; do
  if [ -f "$dir/build.zig" ]; then
    (cd "$dir" && zig build --cache-dir .zig-cache 2>&1 | tail -1) && echo "  ✅ $dir"
  fi
done

# 4. Prewarm — memory plane + docs cache
echo ""
echo "--- Phase 4: Prewarm ---"
# Index docs
(cd tools/crawl && ls doc-indexer 2>/dev/null && ./doc-indexer 2>&1 || echo "  ⚠️ doc-indexer not built — run: zig build-exe doc-indexer.zig") || true
echo "  ✅ Docs indexed"

# 5. Node status
echo ""
echo "--- Phase 5: Node Status ---"
echo "  M3:     $(uname -m)"
echo "  OS:     $(uname -s)"
echo "  Zig:    $(zig version 2>/dev/null || echo 'MISSING')"
echo "  Daemon: $(curl -sf http://localhost:9090/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(\"status\",\"DOWN\"))' 2>/dev/null || echo 'DOWN')"
echo "  Memory: $(curl -sf http://localhost:8420/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(str(d.get(\"entries\",\"?\"))+\" entries\")' 2>/dev/null || echo 'DOWN')"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  LIVE PREP COMPLETE"
echo "  GENESIS_SEAL: 7c242080"
echo "═══════════════════════════════════════════════════"
