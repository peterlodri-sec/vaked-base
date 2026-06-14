#!/usr/bin/env bash
# [OPERATOR] Provision 3x Hetzner CCX13 in one location for the NATS cluster.
# Requires: hcloud CLI + HCLOUD_TOKEN. Cost ~EUR39/mo (see docs/economy.md).
set -euo pipefail
: "${HCLOUD_TOKEN:?set HCLOUD_TOKEN}"

LOC=${LOC:-fsn1}
TYPE=${TYPE:-ccx13}
IMAGE=${IMAGE:-debian-12}
KEY=${SSH_KEY:-$(hcloud ssh-key list -o noheader -o columns=name | head -1)}
: "${KEY:?no ssh-key in hcloud; add one first}"

for n in nats-1 nats-2 nats-3; do
  if hcloud server describe "$n" >/dev/null 2>&1; then
    echo "exists: $n"; continue
  fi
  hcloud server create --name "$n" --type "$TYPE" --image "$IMAGE" \
    --location "$LOC" --ssh-key "$KEY" --label role=nats
done

echo "=== record these IPs into nix/nats/hosts/*.nix ==="
hcloud server list -l role=nats -o columns=name,ipv4,ipv6,datacenter
