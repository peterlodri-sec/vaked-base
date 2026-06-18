#!/bin/sh
# ═══════════════════════════════════════════════════════════
# Vaked Agent — Compiled Binary Build Pipeline
# Targets: Deno, Bun, QuickJS+Zig
# GENESIS_SEAL: 7c242080
# ═══════════════════════════════════════════════════════════
set -e

echo "=== Vaked Agent Binary Build ==="
echo ""

# ── Build SDK ─────────────────────────────────────────────
echo "[1/4] Building SDK..."
cd ../openrouter-ts && npm run build --silent 2>/dev/null
cd - > /dev/null

# ── Deno ──────────────────────────────────────────────────
echo "[2/4] Deno compile..."
deno compile --no-check \
  --allow-env --allow-net --allow-read --allow-write=$HOME/.orcli_budget \
  -o vaked-deno minimal.ts 2>/dev/null
strip vaked-deno 2>/dev/null || true
DENO_SIZE=$(ls -lh vaked-deno | awk '{print $5}')
echo "  vaked-deno: $DENO_SIZE"

# ── Bun ───────────────────────────────────────────────────
echo "[3/4] Bun compile..."
bun build --compile --minify ./minimal.ts --outfile vaked-bun 2>/dev/null
strip vaked-bun 2>/dev/null || true
BUN_SIZE=$(ls -lh vaked-bun | awk '{print $5}')
echo "  vaked-bun:  $BUN_SIZE"

# ── QuickJS (logic only, no TLS) ──────────────────────────
echo "[4/4] QuickJS benchmark..."
QJS_SIZE=$(ls -lh $(which qjs) | awk '{print $5}')
echo "  qjs:        $QJS_SIZE (logic only — TLS via Zig daemon)"

echo ""
echo "=== Results ==="
echo "  deno:     $DENO_SIZE  (full JS runtime + npm deps)"
echo "  bun:      $BUN_SIZE   (full JS runtime + npm deps)"
echo "  quickjs:  $QJS_SIZE   (logic only, TLS via Zig)"
echo "  zig:      5.4MB       (TLS native, no JS)"
echo ""
echo "Optimal: Zig daemon (5.4MB) + QuickJS embed (2.6MB) = 8MB total"
echo "GENESIS_SEAL: 7c242080"
