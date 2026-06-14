# docs/vision — aspirational material (NOT implemented)

> **Status: vision / narrative.** These documents describe an *aspirational*
> Vaked architecture and were authored as NotebookLM seed material. They do
> **not** describe the current codebase and must not be read as a spec.
>
> Reality checks (2026-06-14):
> - `crabcc` is a Rust **SQLite symbol indexer** with in-memory fuzzy search —
>   it does **not** emit LLVM IR or do zero-copy mempalace pointer loads.
> - `vakedc` is an early-stage compiler; the runtime daemons are stubs
>   (`docs/runtime/README.md`). There is no `vaked.topology` MLIR dialect and no
>   `E-TOPO-DEPTH` build-time check today.
> - The "Ralph Loop autonomous refactoring" narrative is illustrative, not a log
>   of a real automated change.
>
> Keep these for narrative/marketing/NotebookLM use. For what actually exists,
> see [`docs/OVERVIEW`-style docs], `AGENTS.md`, and the per-crate docs.

## Contents
- [`the_vaked_manifesto_systems_imbalance.md`](the_vaked_manifesto_systems_imbalance.md)
- [`mlir_topology_and_static_invariants.md`](mlir_topology_and_static_invariants.md)
- [`the_mempalace_paradox_zero_copy_state.md`](the_mempalace_paradox_zero_copy_state.md)
- [`the_ralph_loop_autonomous_refactoring.md`](the_ralph_loop_autonomous_refactoring.md)
- [`notebooklm-playbook.md`](notebooklm-playbook.md)

Source: Gemini share `https://gemini.google.com/share/e13ccfe06774`.
