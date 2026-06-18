#!/bin/sh
# Blogger — CI fleet agent for vaked.dev
# Triggered on push to main when blog/ changes
# GENESIS_SEAL: 7c242080
set -e
echo "=== Blogger Agent ==="
CHANGED=$(git diff --name-only HEAD~1 -- blog/posts/ 2>/dev/null || echo "")
if [ -z "$CHANGED" ]; then echo "No blog changes."; exit 0; fi
echo "Changed: $CHANGED"
for post in blog/posts/*.md; do
  [ -f "$post" ] || continue
  TITLE=$(head -1 "$post" | sed 's/^# //' | sed 's/\*\*//g')
  echo "  $TITLE"
done
echo "Blogger complete. GENESIS_SEAL: 7c242080"
