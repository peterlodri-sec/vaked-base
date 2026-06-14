#!/usr/bin/env bash
# Create the fleet streams (R3) on the cluster. Run after the cluster is up.
# Requires: nats CLI + the per-account creds from nsc-bootstrap.sh.
set -euo pipefail
S=${NATS_URL:-nats://nats-1.vaked.internal:4222}

# swe_af work-queue: exactly-once delivery to one worker, 24h TTL, 2m dedupe.
nats --server "$S" --creds creds/SWE_AF-orchestrator.creds stream add SWE_AF_TASKS \
  --subjects 'swe.af.tasks' --retention work --replicas 3 \
  --max-age 24h --dupe-window 2m --storage file --defaults

# crabcc event spine the console renders: limits retention, 7d / 5GB caps.
nats --server "$S" --creds creds/EVENTS-console.creds stream add EVENTS \
  --subjects 'crabcc.>' --retention limits --replicas 3 \
  --max-age 168h --max-bytes 5GB --storage file --defaults

echo "=== streams ==="
nats --server "$S" --creds creds/SWE_AF-orchestrator.creds stream report
