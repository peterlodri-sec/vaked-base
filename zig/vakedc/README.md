# vakedc-zig (v0.x) — native Zig front-end for Vaked

A small, **runnable** Zig lexer + parser for a documented subset of the Vaked
grammar. This is the first step of the "Zig enforces" half of the project
thesis and the long-horizon native-compiler item in
[`docs/compiler/OPTIMIZATION_ROADMAP.md`](../../docs/compiler/OPTIMIZATION_ROADMAP.md)
(the v1.0 "rewrite the hot path in a compiled language" line).

> **Status:** v0.0.1. Lexes + parses the subset in
> [`docs/compiler/ZIG_FRONTEND.md`](../../docs/compiler/ZIG_FRONTEND.md). It does
> **not** type-check or lower — the Python `vakedc` remains the reference
> implementation. See the PR follow-up for the road to parity.
>
> **Validation note:** this code was authored in an environment without a Zig
> toolchain, so it has **not been compiled here**. Run the steps below (after
> `scripts/setup-zig.sh`) to build and test it; `zig build test` is the
> acceptance gate.

## Build & test

```bash
# 1. Install the pinned toolchain (Zig 0.13.0) — idempotent:
../../scripts/setup-zig.sh

# 2. From this directory (zig/vakedc):
zig build test                                   # run lexer + parser unit tests
zig build                                        # produce zig-out/bin/vakedc-zig
zig build run -- parse ../../vaked/examples/swe-swarm-loadtest.vaked
zig build run -- parse ../../vaked/examples/swe-swarm-loadtest.vaked --json
```

Expected (the 8-worker example has 1 import, 1 runtime decl, and 16 mesh edges):

```
vakedc-zig: parsed …/swe-swarm-loadtest.vaked OK — 1 import(s), 1 declaration(s), 16 edge(s), N tokens
```

## Layout

| File | Purpose |
|------|---------|
| `src/lexer.zig` | UTF-8 → flat token list; comments/whitespace stripped; tests |
| `src/parser.zig` | recursive-descent parser → AST; `summarize()`; tests |
| `src/main.zig` | CLI (`parse <file> [--json]`); aggregates the tests |
| `build.zig` / `build.zig.zon` | build (pinned to Zig 0.13.0) |

## Cross-checking against the reference

`vakedc-zig parse` should accept exactly the files the Python reference parses
within the subset. To dogfood:

```bash
python3 -m vakedc parse vaked/examples/swe-swarm-loadtest.vaked   # reference
zig build run -- parse ../../vaked/examples/swe-swarm-loadtest.vaked  # this
```

Both should succeed. Divergences are bugs in this front-end (or, occasionally,
a documented subset boundary — see the design note).
