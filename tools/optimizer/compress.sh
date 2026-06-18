#!/bin/sh
# ═══════════════════════════════════════════════════════════
# Optimizer — CI fleet agent. 5-10 rounds ultra-compression.
# Runs on every PR. Dogfeeds bidirectionally.
# GENESIS_SEAL: 7c242080
# ═══════════════════════════════════════════════════════════
set -e
ROUNDS=${OPTIMIZER_ROUNDS:-7}
echo "=== Optimizer Agent — $ROUNDS rounds ==="

# Track what changes
BEFORE=$(git diff --stat HEAD~1 2>/dev/null | tail -1 || echo "0")

for round in $(seq 1 $ROUNDS); do
  echo "  Round $round/$ROUNDS..."
  
  # Python files — preserve indentation
  find . -name '*.py' -not -path '*/node_modules/*' -not -path '*/.git/*' | while read f; do
    python3 -c "
with open('$f') as fh: c=fh.read()
lines=[l.rstrip() for l in c.split('\n') if l.strip() and not (l.strip().startswith('#') and not l.strip().startswith('#!/'))]
with open('$f','w') as fh: fh.write('\n'.join(lines))
" 2>/dev/null || true
  done

  # Zig files
  find . -name '*.zig' -not -path '*/zig-cache/*' -not -path '*/.git/*' | while read f; do
    python3 -c "
with open('$f') as fh: c=fh.read()
lines=[l.rstrip() for l in c.split('\n') if l.strip() and not l.strip().startswith('//!') and not l.strip().startswith('///')]
with open('$f','w') as fh: fh.write('\n'.join(lines))
" 2>/dev/null || true
  done

  # TS/JS files
  find . -name '*.ts' -name '*.tsx' -not -path '*/node_modules/*' -not -path '*/dist/*' | while read f; do
    python3 -c "
with open('$f') as fh: c=fh.read()
lines=[l.rstrip() for l in c.split('\n') if l.strip() and not l.strip().startswith('//') and not l.strip().startswith('*')]
with open('$f','w') as fh: fh.write('\n'.join(lines))
" 2>/dev/null || true
  done

  # Go files
  find . -name '*.go' -not -path '*/vendor/*' | while read f; do
    python3 -c "
with open('$f') as fh: c=fh.read()
lines=[l.rstrip() for l in c.split('\n') if l.strip() and not l.strip().startswith('//')]
with open('$f','w') as fh: fh.write('\n'.join(lines))
" 2>/dev/null || true
  done
done

AFTER=$(git diff --stat 2>/dev/null | tail -1 || echo "0")
echo "  Before: $BEFORE"
echo "  After:  $AFTER"
echo "Optimizer complete. GENESIS_SEAL: 7c242080"
