#!/usr/bin/env bash
# Images as code: render every diagram source (docs/assets/diagrams/src/*.d2)
# to a committed SVG next to the existing RFC figures (docs/assets/diagrams/*.svg).
#
# The .d2 files are the source of truth; the .svg files are generated artifacts.
# d2 is provided by the dev shell (`nix develop`); `task diagrams` runs this.
#
#   render.sh            render all sources -> docs/assets/diagrams/*.svg
#   render.sh --check    render to a temp dir and fail if any committed SVG drifts
#
# Determinism: d2 layout + theme are fixed below so the same source + same d2
# version yields byte-identical SVGs (so --check is meaningful in CI).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
src_dir="$repo_root/docs/assets/diagrams/src"
out_dir="$repo_root/docs/assets/diagrams"

# Pin layout + theme for reproducible output.
export D2_LAYOUT="${D2_LAYOUT:-dagre}"
export D2_THEME="${D2_THEME:-0}"
export D2_PAD="${D2_PAD:-20}"

if ! command -v d2 >/dev/null 2>&1; then
  echo "render.sh: d2 not found. Run inside the dev shell (\`nix develop\`) or \`nix run nixpkgs#d2\`." >&2
  exit 127
fi

shopt -s nullglob
sources=("$src_dir"/*.d2)
if [ ${#sources[@]} -eq 0 ]; then
  echo "render.sh: no .d2 sources in $src_dir" >&2
  exit 0
fi

mode="render"
[ "${1:-}" = "--check" ] && mode="check"

check_dir=""
if [ "$mode" = "check" ]; then
  check_dir="$(mktemp -d)"
  trap 'rm -rf "$check_dir"' EXIT
fi

drift=0
for src in "${sources[@]}"; do
  name="$(basename "${src%.d2}")"
  if [ "$mode" = "check" ]; then
    d2 --layout "$D2_LAYOUT" --theme "$D2_THEME" --pad "$D2_PAD" "$src" "$check_dir/$name.svg" >/dev/null
    if ! diff -q "$out_dir/$name.svg" "$check_dir/$name.svg" >/dev/null 2>&1; then
      echo "DRIFT: $name.svg is out of date — run \`task diagrams\`" >&2
      drift=1
    fi
  else
    d2 --layout "$D2_LAYOUT" --theme "$D2_THEME" --pad "$D2_PAD" "$src" "$out_dir/$name.svg" >/dev/null
    echo "rendered $name.svg"
  fi
done

if [ "$mode" = "check" ] && [ "$drift" -ne 0 ]; then
  exit 1
fi
