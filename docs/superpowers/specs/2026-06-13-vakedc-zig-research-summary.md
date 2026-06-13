# vakedc-zig: Research & Architecture Summary

**Date**: 2026-06-13  
**Authors**: Claude Code (fan-out research)  
**Branch**: `claude/zig-vaked-compiler-parser-ahmm23`

---

## Executive Summary

We bootstrapped a **Zig-based Vaked compiler** (vakedc-zig) targeting **complete feature parity** with the existing Python reference implementation (vakedc). The compiler implements the parse → check → lower pipeline for Vaked, a flake-native capability-graph language.

**Key architectural decisions**:

1. **Three-phase rollout**: (1) Lexer + Parser + LPG→JSON, (2) Type checker + lowering, (3) LSP + dogfeeding
2. **Stdlib-only**: No external dependencies (embedded deployment in Zig daemons)
3. **Determinism first**: Byte-identical JSON output across runs (test oracle: compare to Python reference)
4. **Span fidelity**: Exact source byte offsets from lexer → provenance (error attribution)
5. **Ralph loop integration**: `-ralphloop-cache` as a native memory primitive (decision closure)

---

## 1. Fan-Out Research: Reference Implementation (vakedc)

### 1.1 Architecture Overview

**vakedc** is a **four-stage pipeline** (Python, stdlib-only):

```
Source file
    ↓
[Stage 1: Lexer] → Token stream (with byte spans, NFC-validated)
    ↓
[Stage 2: Parser] → AST (recursive descent, PEG-ordered soft keywords)
    ↓
[Stage 3: Resolver] → Labeled Property Graph (nodes + edges, stable IDs)
    ↓
[Stage 4: Type Checker] → Diagnostics (0011 type system: conformance, constraints, capabilities)
    ↓
[Lowering: 18+ emitters] → Artifacts (flake.nix, zig configs, catalogs, provenance.json)
```

### 1.2 Lexer Characteristics

| Aspect | Detail |
|--------|--------|
| **Input** | UTF-8 source with NFC validation (Unicode 15.1.0 pinned) |
| **Tokens** | IDENT, STRING (w/ `${ref}` interpolation), NUMBER, DURATION, BYTES, PATH, REGEX, operators, NEWLINE, EOF |
| **Newline semantics** | Suppressed inside `()`, `[]`, `{}` (group depth tracking); emitted at depth 0 |
| **Regex mode** | Lexer state machine: `/…/` only after `matches` keyword |
| **Comments** | `#` to EOL stripped before tokenization |
| **Span metadata** | Every token carries `(byteStart, byteEnd, line, col)` |

**Key insight**: Group-aware newline suppression is crucial for correctly parsing multi-line expressions and field lists.

### 1.3 Parser Characteristics

| Aspect | Detail |
|--------|--------|
| **Algorithm** | Hand-written recursive descent (PEG-ordered per grammar v0.3) |
| **Soft keywords** | `field`, `grant`, `order`, `open` self-disambiguate via lookahead (2nd token) |
| **Newline semantics** | Statements terminate on NEWLINE (outside groups); `grant`/`order` lists are line-bounded |
| **Declaration kinds** | 28 total (runtime, engine, host, network, fiber, stream, index, …) |
| **Expression forms** | Literals, lists, records, apps (ref + optional args + optional record) |
| **Types** | Parsed (not checked in v0.2): type unions, parameterized types, function types |

**Key insight**: Soft-keyword dispatch using lookahead avoids ambiguity while keeping grammar small.

### 1.4 Graph & Resolver

| Aspect | Detail |
|--------|--------|
| **Node ID** | Stable, path-derived: `<filename>#<path/chain>` (e.g., `op.vaked#fiber/reader/input`) |
| **Provenance** | `Provenance(file, decl, Span)` attached at instantiation (byte-exact) |
| **Symbol table** | Lexically-scoped; ref resolution post-parse (worklist for forward refs) |
| **Edge labels** | `contains` (nesting), `imports` (use), `depends_on` (refs), `requires_capability`, `routes_to` (mesh DAG), `member_of` (parallel group) |
| **External stubs** | One per unresolvable dotted path: `external:<head-path>` |
| **Determinism** | Nodes + edges sorted by ID before emission |

