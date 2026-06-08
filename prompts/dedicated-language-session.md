# Dedicated Vaked Language Session Prompt

We are starting a dedicated language-design session for Vaked.

## Context

Vaked is a proposed typed, flake-native complement language for Nix.

It began as a way to make flake definitions, engines, and runtime declarations easier to author. It has now expanded into a capability graph language for agentic, native, mesh-aware, parallel systems.

Core stack:

```text
Vaked declares.
Nix materializes.
OTP supervises.
Zig enforces.
eBPF testifies.
CrabCC indexes.
Surfaces reveal.
```

Vaked should compile into ordinary, inspectable artifacts:

- `flake.nix`
- NixOS modules
- Zig daemon configs
- eBPF policy manifests
- MCP broker configs
- OpenTelemetry config
- CrabCC indexes/catalogs
- generated documentation
- operator surface configs

## Current language identity

Vaked is a **flake-native capability graph language**.

It declares:

- inputs
- systems
- engines
- hosts
- network policies
- filesystem policies
- MCP tool policies
- eBPF programs
- budgets
- observability profiles
- runclasses
- workflows
- indexes
- catalogs
- streams
- fibers
- native surfaces
- mesh/device nodes
- media pipelines
- approval gates

## Design constraints

Preserve these:

- Nix remains the lower-level substrate.
- Generated artifacts are boring, inspectable, and diffable.
- Evaluation is deterministic and side-effect-free.
- Network, filesystem, tools, secrets, and approvals are explicit capabilities.
- Raw Nix escape hatches exist but are visible and source-mapped.
- `vaked explain` is first-class.
- The language should stay small enough to implement and remember.
- Avoid becoming a generic app language, cloud DSL, or shell scripting language.

## Reference influences

Borrow from:

- Nix: flakes, derivations, store, attrsets, reproducibility.
- Nickel: records, contracts, optional typing, configuration ergonomics.
- CUE: constraints, schema/data unification, validation-first design.
- Dhall: total programmable configuration and normalization.
- Starlark: deterministic embedded language model.
- HCL: readable blocks.
- OPA/Rego: decisions as data.
- OTP: supervision vocabulary.
- Zig: explicitness and native systems posture.
- Zigbee: mesh/device/capability topology.
- CrabCC: raw content indexes and reproducible catalogs.

## New reference sparks

Use these as inspiration, not as direct dependencies:

- `raylib-zig`: native visualization surfaces.
- `zero-native`: Zig-native desktop/mobile shell with web UI.
- `zigimg`: native media/image pipelines.
- `zigbee-OTA`: raw manifest/index pattern.
- `zigpy`: Zigbee stack semantics.
- `nullclaw`: Zig-native AI assistant infrastructure.
- `awesome-zig` and `zig.guide`: corpus/index sources.

## Task

Design Vaked v0 as a language.

Please produce:

1. A crisp v0 language identity.
2. The core semantic graph model.
3. A v0/v0.1/later split for declarations.
4. Three syntax variants for declarations, functions, imports, merges, defaults, overrides, raw Nix, and fibers.
5. A recommended syntax direction.
6. A v0 grammar.
7. A type system sketch.
8. A compiler pipeline.
9. `vaked explain` semantics.
10. Five example `.vaked` files.
11. A milestone plan with acceptance criteria.

Prioritize semantics before aesthetics. Syntax is the mask; the graph is the face.
