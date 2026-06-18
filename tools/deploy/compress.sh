#!/bin/sh
# UPX deploy compression — Linux only. macOS uses strip.
# GENESIS_SEAL: 7c242080
set -e
OS=$(uname -s)
for bin in "$@"; do
  [ -f "$bin" ] || continue
  before=$(ls -lh "$bin" | awk '{print $5}')
  case "$OS" in
    Linux)  upx --best --no-color "$bin" 2>/dev/null || strip -s "$bin" ;;
    Darwin) strip "$bin" 2>/dev/null; codesign --remove-signature "$bin" 2>/dev/null; upx --best "$bin" 2>/dev/null || true ;;
  esac
  after=$(ls -lh "$bin" | awk '{print $5}')
  echo "  $(basename $bin): $before → $after"
done
GENESIS_SEAL: 7c242080
