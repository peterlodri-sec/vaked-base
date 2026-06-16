# vaked-oracle slice 4b · thread 2 — RE-vakedz (design)

**Date:** 2026-06-16
**Status:** approved (brainstorm) — ready for plan
**Base:** `origin/main` @ `54dc839` (slices 1–4a + 4b-thread-1 merged)

## One-liner

The oracle reverse-engineers our **own** `vakedz` Zig compiler — recursive self-RE — and
quantifies **cross-language** decompilation fidelity: the C-shaped decompiler output
(Ghidra → llm4decompile) scored against the **Zig** source. The headline research finding
is the language-boundary cost (C-vs-Zig fidelity < the C-vs-C libllama case).

## Why

Slice 1 RE'd `libllama` (C, FOSS ⇒ objective fidelity). Thread 2 turns the lens on the
ecosystem's own Zig front-end: the decompiler-LLM pipeline RE's the *compiler that is a
cache-native port of `vakedc`*. It tests how the fidelity premise holds when ground truth is
a **different source language** than the decompiler's C output.

## What already works (no change)

`oracle run --target <ELF> --funcs <fns> --source-dir <src>` already drives:
`ghidra_frontend` (any ELF) → `llm4decompile` refine → `fidelity.score` (token Dice) →
finding + hash-chained ledger. `fidelity.py`'s tokenizer (`[A-Za-z_]\w*|[^\sA-Za-z_]`) is
language-agnostic and its comment stripper handles Zig `//` (Zig has no `/* */`), so it scores
Zig source as-is — **degraded** (Zig keywords `pub fn const` vs C `int void`; signal comes
from shared identifiers, control-flow, operators). That degradation is the measured finding,
not a defect.

## Target acquisition (de-risked during brainstorm ✓)

dev-cx53 had no Zig. Verified working path (unprivileged, NixOS):
`nix shell nixpkgs#zig --command zig build` → **Zig 0.16.0** (== vakedz's
`minimum_zig_version`) → `vakedz/zig-out/bin/vakedz` = a 19.5 MB x86-64 ELF, **statically
linked, debug_info, not stripped** (ideal RE target — Ghidra resolves symbols). Sanity
`./vakedz parse` works. This is a **box build** (allowed; M3 ban does not apply); the 3-gate
protocol is satisfied (target dev-cx53, user approved option-a, preflight = `nix shell` pins
the version).

## Components / files (thin — the value is the acceptance run)

1. **`tools/oracle/Taskfile.yml`** (MODIFY) — new `run:vakedz` target:
   - `nix shell nixpkgs#zig --command zig build` in `vakedz/` (idempotent; skips if
     `zig-out/bin/vakedz` already fresh — `zig build` is itself incremental).
   - then `oracle.py run --target vakedz/zig-out/bin/vakedz --source-dir vakedz/src
     --funcs <FUNCS>` with the existing pyghidra nix-env derivation (copied from `run:`).
   - `FUNCS` default = a small set of vakedz functions confirmed during acceptance to be
     Ghidra-resolvable (e.g. the `cache.zig` crypto helpers + a parser entry).
   - **static-only by default** for this target (no `--infer-cmd`/dynamic): the self-RE
     finding is the static cross-language fidelity; dynamic evidence on a CLI compiler is out
     of scope for thread 2.
2. **`docs/oracle/v0.md`** (MODIFY) — "Recursive self-RE: vakedz (slice 4b · thread 2)"
   section: the premise, the cross-language fidelity finding (with the real numbers from
   acceptance), and the tree-sitter-Zig AST fidelity as the slice-5 follow-up.
3. **`.DEV.TODO`** (MODIFY) — thread 2 done; note the Zig-on-box recipe + the fidelity
   follow-up.

No new Python module is needed: `fidelity.py` is intentionally unchanged (the cross-language
degradation is the finding); the `run` loop already handles an arbitrary ELF target.

## Acceptance (the deliverable — run on dev-cx53)

Build vakedz (nix-zig), then `oracle run` on 2–3 vakedz functions with `--source-dir
vakedz/src`. Record per function: the Ghidra-resolved name, the refined-C, the
**cross-language fidelity score** vs the Zig source, and the finding/ledger `chain_ok`.
Compare the fidelity band to the slice-1 C-vs-C libllama band → quantify the language-boundary
cost. Empirical detail to resolve in the run: Ghidra's symbol names for Zig functions (debug
info present, but Zig mangles as `module.fn`); pick `--funcs` that resolve.

## Risks / open

- **Ghidra symbol resolution for Zig fns** — debug_info is present and the binary is not
  stripped, so names should resolve; the acceptance confirms the exact `--funcs` strings.
  Fallback: target by address if a name doesn't resolve.
- **Fidelity may be low (e.g. < 0.3)** — expected and *is the finding*; document the band,
  don't "fix" it. A near-zero score on a function would itself be a result (decompiler
  produced C bearing little token overlap with idiomatic Zig).
- **`zig build` time/space** — one-time ~tens of seconds; box has 28 GB free. Idempotent.

## Out of scope (own cycles)

- tree-sitter-Zig AST fidelity (replaces token-Dice) — slice 5.
- `re-vakedz.vaked` graph-derived scope for the `run` loop (the `run` path doesn't enforce
  graph scope today; only the kernel/team paths do) — a later cycle if wanted.
- dynamic (Frida/eBPF) evidence on vakedz.
- Thread 3 (ARP-emission, deferred — other dev's lane).

## Constraints (always)

Box build is allowed (M3 ban does not apply on dev-cx53); revdev unprivileged (Zig via
`nix shell`, no root); Snyk OFF; reuse `tools/ralph` + `eventd` read/call-only; don't touch
the execution ARP IR / L2 eBPF-LSM (other dev's lanes); never print secrets.
