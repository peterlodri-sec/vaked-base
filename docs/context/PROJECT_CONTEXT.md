# Project Context: Vaked, CrabCC, and the Operator Field

## Summary

Vaked is a proposed flake-native complement language for Nix. It describes reproducible agent systems, runtime membranes, capability graphs, indexes, fibers, native surfaces, and mesh/device interactions. It compiles into ordinary Nix flakes, NixOS modules, Zig daemon configs, eBPF policy manifests, OpenTelemetry config, generated docs, and CrabCC indexes.

## Core stack

```text
Vaked source
    ↓
typed semantic graph
    ↓
generated artifacts
    ├── flake.nix
    ├── NixOS modules
    ├── Zig daemon configs
    ├── eBPF policy manifests
    ├── OTel collector config
    ├── CrabCC indexes/catalogs
    └── docs
    ↓
NixOS host
    ↓
OTP supervision plane
    ↓
Zig enforcement daemons
    ↓
eBPF evidence
    ↓
operator surfaces
```

The `typed semantic graph → generated artifacts` step is **lowering** (Goal 3),
specified in [`docs/language/0012-lowering.md`](../language/0012-lowering.md): a
pure, total, hermetic graph→artifacts pass (Vaked owns the `gen/` artifacts; a
Nix spine wires/builds/deploys them). The graph it consumes is produced by the
type checker (Goal 2, [`docs/language/0011-type-system.md`](../language/0011-type-system.md)).

## Mantra

```text
Vaked declares.
Nix materializes.
OTP supervises.
Zig enforces.
eBPF testifies.
CrabCC indexes.
Surfaces reveal.
```

## Runtime membranes

```text
network     deny-by-default egress, DNS oracle, eBPF cgroup maps
filesystem explicit mounts, overlays, snapshots, write budgets
mcp         brokered tool calls, budgets, approvals, structured errors
process     cgroups, namespaces, supervised execution
ebpf        kernel evidence for network/process/file events
media       native compression/redaction/transcode pipelines
mesh        device/agent/node topology and capability routing
index       raw + CrabCC reproducible corpora and catalogs
surface     local native UI, web-native UI, TUI, iOS/operator clients
```

## Language identity

Vaked should be small, typed, deterministic, side-effect-free during evaluation, Nix-output-first, explainable, source-mapped, policy-aware, capability-oriented, and graph-native.
