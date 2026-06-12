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
| `memoryd` | Zig | — | Runtime memory plane for the `memory` kind: mines `source` streams into typed entries appended via `eventd`, serves capability-bound recall over the folded state ([0014](../language/0014-memory-primitive.md), #24) |
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

## Status

Stub. No daemon is implemented. The roster and membrane mapping are the contract that the Vaked compiler targets and that each daemon's eventual spec must satisfy.
