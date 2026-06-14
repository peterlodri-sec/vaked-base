# Vaked Runtime — daemon roster

> OTP supervises. Zig enforces. eBPF testifies.

The runtime is the **enforcement and supervision plane** that a Vaked declaration materializes onto. An OTP control plane supervises a set of single-purpose Zig daemons; eBPF provides kernel-level evidence. This document is the roster; each daemon gets its own design → plan → implementation cycle, and code lands under [`/daemons`](../../daemons/).

## Daemons

| Daemon | Language | Membrane(s) | Responsibility |
|--------|----------|-------------|----------------|
| `agent-supervisord` | Erlang/OTP | process | Control plane: supervision trees, lifecycle, restart strategy, orchestration of the Zig daemons |
| `agent-guardd` | Zig | ebpf, network | eBPF program loader, policy compilation, audit; the testimony layer |
| `sandboxd` | Zig | process, filesystem | Namespaces, cgroups, mounts, supervised `exec` of agent workloads |
| `mcp-brokerd` | Zig | mcp | Brokered MCP tool calls — policy, budgets, approvals, structured errors |
| `fs-snapshotd` | Zig | filesystem | Overlays, diffs, write budgets, artifact capture |
| `eventd` | Zig | — | Append-only, hash-chained event log (tamper-evident audit spine) |
| `otelcol` | (OpenTelemetry) | — | Telemetry collection/export across the plane |

## Membrane mapping

The runtime enforces the membranes declared in Vaked (see [`docs/context/PROJECT_CONTEXT.md`](../context/PROJECT_CONTEXT.md)):

```text
network    → agent-guardd (deny-by-default egress, DNS oracle, eBPF cgroup maps)
filesystem → sandboxd + fs-snapshotd (explicit mounts, overlays, snapshots, write budgets)
mcp        → mcp-brokerd (brokered calls, budgets, approvals)
process    → sandboxd (cgroups, namespaces, supervised execution)
ebpf       → agent-guardd (kernel evidence for network/process/file events) + eventd
```

## Language to Runtime Mapping

Vaked primitives lower to two classes of artifact (see [`docs/language/0012-lowering.md`](../language/0012-lowering.md) for the normative spec):

**Compiler-generated artifacts (`gen/`)** — produced by `vakedc lower`, checked into the repo:

| Primitive | Artifact | Consuming daemon |
|-----------|----------|-----------------|
| `fiber` | `gen/zig/<name>.json` — Zig daemon config | `sandboxd` (process isolation), `agent-guardd` (eBPF policy) |
| `index` | `gen/catalog/<name>/` — CrabCC derivation + manifest | CrabCC toolchain (offline) |
| `catalog` | `gen/catalog/<name>.jsonl` — bundled catalog | CrabCC toolchain (offline) |
| `ebpf` | `gen/ebpf/<name>.policy` — allow/deny rules | `agent-guardd` (kernel enforcement) |
| `observability` | `gen/otel/<name>.yaml` — collector config | `otelcol` |
| all | `gen/docs/` — generated reference docs | human operators / `surface` UIs |

**Nix spine** — `flake.nix` + NixOS modules wiring the above into a deployable system (built by Nix, not `vakedc`).

**Capability declarations** route to membrane daemons at runtime:

| Capability | Daemon | Enforcement |
|-----------|--------|-------------|
| `network` | `agent-guardd` | eBPF cgroup egress maps, DNS oracle |
| `filesystem` | `sandboxd` + `fs-snapshotd` | namespaces, mounts, write budgets |
| `mcp` | `mcp-brokerd` | brokered tool calls, budgets, approvals |
| `process` | `sandboxd` | cgroups, namespaced exec |
| `ebpf` | `agent-guardd` | kernel-level evidence for all membrane events |

`eventd` receives events from all membrane daemons and provides the tamper-evident audit spine that `surface` declarations can query.

## Status

Stub. No daemon is implemented. The roster and membrane mapping are the contract that the Vaked compiler targets and that each daemon's eventual spec must satisfy.
