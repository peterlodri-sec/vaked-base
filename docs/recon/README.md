# recon vault

Operational notebook for vaked-oracle reverse-engineering runs — **recipes + findings**,
not design. (Design → `docs/oracle/`; spec → `docs/superpowers/specs/2026-06-15-vaked-oracle-design.md`.)

| file | what |
|------|------|
| [00-dev-cx53-env.md](00-dev-cx53-env.md) | golden recon-env bring-up on dev-cx53 (PyGhidra · llama-server · GGUF · ground truth) |
| [01-libllama-so.md](01-libllama-so.md) | target #1 — the LLM runtime (`libllama.so.0`), decompiled functions |
| [golden-ssh-patterns.md](golden-ssh-patterns.md) | bulletproof remote-exec patterns (learned the hard way) |

Substrate: the **revdev** cell on dev-cx53 (least-authority, no sudo). Heavy work on the box, never the M3.
Recursive premise: a decompiler-LLM (llm4decompile-6.7B) reverse-engineers the inference-LLM's own runtime.
