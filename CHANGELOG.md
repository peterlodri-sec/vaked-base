# CHANGELOG

All notable changes to `vaked-base` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

## [0.1.0] — 2026-06-13 · *vakedc-zig: first Zig compiler-parser*

### Added

#### `zig/vakedc/` — vakedc-zig v0.1.0 (PR [#118](https://github.com/peterlodri-sec/vaked-base/pull/118))

Zig-native parse stage: `source bytes → lexer → parser → JSON AST`.

| File | What |
|------|------|
| `src/lexer.zig` | UTF-8 tokenizer; NEWLINE suppression inside `()`/`[]`; duration/bytes units; path/regex soft-keyword detection |
| `src/ast.zig` | Tagged union AST mirroring EBNF v0.3 grammar; JSON serializer compatible with Python `vakedc parse` output |
| `src/parser.zig` | Recursive descent following EBNF verbatim; 28 kind keywords via `std.StaticStringMap`; `peekNonNl` for newline-tolerant lookahead |
| `src/cache.zig` | ralphloop-cache: SHA-256 content-addressed objects + hash-chained JSONL index (same ledger shape as `tools/ralph/state/events.jsonl`) |
| `src/main.zig` | CLI dispatcher; arena allocation; `--version`, `--cache-dir`, `--no-cache` flags; non-fatal cache write warnings |
| `build.zig` | Zig 0.16+ build; `-Dversion`, `-Dstrip`; `build_options` comptime version embedding |
| `build.zig.zon` | Package manifest; `.fingerprint` for Zig 0.16; stdlib-only, no external deps |

**Type-safety hardening** (10 improvements in a single commit):

1. `Span.valid()` — monotonicity predicate (`byte_end >= byte_start`)
2. `@sizeOf(Span) == 16` comptime assert — no hidden padding
3. Exhaustiveness guards — comptime assert union fields match tag enum fields for `Expr`, `Refinement`, `Stmt`, `Item`
4. `LITERAL_KIND_STRS` — `std.enums.EnumArray(LiteralKind, []const u8)` replaces switch in `writeJsonLiteral`
5. `CMP_OP_STRS` — same for `CmpOp` → JSON operator strings
6. `TOKEN_KIND_NAMES` — `pub EnumArray` in lexer; exhaustive debug-name table
7. `MAX_REF_PARTS = 64` — bounds guard in `parseRef` against pathological input
8. GPA leak-detection test — parse pipeline through `GeneralPurposeAllocator(.{.safety=true})`
9. `Span.valid` + EnumArray coverage tests
10. `comptime TOKEN_KIND_NAMES.len == fields(TokenKind).len` assertion

**ralphloop-cache primitive** ([issue #114](https://github.com/peterlodri-sec/vaked-base/issues/114)):

- Content-addressed object store: `.vaked/cache/objects/<sha256-hex>`
- Hash-chained JSONL ledger: `.vaked/cache/parse.index.jsonl`
- Same event-log shape as `tools/ralph/state/events.jsonl`; provenance chain is continuous

#### `vaked/examples/compiler/`

| File | What |
|------|------|
| `vakedc-zig.vaked` | Dogfeed: the compiler pipeline expressed in Vaked (`fiber parse`, `fiber check`, `fiber lower`, `parallel "vakedc-pipeline"`) with `# gap:` annotations at two unresolved language points |
| `ralphloop-cache.vaked` | Isolated ralphloop-cache pattern as a standalone Vaked example |

#### `docs/language/0018-zig-compiler-design.md`

Design note: motivation, v0.1.0 scope, ralphloop-cache spec (layout, entry format, semantics, provenance chain), dogfeed loop gaps, architecture, JSON AST schema.

#### `docs/language/0017-ralphloop-cache.md`

Folded into this PR: ralphloop primitive proposal + parity roadmap.

#### `flake.nix` additions

- `packages.vakedc-zig` — `nix build .#vakedc-zig` (ReleaseSafe + tests + `zig build test`)
- `packages.vakedc-zig-static` — `nix build .#vakedc-zig-static` (ReleaseSmall + musl + stripped)

#### `.github/workflows/spec-tests.yml` additions

- `zig-build` CI job: `nix build .#vakedc-zig` + `zig build test` + smoke-parse of the dogfeed example

#### `docs/README/`

Session documentation: development chronicle, attribution, graph of the 2-hour build session (see [`docs/README/README.md`](docs/README/README.md)).

### Language gaps surfaced by the dogfeed loop

Both filed before implementation (project convention §2 — grammar before code):

- **[#114](https://github.com/peterlodri-sec/vaked-base/issues/114)** — `memory` kind is runtime-only; no build-time cache/scope variant exists for compile-time `ralphloop-cache`
- **[#115](https://github.com/peterlodri-sec/vaked-base/issues/115)** — `parallel … strategy = "supervised-dag"` targets runtime fibers under OTP; sequential compiler pipelines need a `strategy = "sequential"` variant or a first-class `pipeline` kind

### Zig version compatibility

nixpkgs-unstable shipped **Zig 0.16.0** during this PR cycle (three CI iterations):

| Iteration | Failure | Fix |
|-----------|---------|-----|
| 1 | `.name` must be enum literal | `.name = .@"vakedc-zig"` |
| 2 | Enum literal must be bare identifier (no hyphens) | `.name = .vakedc_zig` |
| 3 | Missing `.fingerprint` field | Added `0xe7dc41570c90531d` |
| 4 | `root_source_file` renamed to `root` in Zig 0.16 | Updated `build.zig` |

### Co-development attribution

This release was produced in a single interactive session:

```
Session:   https://claude.ai/code/session_01VpDTz2ngK38i9PZUjrZ6BK
Initiated: peterlodri-sec <cabotage@protonmail.com>
Author:    Claude (claude-sonnet-4-6) via Anthropic
Branch:    claude/zig-vaked-compiler-parser-u3es8b
Date:      2026-06-13
```

**peterlodri-sec** directed the design, reviewed each CI iteration, approved the
type-system additions, and owns all artifacts pushed to this repository.
**Claude (claude-sonnet-4-6)** acted as code author and orchestrator — proposing
architecture, writing all Zig source, iterating on CI failures, and writing this
document.

To independently verify: every commit on branch `claude/zig-vaked-compiler-parser-u3es8b`
references the session URL; the git log is the tamper-evident record of the co-development.

```
Signed-off-by: Claude (claude-sonnet-4-6) via Anthropic <noreply@anthropic.com>
Attested-by:   peterlodri-sec <cabotage@protonmail.com>
```

---

*Previous entries will be backfilled as the v0.1 backlog matures.*