**Key insight**: Stable node IDs enable deterministic, reproducible compilation (same input → same output regardless of host/order).

### 1.5 Lowering (0012 Pipeline)

| Aspect | Detail |
|--------|--------|
| **Purity** | No IO, clock, or randomness; pure functions per target |
| **Targets** | 18+ emitters (nix.spine, zig.daemoncfg, catalog.jsonl, crabcc.index, otp.supervision, ebpf.policy, …) |
| **Provenance** | Per-artifact `ProvEntry` with `inputsHash` (sha256 of canonical projection JSON) |
| **Deferred machinery** | Placeholder slots for future targets (surface launcher, otel.config) emit inert no-ops |
| **Contract** | Rejects lowering if checker reports *any* diagnostic (0012 §1) |

**Key insight**: Deterministic per-artifact hashing ensures reproducibility; deferred machinery keeps earlier fixtures byte-identical.

### 1.6 Test Verification

The Python reference includes **comprehensive test oracle**:

- **Differential oracle** (parser): All 15 examples → compare token streams + AST + graph JSON
- **Checker tests**: Catalog self-validates; conformant.vaked → 0 diagnostics; rejected.vaked → exactly 3 documented codes
- **Lowering tests**: operator-field.vaked lowers byte-identically to committed fixture tree
- **Determinism check**: Two runs of same file → identical bytes (every JSON key order, every hash value)

**Acceptance criterion for vakedc-zig**: Phase 1 passes oracle test (JSON output matches Python byte-for-byte on all 15 examples).

---

## 2. Design Decisions: Zig Implementation

### 2.1 Why Zig?

