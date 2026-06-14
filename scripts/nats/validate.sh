#!/usr/bin/env bash
# Spike validation drills. Run against the live cluster. Records the numbers that
# justify (or reject) the topology. See docs/superpowers/specs/2026-06-14-nats-ha-cluster-design.md.
# Usage: NATS_URL=... CREDS=... validate.sh nats-1.vaked.internal nats-2... nats-3...
set -euo pipefail
S=${NATS_URL:?set NATS_URL}
CREDS=${CREDS:?set CREDS (an SWE_AF or EVENTS creds file)}

echo "== inter-node RTT (target < 2ms; RAFT degrades past ~10ms) =="
for h in "$@"; do ping -c5 "$h" 2>/dev/null | tail -1 || echo "ping $h failed"; done

echo "== throughput / latency (JetStream R3 publish) =="
nats --server "$S" --creds "$CREDS" bench bench.test \
  --js --replicas 3 --pub 4 --sub 4 --msgs 100000 --size 256

echo "== cluster health =="
nats --server "$S" --creds "$CREDS" server list
nats --server "$S" --creds "$CREDS" server report jetstream

echo "== auth isolation: SWE_AF creds must NOT read crabcc.> (EVENTS) =="
if nats --server "$S" --creds creds/SWE_AF-orchestrator.creds sub 'crabcc.>' \
     --count 1 --timeout 3s >/dev/null 2>&1; then
  echo "FAIL: isolation breach — SWE_AF read EVENTS subject"; exit 1
else
  echo "ok: account isolation holds"
fi

echo "== failover drill (manual/[OPERATOR]) =="
echo "  stop one node (systemctl stop nats), confirm 'stream report' stays writable"
echo "  (quorum 2/3), then restart and confirm catch-up. Record recovery time."
