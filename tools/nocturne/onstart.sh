#!/usr/bin/env bash
# nocturne box bootstrap — runs ON the rented GPU box once, before the driver.
# Installs uv, syncs the vendored harness deps (torch cu128 etc), prepares data ONCE.
# Idempotent: safe to re-run. Expects the harness dir to already be uploaded.
set -euo pipefail
HARNESS_DIR="${NOCTURNE_HARNESS_DIR:-/workspace/nocturne/harness}"
log() { echo "[onstart] $*" >&2; }

log "harness: $HARNESS_DIR"
cd "$HARNESS_DIR"

# C toolchain — torch.compile/inductor JIT-compiles CUDA kernels at runtime and needs a C
# compiler, which the pytorch/pytorch:*-runtime image does NOT ship. Without this, train.py
# dies with "InductorError: Failed to find C compiler" and never emits val_bpb.
if ! command -v cc >/dev/null 2>&1; then
  log "installing build-essential (C compiler for torch.compile)"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq && apt-get install -y -qq build-essential >/dev/null
fi
export CC="${CC:-cc}" CXX="${CXX:-c++}"

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
