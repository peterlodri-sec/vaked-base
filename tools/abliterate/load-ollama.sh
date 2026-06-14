#!/usr/bin/env bash
# Convert fused model to GGUF and load into Ollama.
# Requires: llama.cpp (brew install llama.cpp)
#
# Usage: bash tools/abliterate/load-ollama.sh [llama|qwen]

set -euo pipefail

MODEL_KEY="${1:-llama}"

case "$MODEL_KEY" in
  llama)
    FUSED="tools/abliterate/output/llama-cuc-lora/fused"
    OLLAMA_NAME="cuc-llama-8b"
    ;;
  qwen)
    FUSED="tools/abliterate/output/qwen-cuc-lora/fused"
    OLLAMA_NAME="cuc-qwen-7b"
    ;;
  *)
    echo "Usage: $0 [llama|qwen]" >&2; exit 1 ;;
esac

GGUF_PATH="${FUSED}.gguf"

echo "==> Converting to GGUF (Q4_K_M)"
python3 "$(brew --prefix llama.cpp)/bin/convert_hf_to_gguf.py" \
  "$FUSED" --outtype q4_k_m --outfile "$GGUF_PATH"

echo "==> Creating Ollama model: $OLLAMA_NAME"
cat > /tmp/cuc-Modelfile <<EOF
FROM $GGUF_PATH

SYSTEM """
You are a terse, dense assistant. Respond in wenyan-ultra compressed style:
classical Chinese ultra-compression (文言超縮), omit subjects when clear,
use classical particles (之/乃/為/其/則/故), arrows for causality (X→Y).
Technical terms, code, API names: never translate. No filler, no hedging.
ARTIFACT GATE: when producing file content, commit messages, or PR text — use standard English only.
"""

PARAMETER temperature 0.7
PARAMETER num_predict 1024
EOF

ollama create "$OLLAMA_NAME" -f /tmp/cuc-Modelfile
rm /tmp/cuc-Modelfile

echo ""
echo "==> Model loaded: $OLLAMA_NAME"
echo "    Test: ollama run $OLLAMA_NAME 'Why does connection pooling help?'"
echo "    Bench: OLLAMA_HOST=http://localhost:11434 BENCH_MODEL=$OLLAMA_NAME python3 tools/cuc-bench/bench.py"
