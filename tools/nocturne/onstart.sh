#!/usr/bin/env bash
# nocturne box bootstrap — runs ON the rented GPU box once, before the driver.
# Installs uv, syncs the vendored harness deps (torch cu128 etc), prepares data ONCE.
# Idempotent: safe to re-run. Expects the harness dir to already be uploaded.
set -euo pipefail
HARNESS_DIR="${NOCTURNE_HARNESS_DIR:-/workspace/nocturne/harness}"
log() { echo "[onstart] $*" >&2; }

log "harness: $HARNESS_DIR"
cd "$HARNESS_DIR"

if ! command -v uv >/dev/null 2>&1; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

log "uv sync (torch 2.9.1 cu128 + harness deps)"
uv sync

# One-time data prep (downloads shards + trains the BPE tokenizer into ~/.cache/autoresearch).
if [[ ! -d "$HOME/.cache/autoresearch" ]] || [[ -z "$(ls -A "$HOME/.cache/autoresearch" 2>/dev/null)" ]]; then
  log "preparing data (uv run prepare.py) — one time"
  uv run prepare.py
else
  log "data cache present — skipping prepare.py"
fi
log "bootstrap complete"
