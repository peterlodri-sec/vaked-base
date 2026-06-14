# sandboxd

Namespace / cgroups / exec enforcement daemon — WP4-S1 (Jun 24 2026).

- Plan: [`../../docs/superpowers/plans/2026-06-14-wp4-kickoff.md`](../../docs/superpowers/plans/2026-06-14-wp4-kickoff.md)
- Backend: native-exec (Linux namespaces + cgroups v2 + seccomp; pure Zig)

## Build

```
zig build               # → zig-out/bin/sandboxd
zig build test
```

Build target: `dev-cx53`. Min Zig 0.16.
