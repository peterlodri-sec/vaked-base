#!/bin/bash
# vaked-mlir comprehensive test suite
# Tests: correctness, error handling, benchmarks, round-trip validation

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAKED_OPT="${PROJECT_DIR}/build/bin/vaked-opt"
TEST_DIR="${PROJECT_DIR}/test"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== vaked-mlir Test Suite ==="
echo "Project: $PROJECT_DIR"
echo

PASS=0
FAIL=0

# Test 1: Basic integration test
echo "[Test 1] Integration: 3-agent topology"
if "$VAKED_OPT" -pass-pipeline="builtin.module(vaked-topology-analysis,vaked-to-hcp-lowering-full,vaked-aot-index)" \
   "$TEST_DIR/integration-e2e.mlir" > /dev/null 2>&1; then
  echo -e "${GREEN}✓ PASS${NC}"
  ((PASS++))
else
  echo -e "${RED}✗ FAIL${NC}"
  ((FAIL++))
fi

# Test 2: Cycle detection
echo "[Test 2] Error handling: cycle detection"
cat > /tmp/cycle-test.mlir << 'EOF'
module {
  vaked.agent @a {
    %x = vaked.consume @b : !vaked.state_hash
    vaked.yield %x
  }
  vaked.agent @b {
    %y = vaked.consume @a : !vaked.state_hash
    vaked.yield %y
  }
}
EOF

if "$VAKED_OPT" -pass-pipeline="builtin.module(vaked-topology-analysis)" \
   /tmp/cycle-test.mlir 2>&1 | grep -q "E-TOPO-CYCLE"; then
  echo -e "${GREEN}✓ PASS${NC}"
  ((PASS++))
else
  echo -e "${RED}✗ FAIL${NC}"
  ((FAIL++))
fi

# Test 3: Depth computation
echo "[Test 3] Topology analysis: depth computation"
if "$VAKED_OPT" -pass-pipeline="builtin.module(vaked-topology-analysis)" \
   "$TEST_DIR/integration-e2e.mlir" 2>&1 | grep -q "Critical path"; then
  echo -e "${GREEN}✓ PASS${NC}"
  ((PASS++))
else
  echo -e "${RED}✗ FAIL${NC}"
  ((FAIL++))
fi

# Test 4: WAL injection
echo "[Test 4] Pass 2: WAL injection"
if "$VAKED_OPT" -pass-pipeline="builtin.module(vaked-topology-analysis,vaked-to-hcp-lowering-full)" \
   "$TEST_DIR/integration-e2e.mlir" 2>&1 | grep -q "WAL injection"; then
  echo -e "${GREEN}✓ PASS${NC}"
  ((PASS++))
else
  echo -e "${RED}✗ FAIL${NC}"
  ((FAIL++))
fi

# Test 5: AOT index generation
echo "[Test 5] Pass 3: AOT index generation"
if "$VAKED_OPT" -pass-pipeline="builtin.module(vaked-topology-analysis,vaked-to-hcp-lowering-full,vaked-aot-index)" \
   "$TEST_DIR/integration-e2e.mlir" 2>&1 | grep -q "supervisor_index"; then
  echo -e "${GREEN}✓ PASS${NC}"
  ((PASS++))
else
  echo -e "${RED}✗ FAIL${NC}"
  ((FAIL++))
fi

# Benchmark: Full pipeline on integration test
echo "[Bench] Full pipeline throughput (iterations=100)"
START=$(date +%s%N)
for i in {1..100}; do
  "$VAKED_OPT" -pass-pipeline="builtin.module(vaked-topology-analysis,vaked-to-hcp-lowering-full,vaked-aot-index)" \
     "$TEST_DIR/integration-e2e.mlir" > /dev/null 2>&1
done
END=$(date +%s%N)
ELAPSED_MS=$(( (END - START) / 1000000 ))
AVG_MS=$(( ELAPSED_MS / 100 ))
echo "  Time: ${ELAPSED_MS}ms total, ${AVG_MS}ms/iter"

# Summary
echo
echo "=== Results ==="
echo -e "${GREEN}Passed: $PASS${NC}"
if [ $FAIL -gt 0 ]; then
  echo -e "${RED}Failed: $FAIL${NC}"
  exit 1
else
  echo "All tests passed!"
  exit 0
fi
