# daemons/

Code subtree for the Vaked runtime daemons. **Currently empty** — this is the monorepo slot where each daemon's implementation will land.

The authoritative roster, responsibilities, and membrane mapping live in [`docs/runtime/README.md`](../docs/runtime/README.md). Per-daemon directories (e.g. `daemons/sandboxd/`) are created when that daemon's design → plan → implementation cycle begins.

**Reference implementations land at the repo root** (the `#15` pattern: a Python oracle that fixes the bytes + the decision; the Zig daemon reproduces them, and lands under `daemons/` later):

- [`eventd/`](../eventd) — append-only, hash-chained event log.
- [`agent_guardd/`](../agent_guardd) — `agent-guardd`: the `network`/`ebpf` membrane (deny-by-default egress enforcement + eBPF testimony). It closes the first end-to-end vertical slice; see [`docs/runtime/agent-guardd.md`](../docs/runtime/agent-guardd.md).

Planned (see the roster):

```text
agent-supervisord   OTP control plane (Erlang)
agent-guardd        Zig · eBPF loader / policy / audit
sandboxd            Zig · namespaces / cgroups / mounts / exec
mcp-brokerd         Zig · MCP tool policy / budget / approval
fs-snapshotd        Zig · overlays / diffs / artifacts
eventd              Zig · append-only / hash-chained event log
otelcol             OpenTelemetry collector
```
