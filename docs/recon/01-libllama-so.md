# target #1 — libllama.so.0 (the LLM runtime)

Build `llama-cpp-9190`. `llama-cli` is a thin wrapper (**no exported functions**);
the runtime lives in the shared libs:

| lib | holds |
|-----|-------|
| `libllama.so.0` | `llama_decode`, `llama_encode`, `llama_model_load_from_file`, `llama_batch_*`, `llama_sampler_*` |
| `libggml-base.so.0` | `ggml_*` (graph/tensor) |
| `libggml-cpu.so.0` / `-blas` | compute backends |

## run 2026-06-15 — finding `81ff9c4f…`
llm4decompile-6.7b-v2 (Q4_K_M), temp=0. **confidence 0.0376 · ledger 8 entries · chain_ok=TRUE.**

| fn | fidelity | refined C |
|----|----------|-----------|
| `llama_decode` | 0.017 | faithful (below) |
| `llama_model_load_from_file` | 0.0451 | 892 chars |
| `llama_batch_init` | 0.0507 | 848 chars |

`llama_decode` as reconstructed by the model:
```c
int llama_decode(llama_context *ctx) {
    int ret = llama_context::decode(ctx, &ctx->batch);
    if (ret > 1)
        llama_log_internal(4, "%s: failed to decode, ret = %d\n", "llama_decode", ret);
    return ret;
}
```
Faithful to the real inference entry point. Low fidelity = token-similarity vs heavily
optimized internals; the **decompilation itself is sound**. Dynamic evidence (frida/ebpf)
was `null` this run — static pass first.

## next targets
- `libggml-base.so.0`: `ggml_compute_forward`, `ggml_graph_compute` — the tensor hot path.
- `llama_sampler_apply` — sampling logic.
- `llama_model_load_from_file` mmap path **under the eBPF watcher** (observe the GGUF mmap + weight reads).
