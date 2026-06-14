#!/usr/bin/env bash
# Scheduled JetStream backups -> fleet object store (rustfs/minio). Wire via a
# systemd timer on one node. Requires: nats CLI + creds; mc (minio client) or rclone.
set -euo pipefail
S=${NATS_URL:-nats://nats-1.vaked.internal:4222}
CREDS=${CREDS:-creds/SWE_AF-orchestrator.creds}
DEST=${DEST:-/var/lib/nats/backups}
BUCKET=${BUCKET:-nats-backups}   # mc alias/bucket, e.g. minio/nats-backups
mkdir -p "$DEST"

for stream in SWE_AF_TASKS EVENTS; do
  out="$DEST/$stream"
  rm -rf "$out"
  nats --server "$S" --creds "$CREDS" stream backup "$stream" "$out"
done

# push to object store if mc is configured (best-effort)
if command -v mc >/dev/null 2>&1; then
  mc mirror --overwrite "$DEST" "$BUCKET/" || echo "mc mirror failed (check alias)" >&2
fi
echo "backup complete -> $DEST"
