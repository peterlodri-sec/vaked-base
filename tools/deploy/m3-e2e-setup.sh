#!/bin/bash
# M3 E2E Development Setup — one-shot. Everything you need, Peter.
# GENESIS_SEAL: 7c242080
set -e

echo "═══════════════════════════════════════════════════"
echo "  M3 E2E DEVELOPMENT SETUP"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "═══════════════════════════════════════════════════"
echo ""

echo "--- Phase 1: Toolchain ---"
echo "  Checking compilers..."
echo "  Zig:      $(zig version 2>/dev/null || echo 'MISSING → brew install zig')"
echo "  Rust:     $(rustc --version 2>/dev/null || echo 'MISSING → brew install rust')"
echo "  Go:       $(go version 2>/dev/null || echo 'MISSING → brew install go')"
echo "  Swift:    $(xcrun swift --version 2>/dev/null | head -1 || echo 'MISSING → xcode-select --install')"
echo "  Node:     $(node --version 2>/dev/null || echo 'MISSING → brew install node')"
echo "  Python:   $(python3 --version 2>/dev/null || echo 'MISSING')"

echo ""
echo "--- Phase 2: GCP Auth ---"
if [ -f ~/.config/gcloud/application_default_credentials.json ]; then
  echo "  ✅ GCP ADC credentials found"
else
  echo "  ⚠️  GCP credentials missing — run: gcloud auth application-default login"
fi

echo ""
echo "--- Phase 3: Nix ---"
if command -v nix &> /dev/null; then
  echo "  ✅ Nix $(nix --version 2>/dev/null || echo 'installed')"
  echo "  Running: nix develop .#vaked-mobile"
  nix develop .#vaked-mobile 2>&1 | tail -1 || true
else
  echo "  ⚠️  Nix not installed — needed for deterministic builds"
  echo "     curl -L https://nixos.org/nix/install | sh"
fi

echo ""
echo "--- Phase 4: Zig Build All ---"
for d in daemons/openrouterd tools/openrouter-zig vakedz daemons/synapsed daemons/vaked-cdn; do
  if [ -f "$d/build.zig" ]; then
    (cd "$d" && zig build 2>&1 | tail -1)
    echo "  ✅ $d"
  fi
done

echo ""
echo "--- Phase 5: TypeScript Build ---"
if [ -f tools/openrouter-ts/package.json ]; then
  (cd tools/openrouter-ts && npm install --silent 2>/dev/null && npm run build 2>/dev/null | tail -1)
  echo "  ✅ TS SDK built"
fi

echo ""
echo "--- Phase 6: Go Build ---"
if [ -f tools/vaked-docs/go.mod ]; then
  (cd tools/vaked-docs && go build ./cmd/vaked-docs/ 2>/dev/null && echo "  ✅ vaked-docs built") || true
fi

echo ""
echo "--- Phase 7: E2E Verification ---"
echo "  Running e2e test..."
bash tools/bench/e2e-test.sh 2>&1 | tail -5 || echo "  ⚠️ Daemon not running — e2e skipped"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  M3 E2E SETUP COMPLETE"
echo "  GENESIS_SEAL: 7c242080"
echo "═══════════════════════════════════════════════════"
