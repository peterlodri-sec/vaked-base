#!/usr/bin/env bash
#
# gather-context.sh — Non-LLM repo context gatherer
#
# Usage:
#   scripts/gather-context.sh "query"            # Search for files/symbols
#   scripts/gather-context.sh --file "*.vaked"   # Find files by glob
#   scripts/gather-context.sh --grep "pattern"   # Search code content
#   scripts/gather-context.sh --symbol "name"    # Symbol lookup via crabcc
#
# Output: Structured context block with matches and file previews
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEARCH_TYPE="--auto"
QUERY=""

usage() {
  cat >&2 <<'EOF'
Usage: gather-context.sh [--mode] "query"

Modes:
  --auto       Auto-detect: try symbol, then file, then grep (default)
  --file       Find files by glob pattern (e.g., "*.vaked")
  --grep       Search code for regex pattern
  --symbol     Lookup symbol via crabcc
  --function   Find function definitions (Go/Rust style)
  --type       Find type definitions (struct/class/interface)

Examples:
  gather-context.sh "operator-field"          # Auto search
  gather-context.sh --file "*.vaked"          # Find .vaked files
  gather-context.sh --grep "POLA"             # Search content
  gather-context.sh --symbol "vakedc"         # Symbol lookup
EOF
  exit 1
}

