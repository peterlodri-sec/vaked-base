#!/usr/bin/env bash
# vaked dev install - put `vakedc` on PATH, editable, for development.
#
# vakedc is a stdlib-only Python package that resolves its builtins catalog
# (vaked/schema/builtins.vaked) relative to the source tree, so we install it
# EDITABLE: the on-PATH `vakedc` runs straight from this checkout, and edits to
# the lexer/parser/checker take effect with no reinstall.
#
# Usage: bash install.sh            (from the vaked-base checkout)
# Re-running is a safe no-op/upgrade.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "vaked dev install (editable) from ${HERE}"

if command -v pipx >/dev/null 2>&1; then
  # --force makes re-runs idempotent (reinstall in place).
  pipx install --force --editable . >/dev/null 2>&1 \
    && echo "  installed via pipx (isolated venv)" \
    || { echo "  pipx failed; falling back to pip --user"; pip3 install --user --editable .; }
else
  echo "  pipx not found; using pip --user"
  pip3 install --user --editable .
fi

echo
if command -v vakedc >/dev/null 2>&1; then
  echo "  vakedc -> $(command -v vakedc)"
  if vakedc --help >/dev/null 2>&1; then
    echo "  vakedc --help OK"
  else
    echo "  WARN: 'vakedc --help' exited nonzero - check the install"
  fi
else
  echo "  WARN: vakedc not on PATH. Add the install bin dir, e.g.:"
  echo "    pipx:  ensure \"\$(pipx environment --value PIPX_BIN_DIR)\" is on PATH (run: pipx ensurepath)"
  echo "    pip:   add ~/.local/bin (or your Python user-base bin) to PATH"
fi

echo
echo "next:"
echo "  vakedc parse <file.vaked>            # -> Labeled Property Graph (.vaked/)"
echo "  vakedc check <file.vaked> [--json]   # 0011 type checker"
echo "  vakedc lower <file.vaked> --out DIR  # parse->check->lower -> flake.nix, gen/, provenance.json"
