#!/bin/bash
# deploy.sh — Deploy the Vaked Genesis Archive to vaked.dev
# Run from repo root: bash deploy/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy/vaked.dev"
GENESIS_DIR="$DEPLOY_DIR/genesis"
RESEARCH_DIR="$DEPLOY_DIR/research"

echo "═══ Vaked Genesis Deployment ═══"
echo ""

# ── Step 0: Verify seal integrity ──
echo "→ Verifying genesis seal integrity..."
SEAL_LOCAL=$(cat "$REPO_ROOT/genesis_block_00.md" \
                  "$REPO_ROOT/GRAVEYARD.md" \
                  "$REPO_ROOT/genesis_reflection.md" \
                  "$REPO_ROOT/genesis_snapshot.md" \
                  "$REPO_ROOT/HONEST_BEGINNINGS.md" \
             | shasum -a 256 | cut -d' ' -f1)

SEAL_DNS=$(dig TXT vaked.dev +short 2>/dev/null | grep 'vaked-genesis-seal=' | cut -d'=' -f2 || echo "")

echo "  Local seal:  $SEAL_LOCAL"
echo "  DNS seal:    ${SEAL_DNS:-<not yet propagated>}"

if [ -n "$SEAL_DNS" ] && [ "$SEAL_LOCAL" != "$SEAL_DNS" ]; then
    echo ""
    echo "  ⚠️  WARNING: Local seal does not match DNS!"
    echo "  The DNS TXT record at vaked.dev may need updating."
    echo "  Expected: vaked-genesis-seal=$SEAL_LOCAL"
    echo ""
    read -p "  Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ── Step 1: Sync genesis files ──
echo ""
echo "→ Syncing genesis files to deploy directory..."
mkdir -p "$GENESIS_DIR" "$RESEARCH_DIR"
cp "$REPO_ROOT/genesis_block_00.md" "$GENESIS_DIR/"
cp "$REPO_ROOT/GRAVEYARD.md" "$GENESIS_DIR/"
cp "$REPO_ROOT/genesis_reflection.md" "$GENESIS_DIR/"
cp "$REPO_ROOT/genesis_snapshot.md" "$GENESIS_DIR/"
cp "$REPO_ROOT/HONEST_BEGINNINGS.md" "$GENESIS_DIR/"
echo "  Genesis files synced."

# ── Step 2: Sync research docs ──
echo ""
echo "→ Syncing research docs to deploy directory..."
cp "$REPO_ROOT/docs/research/RESEARCH_SUMMARY.md" "$RESEARCH_DIR/"
cp "$REPO_ROOT/docs/research/MASTER_RESEARCH_INDEX.md" "$RESEARCH_DIR/"
cp "$REPO_ROOT/docs/research/CROSS_REFERENCE_MAP.md" "$RESEARCH_DIR/"
cp "$REPO_ROOT/docs/research/genesis_summary.html" "$RESEARCH_DIR/"
echo "  Research docs synced."

# ── Step 3: Verify deployed hashes match originals ──
echo ""
echo "→ Verifying deployed file integrity..."
ORIG_HASHES=$(cat "$REPO_ROOT/genesis_block_00.md" \
                  "$REPO_ROOT/GRAVEYARD.md" \
                  "$REPO_ROOT/genesis_reflection.md" \
                  "$REPO_ROOT/genesis_snapshot.md" \
                  "$REPO_ROOT/HONEST_BEGINNINGS.md" \
              | shasum -a 256 | cut -d' ' -f1)
DEPLOY_HASHES=$(cat "$GENESIS_DIR/genesis_block_00.md" \
                    "$GENESIS_DIR/GRAVEYARD.md" \
                    "$GENESIS_DIR/genesis_reflection.md" \
                    "$GENESIS_DIR/genesis_snapshot.md" \
                    "$GENESIS_DIR/HONEST_BEGINNINGS.md" \
                | shasum -a 256 | cut -d' ' -f1)
if [ "$ORIG_HASHES" = "$DEPLOY_HASHES" ]; then
    echo "  ✅ Deployed files match originals."
else
    echo "  ❌ MISMATCH! Deployed files differ from originals. Aborting."
    exit 1
fi

# ── Step 4: Deployment options ──
echo ""
echo "═══ Ready for deployment ═══"
echo ""
echo "  Deploy directory: $DEPLOY_DIR"
echo "  Domain: vaked.dev"
echo ""
echo "  Choose deployment method:"
echo ""
echo "  A) Cloudflare Pages (recommended):"
echo "     cd $DEPLOY_DIR"
echo "     npx wrangler pages deploy . --project-name=vaked-dev --branch=main"
echo ""
echo "  B) Git push to public repo:"
echo "     cd $DEPLOY_DIR"
echo "     git init && git add -A && git commit -m 'Genesis Archive — vaked.dev'"
echo "     git remote add origin git@github.com:peterlodri-sec/vaked-genesis.git"
echo "     git push -u origin main"
echo "     # Then connect repo to Cloudflare Pages in dashboard"
echo ""
echo "  C) Any static host (Netlify, Vercel, S3, nginx):"
echo "     Upload contents of $DEPLOY_DIR to your host"
echo ""
echo "  ⚠️  REMINDER: Update DNS TXT record at vaked.dev:"
echo "     vaked-genesis-seal=$SEAL_LOCAL"
echo ""

echo "Deployment preparation complete."
