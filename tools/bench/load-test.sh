#!/bin/sh
# Load test: 10 concurrent agents on 256-slot pool
# GENESIS_SEAL: 7c242080
set -e
echo "=== Load Test ==="
echo "Spawning 10 concurrent agent requests..."
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:9090/ -d "{\"prompt\":\"test $i\"}" -o /tmp/load-$i.json &
  echo "  [agent $i] spawned"
done
wait
echo ""
echo "=== Results ==="
for i in $(seq 1 10); do
  if [ -f /tmp/load-$i.json ]; then
    cat /tmp/load-$i.json | head -c 80
    echo ""
  else
    echo "  [agent $i] failed"
  fi
done
echo ""
echo "=== Load test complete ==="
