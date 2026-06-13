#!/usr/bin/env bash
#
# web-search.sh — Search web for Vaked-related content and research
#
# Uses multiple search APIs:
#   - Brave Search (fast, privacy-focused web search)
#   - Tavily AI Search (semantic search optimized for research)
#   - OpenRouter fallback (for general web search via LLM APIs)
#
# Requires environment variables:
#   - BRAVE_SEARCH_API_KEY (optional, Brave Search)
#   - TAVILY_API_KEY (optional, Tavily)
#   - OPENROUTER_API_KEY (optional, OpenRouter fallback)
#
# Usage:
#   scripts/web-search.sh "query"                    # Default: Tavily
#   scripts/web-search.sh --brave "query"            # Use Brave Search
#   scripts/web-search.sh --tavily "query"           # Use Tavily (recommended)
#   scripts/web-search.sh --all "query"              # Run all and merge
#   scripts/web-search.sh --deep "query"             # Deep search (100 results)
#
# Output: JSON with url, summary, score, source
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
QUERY="${1:-}"
SEARCH_MODE="--tavily"
DEPTH="50"

# Colors
if [ -t 1 ]; then
  BOLD='\033[1m'
  BLUE='\033[34m'
  GREEN='\033[32m'
  YELLOW='\033[33m'
  RESET='\033[0m'
else
  BOLD='' BLUE='' GREEN='' YELLOW='' RESET=''
fi

usage() {
  cat >&2 <<'EOF'
web-search.sh — Search web for research and context

Usage:
  scripts/web-search.sh "query"              # Tavily (default, recommended)
  scripts/web-search.sh --brave "query"      # Brave Search
  scripts/web-search.sh --tavily "query"     # Explicit Tavily
  scripts/web-search.sh --all "query"        # All APIs (merged results)
  scripts/web-search.sh --deep "query"       # Deep search (100 results, slower)

Environment:
  BRAVE_SEARCH_API_KEY      Brave Search API key
  TAVILY_API_KEY            Tavily API key (recommended)
  OPENROUTER_API_KEY        OpenRouter fallback

Output: JSON lines with fields: url, summary, score, source

Examples:
  scripts/web-search.sh "capability-based security"
  scripts/web-search.sh --deep "agentic systems"
  scripts/web-search.sh --all "infrastructure as code"
EOF
  exit 1
}

# Parse arguments
if [ $# -eq 0 ]; then
  usage
elif [[ "$1" == --* ]]; then
  SEARCH_MODE="$1"
  QUERY="${2:-}"
  if [[ "$SEARCH_MODE" == "--deep" ]]; then
    DEPTH="100"
    SEARCH_MODE="--tavily"
    QUERY="${2:-}"
  elif [[ "$SEARCH_MODE" == "--all" ]]; then
    QUERY="${2:-}"
  fi
fi

if [ -z "$QUERY" ]; then
  usage
fi

echo -e "${BOLD}${BLUE}Web Search: '$QUERY'${RESET}" >&2
echo -e "${YELLOW}Mode: ${SEARCH_MODE#--} | Depth: $DEPTH${RESET}" >&2
echo ""

# Brave Search API wrapper
brave_search() {
  local q="$1"
  local count="${2:-50}"

  if [ -z "${BRAVE_SEARCH_API_KEY:-}" ]; then
    echo -e "${YELLOW}⚠ BRAVE_SEARCH_API_KEY not set${RESET}" >&2
    return 1
  fi

  # Brave Search API endpoint
  local response=$(curl -s -X GET "https://api.search.brave.com/res/v1/web/search" \
    -H "Accept: application/json" \
    -H "X-Subscription-Token: $BRAVE_SEARCH_API_KEY" \
    -G --data-urlencode "q=$q" \
    --data-urlencode "count=$count" \
    --data-urlencode "text_format=html" 2>/dev/null)

  if [ -z "$response" ]; then
    return 1
  fi

  # Parse results: url, title (as summary), and assign score based on rank
  echo "$response" | jq -r '.web[]? |
    {
      url: .url,
      summary: (.description // .title // "" | gsub("<[^>]*>"; "") | .[0:200]),
      score: (100 - ((input_line_number // 0) * 2) | if . < 0 then 0 else . end),
      source: "brave"
    } | @json' 2>/dev/null || true
}

# Tavily API wrapper (recommended for research)
tavily_search() {
  local q="$1"
  local depth="${2:-50}"

  if [ -z "${TAVILY_API_KEY:-}" ]; then
    echo -e "${YELLOW}⚠ TAVILY_API_KEY not set${RESET}" >&2
    return 1
  fi

  # Tavily AI Search API
  local response=$(curl -s -X POST "https://api.tavily.com/search" \
    -H "Content-Type: application/json" \
    -d @- 2>/dev/null <<EOF
{
  "api_key": "$TAVILY_API_KEY",
  "query": "$q",
  "include_answer": true,
  "search_depth": "$([ "$depth" -gt 50 ] && echo "advanced" || echo "basic")",
  "max_results": $depth,
  "topic": "research"
}
EOF
)

  if [ -z "$response" ]; then
    return 1
  fi

  # Parse results
  echo "$response" | jq -r '.results[]? |
    {
      url: .url,
      summary: (.content // .title // "" | .[0:200]),
      score: (.score // 75),
      source: "tavily"
    } | @json' 2>/dev/null || true
}

# OpenRouter semantic search fallback
openrouter_search() {
  local q="$1"

  if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo -e "${YELLOW}⚠ OPENROUTER_API_KEY not set (skipping)${RESET}" >&2
    return 1
  fi

  # OpenRouter doesn't have a web search API, so this is a placeholder
  # In practice, you'd integrate with a search engine via OpenRouter
  echo -e "${YELLOW}⚠ OpenRouter search not yet implemented${RESET}" >&2
  return 1
}

# Merge results from multiple sources
merge_results() {
  # Read JSON lines, deduplicate by URL, sort by score
  jq -s 'sort_by(-.score) | unique_by(.url) | .[]' 2>/dev/null || true
}

# Format and display results
format_results() {
  local count=0
  while IFS= read -r line; do
    if [ -n "$line" ]; then
      count=$((count + 1))
      url=$(echo "$line" | jq -r '.url // ""')
      summary=$(echo "$line" | jq -r '.summary // ""' | tr '\n' ' ')
      score=$(echo "$line" | jq -r '.score // 0')
      source=$(echo "$line" | jq -r '.source // "?"')

      # Truncate summary to 200 chars
      summary="${summary:0:200}"

      printf "%3d. [%s] [%d/100]\n" "$count" "$source" "$score"
      printf "     %s\n" "$url"
      printf "     → %s\n\n" "$summary"
    fi
  done
}

# Main search dispatcher
main() {
  local results=()

  case "$SEARCH_MODE" in
    --brave)
      brave_search "$QUERY" "$DEPTH" | while read -r line; do
        echo "$line"
      done
      ;;
    --tavily)
      tavily_search "$QUERY" "$DEPTH" | while read -r line; do
        echo "$line"
      done
      ;;
    --all)
      {
        brave_search "$QUERY" "$DEPTH" 2>/dev/null || true
        tavily_search "$QUERY" "$DEPTH" 2>/dev/null || true
      } | merge_results
      ;;
    *)
      echo "Unknown mode: $SEARCH_MODE" >&2
      usage
      ;;
  esac | format_results

  echo -e "${GREEN}✓ Search complete${RESET}" >&2
}

main
