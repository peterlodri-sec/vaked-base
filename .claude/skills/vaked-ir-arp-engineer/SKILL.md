---
name: vaked-ir-arp-engineer
description: Engineer the Vaked IR/ARP compiler internals and reason about Vaked as an LLM linguist. Use when working on the vakedc pipeline (lexer→parser→resolve→check→graph→lower→emit), the typed semantic graph / ARP traversable execution graph, lowering to artifacts (flake.nix, Zig configs, eBPF, OTel), the type system, or evolving the EBNF grammar, schema, and .vaked examples. Trigger on "IR", "ARP", "lowering", "vakedc", "typed semantic graph", "capability graph", "type system", "EBNF", "Vaked grammar", "emitter", "checker".
---

# Vaked IR/ARP Engineer + LLM Linguist

Two roles over one codebase. Wear both:

- **IR/ARP Engineer** — the `vakedc/` compiler internals. Builds the typed semantic graph (the IR) from source, validates capabilities, and lowers to artifacts. ARP = the traversable execution graph the runtime walks (pause/rewind/resume/stop).
- **LLM Linguist** — the *surface* language. Grammar (EBNF), type semantics, schema, and `.vaked` examples. Keeps the language self-consistent so it reads and compiles cleanly.

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies.

A Vaked declaration → typed semantic graph (IR) → artifacts: `flake.nix`/NixOS modules, Zig daemon configs, eBPF policy manifests, OTel config, CrabCC indexes, docs.

## The compiler pipeline (IR Engineer)

`vakedc/` is a 9-module Python compiler. Stages run in order; each consumes the prior stage's structure.

| Stage | Module | Lines | Role |
|-------|--------|------:|------|
| 1 Lex | `lexer.py` | 388 | source → tokens |
| 2 Parse | `parser.py` | 844 | tokens → AST (declarations, capabilities, lifecycle) |
| 3 Resolve | `resolve.py` | 345 | bind names, merge user schemas over builtins |
| 4 Check | `check.py` | 1277 | type + capability validation (stages 1–4), error codes |
| 5 Graph | `graph.py` | 159 | AST → typed semantic graph (the IR) |
| 6 Lower | `lower.py` | 1400 | IR → per-target artifact models |
| 7 Emit | `emit.py` | 160 | artifact models → files |

Entry: `__main__.py` (269) — CLI driver. `check.py` and `lower.py` are the two hot spots — touch them first for behavior changes.

**Where things live (search `references/files.md` for `## File: <path>`):**
- Checker error codes + capability checking → `vakedc/check.py` (e.g. `E-CAP-*`)
- Primitive → artifact mapping → `vakedc/lower.py` + `docs/language/0012-lowering.md`
- Name binding / schema override-by-name → `vakedc/resolve.py`

## The language (LLM Linguist)

| Artifact | Path | Note |
|----------|------|------|
| Grammar | `vaked/grammar/vaked-v0-plus.ebnf` (260) | v0+; declaration + capability model |
| Grammar guide | `vaked/grammar/README.md` (231) | prose companion to the EBNF |
| Builtins schema | `vaked/schema/builtins.vaked` (179) | built-in kinds; user schemas override by name |
| Parallel types | `vaked/schema/parallel-types.md` (508) | fibers/indexes/surfaces type theory |
| Examples | `vaked/examples/{primitives,types,lowering,engines}/` | grammar-coverage + golden lowering |

**Grammar-before-code rule:** new constructs go in the EBNF + an example *first*, then the parser. Use the `vaked-language-author` skill for grammar/schema edits.

## Design series (the theory)

`docs/language/` — read the doc before changing the matching subsystem:

- `0001-language-manifesto.md` — what Vaked is
- `0008-parallel-fibers-indexes-surfaces.md` (215) — parallelism primitives; `device` + `mediaPipeline` concepts
- `0011-type-system.md` (646) — kinds; `Device` and `MediaPipeline` are first-class non-generic kinds
- `0012-lowering.md` (830) — emitters, exemplar mappings, primitive→artifact reference table, deferred targets
- `0003`, `0009`, `0010` — reference map, session kickoff, MirageOS unikernel surface

**ARP note:** the lifecycle/traversable-execution-graph design (pause/rewind/resume/stop, `lifecycle` block) is in-flight in a separate worktree — **not yet in this corpus**. Don't cite `0013`/`0014` from here; confirm against the live branch first.

## Corpus (full source, searchable)

Generated reference — 46 files, 9,065 lines, ~97k tokens:

- `references/files.md` — all file contents. Grep `## File: <path>` to jump; grep keywords for usages.
- `references/project-structure.md` — directory tree + per-file line counts.
- `references/summary.md` — stats + format.

Read-only snapshot. Edit the real repo files, not these. Largest: `lower.py` (1400), `check.py` (1277), `parser.py` (844), `0012-lowering.md` (830), `0011-type-system.md` (646).

## Workflows

**Add/change a language construct (Linguist→Engineer):**
1. EBNF + example first (`vaked-language-author` skill).
2. `lexer.py` → `parser.py` to accept it.
3. `check.py` type/capability rules; `graph.py` if it adds IR nodes.
4. `lower.py` + `emit.py` for artifact output; add a golden under `vaked/examples/lowering/`.
5. Run `tests/spec/run_all.py`.

**Trace a primitive to its artifact (Engineer):**
1. `0012-lowering.md` for the spec'd mapping.
2. Grep the kind in `lower.py`.
3. Cross-check the golden in `vaked/examples/lowering/gen/`.

**Debug a checker rejection:**
1. Grep the error code (`E-CAP-*`, etc.) in `check.py`.
2. Read the stage that raises it; confirm the type rule in `0011-type-system.md`.

---

Corpus generated by Repomix; entry point hand-authored for the IR/ARP + linguist persona.
