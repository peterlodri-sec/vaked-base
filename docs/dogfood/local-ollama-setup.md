# Local Ollama setup — ralph dogfood loop at zero cloud cost (M3)

Run the existing `tools/ralph/` decision loop against a self-hosted Ollama model
instead of OpenRouter. No code change to ralph — it already honors a base-url +
key override.

## Memory budget — keep Ollama under ~8GB

A 16k context with an 8B model nearly froze the host. Serve bounded:

```bash
OLLAMA_HOST=127.0.0.1:11434 \
OLLAMA_CONTEXT_LENGTH=8192 \
OLLAMA_MAX_LOADED_MODELS=1 \
OLLAMA_KEEP_ALIVE=60s \
OLLAMA_FLASH_ATTENTION=1 \
ollama serve &
```

- `OLLAMA_CONTEXT_LENGTH=8192` — ralph prompts reach ~21k tokens; they are
  truncated to this window. Acceptable for plumbing. **Do not raise to 16k.**
- `OLLAMA_MAX_LOADED_MODELS=1` + `OLLAMA_KEEP_ALIVE=60s` — one model resident,
  auto-unloaded after 60s idle to free RAM.
- `OLLAMA_FLASH_ATTENTION=1` — smaller KV cache.

`qwen3:8b` ≈ 6.5GB resident, `qwen2.5-coder:7b` ≈ 6GB. Both fit under 8GB.

## Model must support "thinking"

ralph stage-1 sends `reasoning={enabled, effort}`. Ollama **400s** on a model
that lacks thinking (`"<model> does not support thinking"`). Use `qwen3:8b`
(thinking-capable); `qwen2.5-coder` does **not** work for ralph's decide loop.
`response_format` (json / json_schema) works on both.

## Run

`tools/ralph/tracks.local.json` pins every track to `qwen3:8b`. Point ralph at
Ollama's OpenAI-compatible endpoint and use the local tracks file:

```bash
export RALPH_BASE_URL=http://localhost:11434/v1/chat/completions
export RALPH_API_KEY=ollama          # placeholder; Ollama ignores it
export RALPH_CRITIQUE=off            # skip stage-3 to save a model round-trip

# free dry-run (no model call): build prompts + cost estimate
python3 tools/ralph/ralph.py decide --tracks tools/ralph/tracks.local.json \
  --track mlir-topology --dry-run

# one real decision against the local model
python3 tools/ralph/ralph.py decide --tracks tools/ralph/tracks.local.json \
  --track mlir-topology

# verify the hash-chained ledger replays clean
python3 tools/ralph/ralph.py events --replay
```

Validated 2026-06-14: real decision appended to the ledger (seq 19), chain
replays clean, `$0` real cost (`tracks.local.json` model is unknown to the
fallback price table, so the reported cost is a nominal estimate, not spend).
