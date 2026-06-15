# vaked dev brief (appended to the local Claude Code system prompt by `vk code`)

You are working on **vaked-aegis** (the local proposer/judge verification kernel)
and **vaked-oracle** (the LLM-assisted reverse-engineering side-research) in the
`vaked-base` monorepo. Full onboarding: `docs/dogfood/README.md`.

## Ground rules
- **Branch from `origin/main`.** The local `main` may be a stale scaffold; never
  assume it's the trunk. Other PRs land constantly — rebase/cut fresh, never
  revert intervening merges.
- **Never build/compile on this M3.** clang/zig/cargo/nix builds, eBPF, LD_PRELOAD,
  seccomp are gated to **dev-cx53** (NixOS, `dev@100.105.72.88`, sanctioned target).
  macOS can't do LD_PRELOAD/eBPF. Use `vk to-dev53` / the dogfood `Taskfile.yml`.
- **Self-hosted LLM is on dev-cx53** (crabcc-ollama-stack → litellm `:4000`,
  auth-gated). Keep any local Ollama ≤8GB.
- **Lane boundaries:** another dev owns the ARP IR / DSL parser, the A2A scheduler,
  the ZetaTensor wire / io_uring Zig logger, and the **L2 eBPF-LSM** enforcement.
  Our eBPF/Frida work is **advisory evidence (L1)**, never enforcement. No AIL/ARP
  parser here — transition records are neutral JSON.

## The kernel (tools/dogfood/)
Four gates, all must pass or the tree rolls back: **capability** (POLA path-scope,
lowered from a Vaked graph) · **declared==actual** · **observed** (LD_PRELOAD/Frida)
· **replay-stable** → accept appends to the `eventd` WAL. Pure stdlib; 16 tests in
`test_kernel.py`. Hot paths are linear-in-change (see `kernel-v0.md`).

## Conventions
- Grammar-before-code for Vaked; validate examples with `python3 -m vakedc check`.
- Reuse `eventd` (don't change its format) and the dogfood `Taskfile.yml`.
- Run `python3 tools/dogfood/test_kernel.py` after kernel edits.
