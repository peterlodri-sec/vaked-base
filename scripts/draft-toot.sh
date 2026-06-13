#!/usr/bin/env bash
# Draft a Carcin-voice toot with google/gemma-4-31b-it (OpenRouter) and write it to
# .github/social/toot.txt for review. Posting is done by .github/workflows/social-post.yml
# once you commit + push that file. See .claude/skills/mastodon-poster/SKILL.md.
#
# Usage: scripts/draft-toot.sh "<topic, fix summary, or anecdote>"
# Env:   OPENROUTER_API_KEY (required), TOOT_MODEL (default google/gemma-4-31b-it),
#        OPENROUTER_BASE_URL (default https://openrouter.ai/api/v1)
set -euo pipefail

topic="${*:-}"
[ -n "$topic" ] || { echo "usage: $0 \"<topic/summary>\"" >&2; exit 2; }
: "${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"
MODEL="${TOOT_MODEL:-google/gemma-4-31b-it}"
BASE="${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}"
OUT=".github/social/toot.txt"

SYS='You are Carcin, the dev feed for social.crabcc.app: terse, dry, technically
credible. Ship receipts, not hype. Rules: <=500 characters; ONE idea; keep code,
identifiers, API names, CLI flags and error strings EXACT; no secrets or internal
model IDs; no marketing adjectives; at most one emoji and at most one understated crab
pun, only if they do not cost clarity; never invent facts. Output ONLY the toot text —
no quotes, no preamble, no hashtags unless essential.'

payload=$(jq -n --arg m "$MODEL" --arg s "$SYS" --arg u "$topic" \
  '{model:$m, messages:[{role:"system",content:$s},{role:"user",content:$u}],
    max_tokens:300, temperature:0.6}')

resp=$(curl -sS "$BASE/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H 'content-type: application/json' \
  -d "$payload")

toot=$(printf '%s' "$resp" | jq -r '.choices[0].message.content // empty')
[ -n "$toot" ] || { echo "draft failed: $(printf '%s' "$resp" | head -c 400)" >&2; exit 1; }

mkdir -p "$(dirname "$OUT")"
printf '%s\n' "$toot" > "$OUT"

chars=$(printf '%s' "$toot" | wc -m | tr -d ' ')
echo "wrote $OUT ($chars chars):"
echo "----"
cat "$OUT"
echo "----"
[ "$chars" -le 500 ] || echo "WARNING: over 500 chars — trim before posting." >&2
echo "Review, then: git add $OUT && git commit && git push  (social-post.yml posts it)"
