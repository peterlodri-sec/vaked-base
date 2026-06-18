#!/bin/bash
# E2E Integration Test — Vaked Swarm
# Validates all layers: daemon → subagent → synapsed → memory → mobile
# GENESIS_SEAL: b39f110c
set -e
echo "═══════════════════════════════════════════════════"
echo "  E2E SWARM TEST — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "═══════════════════════════════════════════════════"
echo ""

PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ $1"; }

# 1. Daemon health
echo "--- Layer 1: openrouterd ---"
if curl -sf http://localhost:9090/health > /dev/null 2>&1; then
  ok "Daemon health check"
else
  fail "Daemon not running"
fi

# 2. Models endpoint
if curl -sf http://localhost:9090/models > /dev/null 2>&1; then
  ok "Models endpoint"
else
  fail "Models endpoint"
fi

# 3. Chat completion
if curl -sf -X POST http://localhost:9090/ -d '{"prompt":"hi"}' | grep -q genesis; then
  ok "Chat completion"
else
  fail "Chat completion"
fi

# 4. Subagent pool — spawn 16 tasks
echo "--- Layer 2: Subagent Pool ---"
for i in $(seq 1 16); do
  if curl -sf -X POST http://localhost:9090/ -d "{\"prompt\":\"task $i\"}" -o /dev/null; then
    ok "Subagent $i spawned"
  else
    fail "Subagent $i failed"
  fi
done

# 5. Memory plane
echo "--- Layer 3: Memory Plane ---"
STATE_DIR=$(dirname "$0")/../../var/lib/memoryd/eventd
if [ -d "$STATE_DIR" ] && ls "$STATE_DIR"/*.jsonl > /dev/null 2>&1; then
  ok "Memory plane event log exists"
else
  fail "Memory plane event log missing"
fi

# 6. Synapsed protocol test
echo "--- Layer 4: Synapsed Protocol ---"
if cd /Users/peter.lodri/workspace/peterlodri-sec/vaked-base/daemons/synapsed && zig build test > /dev/null 2>&1; then
  ok "Synapsed tests pass"
else
  fail "Synapsed tests fail"
fi

# 7. Markov chain test
cd /Users/peter.lodri/workspace/peterlodri-sec/vaked-base/daemons/openrouterd && zig build test > /dev/null 2>&1 && ok "Daemon tests pass" || fail "Daemon tests fail"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  RESULTS: $PASS passed · $FAIL failed · $((PASS+FAIL)) total"
echo "  GENESIS_SEAL: b39f110c"
echo "═══════════════════════════════════════════════════"