1. **Embedded in daemons**: Zig compiles to standalone binaries with no GC/runtime → can be linked into Zig enforcement daemons for stateless, hot-reloadable config parsing
2. **Determinism**: Zig stdlib provides predictable JSON serialization (no floating-point surprises)
3. **Span fidelity**: Manual memory management makes byte-exact provenance tracking straightforward
4. **No external deps**: Stdlib-only (matching vaked's philosophy: minimal dependencies, reproducible builds)

### 2.2 Architecture Mapping

**vakedc (Python) → vakedc-zig (Zig)**:

| Python Module | Zig Module | Responsibility |
|---------------|-----------|-----------------|
| `lexer.py` | `lexer.zig` | UTF-8 → tokens (NFC validation, group tracking, newline suppression) |
| `parser.py` | `parser.zig` | Tokens → AST (recursive descent, soft-keyword dispatch) |
| `graph.py` | `graph.zig` | Node/edge structures + serialization |
| `resolve.py` | `resolver.zig` | Symbol table + ref resolution + edge emission |
| `emit.py` | `emit.zig` | LPG → canonical JSON (stable key order) |
| `check.py` | `check.zig` (Phase 2) | 0011 type checker (conformance, constraints, capabilities) |
| `lower.py` | `lower.zig` (Phase 2) | Lowering pipeline + per-target emitters |
| `__main__.py` | `main.zig` | CLI (parse, check, lower, lsp subcommands) |

### 2.3 Phase Breakdown

**Phase 1 (this sprint)**: Parser → JSON
- **Goal**: `vakedc-zig parse file.vaked --print` outputs byte-identical JSON to Python
- **Tests**: All 15 examples parse; JSON oracle passes; determinism verified
- **Deliverable**: Lexer + Parser + Graph + Emit (no checker, no lowering)

**Phase 2 (next sprint)**: Checker + Lowering
- **Goal**: `check` and `lower` subcommands produce diagnostics and artifacts matching Python
- **Acceptance**: operator-field.vaked lowers to byte-identical flake.nix + gen/ tree

**Phase 3 (future)**: LSP + Dogfeeding
- **Goal**: IDE integration + vakedos self-describes in Vaked
- **Closure**: ralph loop decisions fed into memory primitive; compiler describes the system that designed it

### 2.4 Ralph Loop Integration (`-ralphloop-cache`)

**Motivation**: The ralph decision loop (tools/ralph) iterates design tracks, recording decisions to an immutable log. A compiled Vaked declaration should cache and query those decisions.

**Semantics** (new memory primitive):

```vaked
memory ralphDecisions {
  source = ralph.decisions      # synthetic source: tools/ralph/state/events.jsonl
  schema = schema.decisionEntry  # built-in schema (track, verdict, cost, text, hash)
  mine = mempalace.ralphloop     # parallel.jq filter (transforms events → recall entries)
  scope = "track"
  retention = 30d
  emit = [catalog.jsonl, catalog.sqlite]
}
```

**Implementation** (Phase 2+):
1. Add `source ralph.decisions` to built-in sources
2. Lowering: `sources.ralph.decisions` → read `tools/ralph/state/events.jsonl` → materialize decision entries
3. `mine` filter: transform event log into recall-searchable fields (track, timestamp, decision_id, verdict, cost)
4. Emit: `gen/memory/ralphDecisions.sqlite` + `gen/catalog/ralphDecisions.jsonl`

**Why native?**
- Closure: compiler describes itself (decisions that shaped the language)
- Testability: decisions are version-controlled + replayable
- Feedback loop: language design ← ralph decisions ← compiler behavior ← deployed system

---

## 3. Implementation Strategy

### 3.1 File Organization

```
vakedc-zig/
├── build.zig                  # Zig build config (stdlib-only)
├── src/
│   ├── main.zig               # CLI entry point
│   ├── lexer.zig              # Tokenization
│   ├── parser.zig             # AST construction
│   ├── graph.zig              # LPG node/edge types
│   ├── resolver.zig           # Symbol table + ref resolution
│   ├── emit.zig               # Canonical JSON
│   ├── check.zig              # Type checker (Phase 2)
│   ├── lower.zig              # Lowering pipeline (Phase 2)
│   ├── catalog.zig            # Builtins loader (Phase 2)
│   └── emitters/              # Per-target emitters (Phase 2)
├── tests/
│   ├── test_lexer.zig
│   ├── test_parser.zig
│   ├── test_graph.zig
│   └── golden/                # Reference JSON snapshots
└── README.md
```

### 3.2 Zig Idioms

**Memory management**: Use `std.mem.Allocator` throughout (passed as parameter).

**Determinism**: StringHashMaps must be **sorted before emission** (Zig's hash iteration order is non-deterministic).

**Error handling**: Bubble errors up with `!` syntax; avoid silent failures (wrap in try-catch at CLI boundary).

**Testing**: Use `std.testing.expect`, `std.testing.expectEqual` for assertions; integration tests read files and compare output.

---

## 4. Success Criteria

### Phase 1 Acceptance

- ✅ `zig build` produces `vakedc-zig` binary (no compiler errors)
- ✅ All 15 `vaked/examples/` files parse without errors
- ✅ JSON output byte-identical to Python reference (oracle test passes)
- ✅ Provenance spans are exact (lexer token positions → graph nodes)
- ✅ Determinism verified: two runs of same file = identical bytes
- ✅ Unit tests pass (lexer, parser, graph, emit)
- ✅ Integration test passes: all 15 examples + oracle comparison

### Phase 2 Acceptance

- ✅ `check` diagnostics match Python reference (same codes + line numbers)
- ✅ `lower` artifacts byte-identical (flake.nix, gen/, provenance.json)
- ✅ Lowering refuses on any diagnostic (0012 §1 contract)

### Phase 3 Acceptance

- ✅ LSP server operational (hover, completion, diagnostics)
- ✅ vakedos.vaked compiles → deployable to bare-metal EPYC 4345P
- ✅ Ralph loop integration working (decisions cached + queryable)

---

## 5. Known Deferred Decisions

(See vakedc/README.md §Checker — Deferrals for reference)

### Parser (Phase 1)

- ✅ Type syntax is parsed (not checked; deferred to Phase 2)
- ✅ Schema + capability declarations are parsed (not validated; deferred to Phase 2)
- ✅ All 28 declaration kinds and expression forms covered by EBNF

### Checker (Phase 2)

- **Use-check deferred** (0011 §4.3): Requires catalog metadata (`uses` annotations); Phase 2 will implement
- **mediaPipeline stage-record conformance deferred**: Stages are open-typed; Phase 2 will wire into nested conformance
- **User override REPLACES builtin** (pinned decision): In-file `schema <kind>` / `capability <domain>` fully replace builtins (no merge)

### Lowering (Phase 2+)

- **Deferred machinery** (0012 §7): Placeholder slots for surface launcher, otel.config, ebpf.policy (emit inert no-ops until implementation)

---

## 6. Dogfeeding Loop

**Once lowering is complete**:

```
1. Write vakedos.vaked (complete host declaration in Vaked)
   ↓
2. vakedc-zig lower vakedos.vaked --out /tmp/vakedos
   ↓
3. Generated artifacts:
   - gen/zig/*.json (daemon configs for sandboxd, policyd, etc.)
   - gen/otp/*_sup.erl (supervision tree)
   - gen/colmena/hive.nix (deployment config)
   ↓
4. Deploy: nixos-rebuild switch --flake /tmp/vakedos
   ↓
5. Observe running system:
   - eBPF policy enforcement (eBPF kernel evidence)
   - OTel traces (daemon communication)
   - Decision log updates (ralph loop)
   ↓
6. Feed back: decisions → tools/ralph/state/events.jsonl
   ↓
7. Compiler caches decisions: memory ralphDecisions
   ↓
8. LOOP CLOSES: system describes itself in Vaked
```

---

## 7. References

**Normative**:
- Grammar: `vaked/grammar/vaked-v0-plus.ebnf`
- Type system: `docs/language/0011-type-system.md`
- Lowering: `docs/language/0012-lowering.md`
- Reference impl: `vakedc/README.md`

**Specifications** (this session):
- Design: `docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md`
- Phase 1 plan: `docs/superpowers/plans/2026-06-13-vakedc-zig-phase-1.md`
- Research summary: (this file)

**Examples**:
- `vaked/examples/primitives/*.vaked` (15 files, all must parse)
- `vaked/examples/lowering/` (golden fixture tree from operator-field.vaked)

**Ralph loop**:
- `tools/ralph/README.md` (decision loop architecture)
- `tools/ralph/PURPOSE.md` (research goals)

---

## 8. Next Steps

### Immediate (within this session)

1. ✅ Create design specification (done)
2. ✅ Create Phase 1 implementation plan (done)
3. ✅ Bootstrap Zig project structure (done)
4. ✅ Create research summary (this document)
5. **Commit to branch** `claude/zig-vaked-compiler-parser-ahmm23`
6. **Create pull request** (ready for review)

### Phase 1 Implementation (next 2–3 days)

1. **Lexer** (~4 hours)
   - Implement `lexer.zig` with full tokenization logic
   - Test on small examples (string interpolation, durations, etc.)

2. **Parser** (~5 hours)
   - Implement `parser.zig` with PEG-ordered statement dispatch
   - Test on each declaration kind + expressions

3. **Graph & Resolver** (~3 hours)
   - Implement node instantiation + symbol table
   - Implement ref resolution + edge emission

4. **Emission + Testing** (~3 hours)
   - Implement canonical JSON with stable key order
   - Run oracle test (all 15 examples vs. Python reference)
   - Verify determinism

### Future Phases

- **Phase 2**: Type checker + lowering (following Phase 1 merge)
- **Phase 3**: LSP + dogfeeding vakedos.vaked (following Phase 2 merge)

---

**End of research summary.**
