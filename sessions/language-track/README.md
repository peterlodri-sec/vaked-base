# Session kit — Vaked Language Track

A self-contained starting point for a **fresh, dedicated session** focused only on
designing the Vaked *language* (not the runtime or the HCP/Litany protocol — those
are tracked separately).

## How to start

Open a fresh Claude Code session in this repo and paste [`KICKOFF.md`](KICKOFF.md)
as your first message. It sets the role, goals, reading list, and guardrails.

## Scope

**In scope:** the Vaked language surface — grammar, type system, the parallelism
primitives, and the "lower-to-artifacts" story (what each construct compiles to).

**Out of scope (other tracks):**
- HCP / Litany wire protocol + `.hcplang` schema → `protocol/` (being specified now).
- Runtime daemons → `daemons/`, `docs/runtime/`.

## Reading list (in order)

1. `docs/context/PROJECT_CONTEXT.md` — canonical overview, mantra, membranes.
2. `docs/language/README.md` — language-track index.
3. `docs/language/0001-language-manifesto.md` — identity & principles.
4. `docs/language/0008-parallel-fibers-indexes-surfaces.md` — the parallelism layer.
5. `docs/language/0003-reference-map.md` + `references/` — influences & sparks (incl. `0010-mirageos-unikernel-surface.md`).
6. `vaked/grammar/vaked-v0-plus.ebnf` — current grammar.
7. `vaked/schema/parallel-types.md` — type notes.
8. `vaked/examples/` — `operator-field.vaked`, `engines/zig.vaked`.

## Working agreement

- Use the **`vaked-language-author`** skill (conventions: grammar-before-code, stay within the primitives, determinism, output-first, source-mapped).
- Capture decisions as numbered design notes `docs/language/00NN-*.md`.
- The mantra is the contract: *Vaked declares · Nix materializes · OTP supervises · Zig enforces · eBPF testifies · CrabCC indexes · Surfaces reveal.*
