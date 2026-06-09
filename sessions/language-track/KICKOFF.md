# Vaked Language Track — dedicated session kickoff

> Paste everything below this line as your first message in a fresh session opened in this repo.

---

You are working in the `vaked-base` monorepo on the **Vaked language track only**. Vaked is a small, typed, deterministic, side-effect-free, Nix-output-first, capability- and graph-native language — *"Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal."*

**First, invoke the `vaked-language-author` skill** and read, in order:
`docs/context/PROJECT_CONTEXT.md`, `docs/language/README.md`, `docs/language/0001-language-manifesto.md`, `docs/language/0008-parallel-fibers-indexes-surfaces.md`, `docs/language/0003-reference-map.md`, `vaked/grammar/vaked-v0-plus.ebnf`, `vaked/schema/parallel-types.md`, and the examples in `vaked/examples/`.

**Goals for this session** (pick up in this order; brainstorm before writing, capture decisions as numbered design notes under `docs/language/`):

1. **Harden the grammar.** Review `vaked-v0-plus.ebnf` for gaps and ambiguities; produce a `v0.2` that covers every primitive (`index`, `catalog`, `stream`, `fiber`, `surface`, `mesh`, `device`, `mediaPipeline`, `parallel`) with at least one example each under `vaked/examples/`.
2. **Formalize the type system.** Turn `vaked/schema/parallel-types.md` into a real typed-semantic-graph spec: what types exist, how capabilities and the parallelism primitives are typed, evaluation determinism rules.
3. **Nail the lowering story.** For each construct, specify what it compiles to (flake.nix / NixOS module / Zig daemon config / eBPF policy / OTel config / CrabCC index / docs). If a construct lowers to nothing, it doesn't belong.

**Out of scope this session:** the HCP/Litany wire protocol and `.hcplang` schema (tracked under `protocol/`), and runtime daemon implementation (`daemons/`).

**Constraints:** evaluation is side-effect-free (effects live in generated artifacts); everything is source-mapped and explainable; prefer composing existing primitives over inventing keywords — justify any new primitive in a design note.

Start by brainstorming Goal 1 with me before editing the grammar.

---

*(This kit lives at `sessions/language-track/`. The original carryover prompt is `prompts/dedicated-language-session.md`; this kickoff supersedes it with the current repo layout.)*