# Parse arguments
if [ $# -eq 0 ]; then
  usage
elif [ $# -eq 1 ]; then
  QUERY="$1"
elif [ $# -ge 2 ]; then
  SEARCH_TYPE="$1"
  QUERY="$2"
fi

if [ -z "$QUERY" ]; then
  usage
fi

# Color codes (disable if not TTY)
if [ -t 1 ]; then
  BOLD='\033[1m'
  DIM='\033[2m'
  GREEN='\033[32m'
  BLUE='\033[34m'
  YELLOW='\033[33m'
  RESET='\033[0m'
else
  BOLD='' DIM='' GREEN='' BLUE='' YELLOW='' RESET=''
fi

# Helper: print section header
section() {
  echo -e "${BOLD}${BLUE}## $1${RESET}"
}

# Helper: print match
match() {
  echo -e "${GREEN}✓${RESET} $1"
}

# Helper: print file preview
preview_file() {
  local file="$1"
  local lines="${2:-10}"

  if [ ! -f "$file" ]; then
    return
  fi

  echo -e "${DIM}→ $file (first $lines lines)${RESET}"
  head -n "$lines" "$file" | sed 's/^/  /'
  echo ""
}

# Search mode: auto-detect
auto_search() {
  local q="$1"

  # Try symbol lookup first (if crabcc is available)
  if command -v crabcc &>/dev/null && crabcc index ls &>/dev/null; then
    section "Symbol Lookup"
    if crabcc index query "$q" 2>/dev/null | head -5; then
      echo ""
      return 0
    fi
  fi

  # Try file glob
  section "Files Matching: $q"
  local file_count=0
  while IFS= read -r file; do
    if [ -n "$file" ]; then
      match "$file"
      ((file_count++))
    fi
  done < <(find "$REPO_ROOT" -type f -name "*$q*" 2>/dev/null | head -20)

  if [ "$file_count" -eq 0 ]; then
    echo "  (no files found)"
  fi
  echo ""

  # Try grep in code
  section "Code References: $q"
  local grep_count=0
  while IFS= read -r match_line; do
    if [ -n "$match_line" ]; then
      match "$match_line"
      ((grep_count++))
    fi
  done < <(grep -r "$q" "$REPO_ROOT" --include="*.vaked" --include="*.md" --include="*.py" \
    --include="*.ebnf" --include="*.json" 2>/dev/null | head -20)

  if [ "$grep_count" -eq 0 ]; then
    echo "  (no matches found)"
  fi
  echo ""
}

# Search mode: file glob
file_search() {
  local pattern="$1"

  section "Files: $pattern"

  local file_count=0
  while IFS= read -r file; do
    if [ -n "$file" ]; then
      match "$file"
      ((file_count++))
    fi
  done < <(find "$REPO_ROOT" -type f -path "*$pattern*" 2>/dev/null | head -30)

  if [ "$file_count" -eq 0 ]; then
    echo "  (no files found)"
  fi
  echo ""

  # Show previews of first 3 matches
  local shown=0
  while IFS= read -r file; do
    if [ -n "$file" ] && [ -f "$file" ] && [ "$shown" -lt 3 ]; then
      preview_file "$file" 15
      ((shown++))
    fi
  done < <(find "$REPO_ROOT" -type f -path "*$pattern*" 2>/dev/null | head -30)
}

# Search mode: grep
grep_search() {
  local pattern="$1"

  section "Code Search: $pattern"

  local match_count=0
  while IFS= read -r line; do
    if [ -n "$line" ]; then
      echo "$line"
      ((match_count++))
    fi
  done < <(grep -rn "$pattern" "$REPO_ROOT" \
    --include="*.vaked" --include="*.md" --include="*.py" \
    --include="*.ebnf" --include="*.json" --include="*.sh" \
    2>/dev/null | head -30)

  if [ "$match_count" -eq 0 ]; then
    echo "  (no matches found)"
  fi
  echo ""
}

# Search mode: symbol lookup
symbol_search() {
  local symbol="$1"

  if ! command -v crabcc &>/dev/null; then
    echo -e "${YELLOW}⚠${RESET} crabcc not found; falling back to grep" >&2
    grep_search "$symbol"
    return
  fi

  section "Symbol: $symbol"

  if crabcc index query "$symbol" 2>/dev/null; then
    echo ""
  else
    echo "  (symbol not found in index; try --grep)"
    echo ""
    grep_search "$symbol"
  fi
}

# Search mode: function definitions
function_search() {
  local name="$1"

  section "Function Definitions: $name"

  # Vaked/Python: def, Go: func, Rust: fn, JavaScript: function/const
  local match_count=0
  while IFS= read -r line; do
    if [ -n "$line" ]; then
      echo "$line"
      ((match_count++))
    fi
  done < <(grep -rn "^\(def\|fn\|func\|function\) $name" "$REPO_ROOT" \
    --include="*.vaked" --include="*.py" --include="*.go" --include="*.rs" --include="*.js" \
    2>/dev/null | head -20)

  if [ "$match_count" -eq 0 ]; then
    echo "  (no definitions found)"
  fi
  echo ""
}

# Search mode: type definitions
type_search() {
  local name="$1"

  section "Type Definitions: $name"

  # Vaked: schema, Go: type, Rust: struct/enum, Python: class, JSON: object
  local match_count=0
  while IFS= read -r line; do
    if [ -n "$line" ]; then
      echo "$line"
      ((match_count++))
    fi
  done < <(grep -rn "^\(schema\|type\|struct\|enum\|class\) $name" "$REPO_ROOT" \
    --include="*.vaked" --include="*.py" --include="*.go" --include="*.rs" --include="*.ts" \
    2>/dev/null | head -20)

  if [ "$match_count" -eq 0 ]; then
    echo "  (no definitions found)"
  fi
  echo ""
}

# Main dispatcher
main() {
  echo -e "${BOLD}Context Gather: '$QUERY'${RESET}"
  echo ""

  case "$SEARCH_TYPE" in
    --auto)
      auto_search "$QUERY"
      ;;
    --file)
      file_search "$QUERY"
      ;;
    --grep)
      grep_search "$QUERY"
      ;;
    --symbol)
      symbol_search "$QUERY"
      ;;
    --function)
      function_search "$QUERY"
      ;;
    --type)
      type_search "$QUERY"
      ;;
    *)
      echo "Unknown mode: $SEARCH_TYPE" >&2
      usage
      ;;
  esac
}

main
