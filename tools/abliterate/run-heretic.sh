#!/usr/bin/env bash
# Abliterate the verbosity/scaffold direction from a model using Heretic.
# Targets: meta-llama/Llama-3.1-8B-Instruct, Qwen/Qwen2.5-7B-Instruct
#
# What this does:
#   1. Computes difference-of-means between verbose and compressed activations
#   2. Finds optimal "verbosity direction" via direction_index search
#   3. Orthogonalizes all transformer weights against that direction
#   4. Saves modified weights to ./output/<model-slug>/
#
# Hardware: M3 Pro 46GB — runs fully on-device via MPS (PyTorch Metal backend).
# No CUDA needed. 8B model at float16 ≈ 16GB unified memory.
#
# Install:
#   pip install -U heretic-llm
#   pip install torch  # Apple builds: https://pytorch.org (MPS included since 2.0)
#
# Usage:
#   bash tools/abliterate/run-heretic.sh [llama|qwen] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_KEY="${1:-llama}"
DRY_RUN="${2:-}"

case "$MODEL_KEY" in
  llama) MODEL_ID="meta-llama/Llama-3.1-8B-Instruct" ;;
  qwen)  MODEL_ID="Qwen/Qwen2.5-7B-Instruct" ;;
  *)     echo "Usage: $0 [llama|qwen]" >&2; exit 1 ;;
esac

OUTPUT_DIR="tools/abliterate/output/$(echo "$MODEL_ID" | tr '/' '-')"
mkdir -p "$OUTPUT_DIR"

echo "Model:  $MODEL_ID"
echo "Config: $SCRIPT_DIR/config.noslop.toml  (verbosity direction, not refusal)"
echo "Output: $OUTPUT_DIR"
echo ""

if [[ -n "$DRY_RUN" ]]; then
  echo "[dry-run] Would run: heretic $MODEL_ID --config $SCRIPT_DIR/config.noslop.toml --save-dir $OUTPUT_DIR"
  exit 0
fi

# Run heretic with noslop config — targets verbose/scaffolded output direction.
# --device mps  = Apple Metal (M-series GPU)
# --save-dir    = write modified safetensors here (no interactive prompt)
heretic "$MODEL_ID" \
  --config "$SCRIPT_DIR/config.noslop.toml" \
  --device mps \
  --save-dir "$OUTPUT_DIR" \
  --plot-residuals

echo ""
echo "==> Abliterated weights: $OUTPUT_DIR"
echo "    Next: bash tools/abliterate/finetune-mlx.sh $MODEL_KEY"
