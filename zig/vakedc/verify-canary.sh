#!/usr/bin/env bash
# Phase-0 differential harness (seed): build the Zig sha256 canary and prove it
# reproduces Python's provenance-hash format (`sha256-<hex>`) byte-for-byte.
# This is the pattern every port phase reuses: same input → both impls → diff.
set -euo pipefail
cd "$(dirname "$0")"

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
bin="$dir/vakedc-canary"   # fresh path so the build output keeps its +x bit
zig build-exe src/main.zig -femit-bin="$bin"

ok=1
for s in "hello vaked" "" "operator-field" "sha256-{}" "café ünïcode"; do
  z=$(printf '%s' "$s" | "$bin" 2>&1)
  p=$(python3 -c "import hashlib,sys;print('sha256-'+hashlib.sha256(sys.argv[1].encode()).hexdigest())" "$s")
  if [ "$z" = "$p" ]; then echo "MATCH  \"$s\""; else echo "DIFF   \"$s\": zig=$z py=$p"; ok=0; fi
done
[ "$ok" = 1 ] && echo "OK — sha256 provenance-hash parity (Zig std.crypto == Python hashlib)"
exit $((1 - ok))
