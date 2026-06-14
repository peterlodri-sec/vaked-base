# ailish — AI-lish V1 runtime

A `nom`-based parser, register-monad guardrail, and idempotent formatter for
**AI-lish V1**, the lowerable agent execution-graph protocol
([RFC](../docs/ailish/2026-06-14-ailish-v1-rfc.md)).

AI-lish V1 is the IR an agent emits to make its reasoning, tool use, and side
effects machine-traceable: SSA registers (`%N`), typed atoms, explicit dataflow
(`→`) and justification (`∵`) edges, per-register structural rules, and a
token-compaction layer.

## What this crate implements

| RFC phase | Module | Summary |
|-----------|--------|---------|
| **B — parser** | `src/parser.rs`, `src/ast.rs`, `src/lib.rs` | `nom` parser → typed `Message`/`Frame`/`Line` AST. Accepts both long (`combine(%1,%2)`) and compact (`&(%1,%2)`) forms under one grammar. |
| **B — guardrail** | `src/guardrail.rs` | Enforces the §3 register monads and the **freeze invariant**: a live `gate(*:fail)` freezes every `R:commit` line pending human override. |
| **C — formatter** | `src/fmt.rs`, `src/bin/ailishfmt.rs` | `ailishfmt`, an idempotent formatter that renders long or compact (RFC §5 map). |
| **C — compaction** | `src/fmt.rs`, `src/bin/tokenbench.rs` | The §5 long↔compact map + a tokens-per-frame benchmark. |

## Usage

```rust
use ailish::{parse_message, guardrail_check, format_message, EXAMPLE_V1};

let msg = parse_message(EXAMPLE_V1).unwrap();
let report = guardrail_check(&msg);
assert!(report.ok());        // no §3 violations
assert!(report.frozen);      // gate(commit:fail) live → R:commit frozen

let compact = format_message(EXAMPLE_V1, true).unwrap();   // RFC §5 compact form
```

Binaries:

```
cargo run --bin ailishfmt -- --compact frame.ail   # reformat (long default; --compact)
cargo run --bin ailish-tokenbench                  # long vs compact, RFC §4 example
```

## Build & test

Per the repository build policy, this crate is built and tested on GitHub
Actions (`.github/workflows/ailish-ci.yml`), not on a developer machine. Locally,
`cargo fmt -- --check` and `cargo clippy` (lint/type-check only) are used to
validate the source.

```
cargo fmt -- --check
cargo clippy --all-targets -- -D warnings
cargo test --all-targets        # runs on CI
```

## Conformance notes

See [`DEVIATIONS.md`](DEVIATIONS.md) for where the implementation deviates from a
strict reading of the RFC §2 EBNF — chiefly because the EBNF and the §4 example
contradict each other, and the parser accepts the superset needed to parse the
example.
