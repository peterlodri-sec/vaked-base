#!/usr/bin/env bash
# Decentralized JWT bootstrap (nsc): operator + SYS + per-domain accounts with
# JetStream tiers + scoped users -> creds, plus the NATS-resolver server fragment.
# Requires: nsc (https://github.com/nats-io/nsc). Re-runnable (|| true on adds).
# OPEN ITEM: verify the `nsc add export/import` flags for the cross-account
#   swe.af.status.> share against your nsc version; see docs/runbooks/nats-ha.md.
set -euo pipefail

export NSC_HOME=${NSC_HOME:-./nsc}
mkdir -p creds

nsc add operator --name vaked --sys 2>/dev/null || true
nsc edit operator --service-url nats://nats-1.vaked.internal:4222

add_acct() { # name mem disk streams consumers
  nsc add account --name "$1" 2>/dev/null || true
  nsc edit account --name "$1" \
    --js-mem-storage "$2" --js-disk-storage "$3" \
    --js-streams "$4" --js-consumers "$5"
}
add_acct EVENTS    256M 5G  50  200
add_acct SWE_AF    256M 5G  20  100
add_acct TELEMETRY 256M 10G 50  500
add_acct AGENTS    128M 2G  20  100

add_user() { # account user
  nsc add user --account "$1" --name "$2" 2>/dev/null || true
  nsc generate creds --account "$1" --name "$2" > "creds/$1-$2.creds"
  echo "creds/$1-$2.creds"
}
add_user SWE_AF    orchestrator
add_user SWE_AF    enqueue
add_user EVENTS    console
add_user TELEMETRY exporter
add_user AGENTS    worker

# NATS-based account resolver fragment, included by the server config.
nsc generate config --nats-resolver --sys-account SYS > nats-resolver.conf
echo "wrote nats-resolver.conf"
