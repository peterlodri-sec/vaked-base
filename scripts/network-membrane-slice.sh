#!/usr/bin/env bash
# network-membrane-slice.sh — run the agent-guardd vertical slice end to end.
#
#   Vaked declares → vakedc lower → agent-guardd (load eBPF · enforce · testify)
#   → eventd hash chain → verify "the membrane held".
#
# Usage: scripts/network-membrane-slice.sh [example.vaked] [out-dir]
# Defaults: vaked/examples/membrane/agent-egress.vaked, a fresh temp dir.
set -euo pipefail

cd "$(dirname "$0")/.."

SRC="${1:-vaked/examples/membrane/agent-egress.vaked}"
OUT="${2:-$(mktemp -d -t vaked-slice-XXXXXX)}"
mkdir -p "$OUT"

echo "==> lowering $SRC"
python3 -m vakedc lower "$SRC" --out "$OUT"
POLICY="$OUT/gen/ebpf.policy.json"
test -f "$POLICY" || { echo "no gen/ebpf.policy.json — does the source declare a network membrane?"; exit 1; }

echo
echo "==> kernel BPF capability on this host"
python3 -m agent_guardd probe

echo
echo "==> agent-guardd: load eBPF · enforce · testify · verify · tamper-check"
exec python3 -m agent_guardd demo "$POLICY" --out "$OUT"
