#!/usr/bin/env bash
# LoRA fine-tune the abliterated model on wenyan-ultra pairs using mlx-tune.
# Recovers benchmark accuracy while keeping cuc compression as native style.
#
# mlx-tune = ARahim3/mlx-tune (Unsloth-compatible API, native Apple MLX)
# M3 Pro 46GB: 8B LoRA r=16 ≈ 8h at ~15 tok/s. QLoRA r=8 ≈ 4h.
#
# Install:
#   pip install mlx-lm  # Apple's official MLX fine-tuning
#   # OR: pip install mlx-tune  # ARahim3/mlx-tune (unsloth-compatible API)
#
# Usage:
#   python3 tools/abliterate/wenyan-pairs.py   # generate dataset first
#   bash tools/abliterate/finetune-mlx.sh [llama|qwen]

set -euo pipefail

MODEL_KEY="${1:-llama}"

case "$MODEL_KEY" in
  llama) ABLITERATED="tools/abliterate/output/meta-llama-Llama-3.1-8B-Instruct" ;;
  qwen)  ABLITERATED="tools/abliterate/output/Qwen-Qwen2.5-7B-Instruct" ;;
  *)     echo "Usage: $0 [llama|qwen]" >&2; exit 1 ;;
esac

DATASET="tools/abliterate/wenyan-pairs.jsonl"
OUTPUT_DIR="tools/abliterate/output/${MODEL_KEY}-cuc-lora"

if [[ ! -d "$ABLITERATED" ]]; then
  echo "ERROR: Abliterated model not found at $ABLITERATED"
  echo "       Run: bash tools/abliterate/run-heretic.sh $MODEL_KEY"
  exit 1
fi

if [[ ! -f "$DATASET" ]]; then
  echo "ERROR: Dataset not found at $DATASET"
  echo "       Run: python3 tools/abliterate/wenyan-pairs.py"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "Model:   $ABLITERATED"
echo "Dataset: $DATASET ($(wc -l < "$DATASET") pairs)"
echo "Output:  $OUTPUT_DIR"
echo ""

# mlx-lm LoRA fine-tuning
# --lora-rank 16: enough expressiveness for style transfer
# --iters 500: ~15-20min on M3 Pro; increase to 1000 for higher quality
python3 -m mlx_lm.lora \
  --model "$ABLITERATED" \
  --train \
  --data "$DATASET" \
  --adapter-path "$OUTPUT_DIR/adapters" \
  --lora-rank 16 \
  --iters 500 \
  --batch-size 4 \
  --learning-rate 2e-4 \
  --grad-checkpoint

echo ""
echo "==> LoRA adapters: $OUTPUT_DIR/adapters"
echo "    Fuse + convert for Ollama:"
echo "    python3 -m mlx_lm.fuse --model $ABLITERATED --adapter-path $OUTPUT_DIR/adapters --save-path $OUTPUT_DIR/fused"
echo "    bash tools/abliterate/load-ollama.sh $MODEL_KEY"
