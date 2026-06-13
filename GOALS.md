# Goals

> Vaked declares. Nix materializes. OTP supervises. Zig enforces. eBPF testifies. CrabCC indexes. Surfaces reveal.

## Vision

Vaked exists to answer a single question: *what is the minimal, correct description of an agentic system that a machine can turn into a running, policy-enforced, observable deployment?*

The answer is a **capability graph** — a typed, reproducible declaration of what a system does, what it is allowed to touch, who it talks to, and how it is supervised. That declaration compiles to real artifacts: a NixOS flake, Zig daemon configs, eBPF policy manifests, OTel collector config, and CrabCC indexes. The compilation target is not a container or a VM — it is a bare-metal NixOS host with a purpose-built supervision plane.

The design is shaped by four convictions:

1. **Declaration before configuration.** Operator intent lives in one typed source of truth. Derived artifacts are generated, not hand-written.
2. **The kernel is the enforcement layer.** eBPF policy is not advisory. It is the evidence that the system is behaving as declared. If the kernel says it happened, it happened; if the kernel says it didn't, it didn't.
3. **Supervision is structural.** OTP-style process supervision is not optional scaffolding — it is the runtime model. Every daemon in the system has an explicit supervisor, restart policy, and failure budget declared in Vaked before it is materialized.
4. **Immutability and provenance.** Every compilation emits a `provenance.json` that chains source hash → graph hash → artifact hash. The decision log (`ralph`) is append-only and hash-chained. Reproducibility is not a feature; it is the baseline.

## Milestones

### Phase 0 — Language foundation *(in progress)*
- [x] EBNF grammar (`vaked-v0-plus.ebnf`) covering nodes, edges, capability declarations, fibers, indexes, surfaces, parallel-types
- [x] Design series `0001`–`0012` (manifesto through lowering)
- [x] `vakedc` prototype: parse → LPG → type-check (stages 1–4) → lower (flake.nix, eventd, OTP, Zig, CrabCC)
- [x] `provenance.json` output chaining source → graph → artifacts
- [ ] Full lowering coverage for all node/edge kinds in the grammar
- [ ] Language v0 spec freeze: no further breaking grammar changes without a version bump

### Phase 1 — Compiler maturity
- [ ] `vakedc check` covers all type rules in `docs/language/0011-type-system.md` with no gaps
- [ ] `vakedc lower` emits correct, deployable artifacts for the full `vakedos` example declaration
- [ ] LSP server (`vakedc lsp`) stable enough for daily use in the Vaked IDE
- [ ] Comprehensive spec test suite (all `vaked/examples/` round-trip through parse → check → lower without errors)

### Phase 2 — Runtime: stubs → real
- [ ] OTP supervision plane: GenServer + Supervisor tree for each daemon in `daemons/`, generated from Vaked declarations
- [ ] Zig enforcement daemons: at least `sandboxd` and one policy daemon compiled and running on vakedos
- [ ] eBPF policy layer: at least one membrane (process or filesystem) enforced and producing OTel spans
- [ ] End-to-end smoke test: a `.vaked` file compiles, deploys to vakedos via `nixos-rebuild`, and the declared eBPF policy is active

### Phase 3 — Wire protocol
- [ ] HCP / Litany RFC series complete (RFCs 0001–0006 ratified, no open design questions)
- [ ] Reference implementation of the HCP frame encoder/decoder (Zig or Elixir)
- [ ] At least two daemons communicating over Litany on vakedos

### Phase 4 — Surfaces and observability
- [ ] At least one operator surface (terminal or web) connected to the OTel collector and rendering live eBPF evidence
- [ ] CrabCC index populated from a real Vaked-compiled deployment
- [ ] `ralph` decision loop covers all four tracks with ratified entries and feeds back into the language design

### Phase 5 — Language v1
- [ ] Grammar stable across a full vakedos deployment cycle with no unplanned breaking changes
- [ ] `vakedc` pipeline is self-hosting: the vakedos host itself is declared in a `.vaked` file that compiles to the `hosts/vakedos/` NixOS config
- [ ] Published language reference derived from the EBNF and design series
