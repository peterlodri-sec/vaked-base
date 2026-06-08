---
name: vaked-language-author
description: Use when authoring or editing .vaked files, evolving the Vaked grammar (EBNF), or extending the type/schema docs — keeps the language self-consistent across vaked/ and docs/language/. Trigger on ".vaked", "grammar", "EBNF", "Vaked primitive", "capability graph", "parallel-types".
---

# Authoring Vaked

Vaked is a small, typed, deterministic, side-effect-free, Nix-output-first,
capability- and graph-native language. Anything authored here must preserve those
properties. The mantra is the contract: *Vaked declares. Nix materializes. OTP
supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.*

## Where things live

| Concern | Path |
|---------|------|
| Grammar (source of truth) | `vaked/grammar/vaked-v0-plus.ebnf` |
| Type / schema notes | `vaked/schema/parallel-types.md` |
| Examples | `vaked/examples/` (+ `examples/engines/`) |
| Design series | `docs/language/0001…0010-*.md` |
| Canonical overview | `docs/context/PROJECT_CONTEXT.md` |

## Rules

1. **Grammar before code.** Adding or changing a construct means editing
   `vaked-v0-plus.ebnf` first, then giving it at least one example under
   `vaked/examples/`. No example → the construct isn't real yet.
2. **Stay within the primitives.** Core primitives include: `index`, `catalog`,
   `stream`, `fiber`, `surface`, `mesh`, `device`, `mediaPipeline`, `parallel`
   (see `docs/language/0008-parallel-fibers-indexes-surfaces.md`). Prefer composing
   these over inventing new top-level keywords; if a new primitive is justified,
   write a numbered design note (`docs/language/00NN-*.md`) explaining why.
3. **Determinism.** No construct may imply evaluation-time side effects. Evaluation
   produces a typed semantic graph; effects belong to the generated artifacts.
4. **Output-first.** Every construct must answer: *what Nix / Zig-config / eBPF /
   OTel / CrabCC / docs artifact does this lower to?* If it lowers to nothing, it
   doesn't belong in the language.
5. **Source-mapped & explainable.** Keep names and structure traceable from output
   back to source.

## When you finish

- Cross-link new design notes from `docs/language/README.md` and the reference map.
- If a change affects the runtime contract, note it in `docs/runtime/README.md`.
- Validate examples parse against the grammar (parser TBD — until then, review by hand against the EBNF).
