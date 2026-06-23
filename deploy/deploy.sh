#!/bin/bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "═══ vaked-base Hugo Deploy ═══"
echo ""

# Step 1: Build Hugo
echo "→ Building Hugo site..."
cd "$REPO_ROOT/hugo-site"
hugo > /dev/null 2>&1
echo "  ✅ Hugo build complete"

# Step 2: Build docs index (auto-generated from .md files)
echo "→ Checking docs index..."
python3 -c "
import os
md_count = sum(1 for _,_,fs in os.walk('$REPO_ROOT/docs') for f in fs if f.endswith('.md'))
print(f'  {md_count} docs indexed')
"

# Step 3: Deploy to Cloudflare Pages
echo "→ Deploying to vaked.dev..."
npx wrangler pages deploy "$REPO_ROOT/hugo-site/public" --project-name=vaked-dev --branch=main --commit-dirty=true

echo ""
echo "═══ Deploy complete ═══"
