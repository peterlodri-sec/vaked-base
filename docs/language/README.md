# Vaked Language Track

Vaked is a proposed typed, flake-native complement language for Nix.

It began as a way to make flake definitions, engines, and runtime declarations easier to author. It has now expanded into a capability graph language for agentic, native, mesh-aware, parallel systems.

## Current definition

Vaked is a **flake-native capability graph language** for declaring reproducible agentic, native, mesh-aware, parallel systems.

It compiles to:

- ordinary `flake.nix`
- NixOS modules
- Zig daemon configs
- eBPF policy manifests
- MCP broker configs
- OpenTelemetry config
- CrabCC indexes/catalogs
- generated documentation

## Core top-level declarations

```text
runtime
input
system
engine
host
network
filesystem
mcp
ebpf
budget
observability
runclass
workflow
index
catalog
stream
fiber
surface
mesh
device
mediaPipeline
parallel
```

## Grammar

The normative EBNF grammar and its design notes are in
[`vaked/grammar/README.md`](../../vaked/grammar/README.md) (currently **v0.3**).

## Type system (Goal 2)

The Vaked type system — structural typing + per-kind schema contracts, a
**closed** constraint set, a typed capability taxonomy with an attenuation
partial order (POLA checked at type-time), bounded generics, and a total +
deterministic checking pipeline (parse → resolve → elaborate → check, *validate
before generating*) — is specified normatively in
[`0011-type-system.md`](./0011-type-system.md). Its built-in schema and
capability catalog is [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md);
worked type-layer examples are in [`vaked/examples/types/`](../../vaked/examples/types/).

## Lowering (Goal 3)

Lowering — the stage **after** the Goal-2 check — turns the validated typed
semantic graph into the boring, inspectable artifacts Vaked owns (`gen/`) plus a
**Nix spine** (`flake.nix` + NixOS modules) that wires, builds, and deploys them.
It is a **pure, total, hermetic** function of (validated graph + pinned inputs):
same graph ⇒ byte-identical artifacts, with no network/IO during lowering
(fetching/building is the Nix build's job, pinned via `flake.lock` from
`trust = pinned{…}`). One emitter per target, selected by declared `emit`
targets; provenance is preserved per-artifact (generated header) and in
`.vaked/provenance.json`. Specified normatively in
[`0012-lowering.md`](./0012-lowering.md); hand-authored expected-output fixtures
for `operator-field.vaked` are in
[`vaked/examples/lowering/`](../../vaked/examples/lowering/).

## Design series

Numbered design notes in this directory. Each note is either a seed draft
(concept + output-first sketch) or a full spec; check its `§1 Status`.

| Note | Title | Role |
|------|-------|------|
| [0001](./0001-language-manifesto.md) | Language Manifesto | Founding design goals and constraints |
| [0003](./0003-reference-map.md) | Reference Map | Cross-reference of constructs to outputs |
| [0008](./0008-parallel-fibers-indexes-surfaces.md) | Parallel Fibers, Indexes, and Native Surfaces | Introduces the 9 core primitive kinds |
| [0009](./0009-kickoff-context-for-dedicated-session.md) | Kickoff Context | Session-start reference snapshot |
| [0010](./0010-mirageos-unikernel-surface.md) | MirageOS Unikernel Surface | Unikernel target for `surface` declarations |
| [0011](./0011-type-system.md) | Type System (Goal 2) | Structural typing, schemas, capability taxonomy |
| [0012](./0012-lowering.md) | Lowering (Goal 3) | Graph → artifacts: emitters, Nix spine, provenance |
| [0013](./0013-traversable-execution.md) | Traversable Execution Tree | `lifecycle` block for `parallel`/`fiber`: pause/resume/stop/rewind |
| [0014](./0014-typed-capability-graph.md) | Typed Capability Graph | Zero-proof containment; typed `domain.grant` refs |
| [0015](./0015-inline-arp-compiled-execution.md) | Inline ARP: Compiled-Parallelized Execution | IR exec overlay + wavefront schedule + dual-projection contract + verification |
| [0016](./0016-runtime-enforcement.md) | Runtime Enforcement | From compile-time POLA proof to kernel-enforced egress: `ebpf.policy` manifest + `agent-guardd` |
| [0017](./0017-pola-formalization.md) | POLA Formalization (deferred) | Deferred mechanization scaffold for the 0011 §4.5 soundness argument (Lean 4 / Coq) |

## Golden commands

```bash
vaked fmt
vaked check
vaked emit graph
vaked emit nix
vaked emit docs
vaked explain runtime operator-field
vaked explain fiber mediaCompress
vaked explain index zigbeeFirmware
```
