#!/usr/bin/env bash
# Internal mTLS CA + per-node certs for NATS RAFT routes + leaf links.
# Tailnet client traffic (:4222) is WireGuard-encrypted, so no client TLS in v1.
# Usage: mtls-ca.sh [OUTDIR] nats-1=<ip1> nats-2=<ip2> nats-3=<ip3>
# Requires: step-cli (https://smallstep.com/cli). Idempotent.
set -euo pipefail

OUT=./nats-pki
case "${1:-}" in *=*) ;; "" ) ;; *) OUT="$1"; shift;; esac
mkdir -p "$OUT"; cd "$OUT"

if [ ! -f ca.crt ]; then
  step certificate create "vaked-nats CA" ca.crt ca.key \
    --profile root-ca --no-password --insecure --not-after 87600h
  echo "created CA"
fi

for spec in "$@"; do
  case "$spec" in
    *=*) name=${spec%%=*}; ip=${spec#*=} ;;
    *) echo "skip malformed spec: $spec" >&2; continue ;;
  esac
  if [ -f "$name.crt" ]; then echo "exists: $name"; continue; fi
  step certificate create "$name" "$name.crt" "$name.key" \
    --profile leaf --ca ca.crt --ca-key ca.key --no-password --insecure \
    --san "$ip" --san "$name.vaked.internal" --not-after 8760h
  echo "issued: $name ($ip)"
done
