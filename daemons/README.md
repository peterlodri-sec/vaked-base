# daemons/

Code subtree for the Vaked runtime daemons. **Currently empty** — this is the monorepo slot where each daemon's implementation will land.

The authoritative roster, responsibilities, and membrane mapping live in [`docs/runtime/README.md`](../docs/runtime/README.md). Per-daemon directories (e.g. `daemons/agent-guardd/`, `daemons/sandboxd/`, `daemons/eventd/`) are created when that daemon's design → plan → implementation cycle begins.

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
