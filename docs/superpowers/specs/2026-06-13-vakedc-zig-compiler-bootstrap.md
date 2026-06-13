# vakedc-zig: Zig-based Vaked Compiler Bootstrap

**Status**: Design phase  
**Target**: v0.1 (lexer + parser + LPG → JSON)  
**Branch**: `claude/zig-vaked-compiler-parser-ahmm23`

---

## 1. Overview

**vakedc-zig** is a **native Zig rewrite** of the reference Python compiler (`vakedc`), targeting:

1. **Phase 1** (this sprint): Lexer + Parser + LPG graph builder → canonical JSON (parity with `vakedc parse`)
2. **Phase 2** (next): Type checker + lowering (parity with `vakedc check` and `vakedc lower`)
3. **Phase 3** (future): LSP server + dogfeeding (vakedos self-describes in Vaked)

**Why Zig?**
- Vaked's enforcement layer is Zig daemons; the compiler must run *inside* those daemons for stateless, hot-reloadable config parsing.
- Standalone binary, no GC, no runtime; embeddable in a Zig program.
- Byte-exact provenance and deterministic JSON match the Python reference exactly (test oracle).

---

## 2. Architecture: Four-Stage Pipeline

### 2.1 Lexer (`src/lexer.zig`)

```
Input: UTF-8 source file
└─→ [NFC validation] → [tokenize with provenance] → [newline suppression in groups]
    └─→ Output: Token stream (kind, value, byteStart, byteEnd, line, col)
```

**Responsibility**: UTF-8 → tokens with exact byte spans.

| Token Kind | Lexed From | Metadata |
|------------|-----------|----------|
| `IDENT` | `[a-z][a-z0-9_-]*` or `[A-Z][a-z0-9_-]*` | plain ident or soft keyword (context determines) |
| `STRING` | `"…"` with `${ref}` interpolation | interpolation sites tracked |
| `NUMBER` | `[-]?[0-9]+[.][0-9]+?` or `[-]?[0-9]+` | float or int |
| `DURATION` | `[0-9]+[a-z]+` (`1m`, `90d`, etc.) | parsed literal with unit |
| `BYTES` | `[0-9]+[KMGT]?B` | sized quantity |
| `PATH` | `.` followed by `/` or letter | `.vaked/`, `./../`, etc. |
| `REGEX` | `/…/` (after `matches` keyword) | opaque body; parser rejects if not in `matches` context |
| `OP` | `{`, `}`, `[`, `]`, `(`, `)`, `,`, `;`, `:`, `"`, `=`, `?=`, `<`, `>`, `<=`, `>=`, `->`, `.`, `..`, `\|`, `@` | single operators and compound operators |
| `NEWLINE` | U+000A or U+000D U+000A | suppressed inside open `()` / `[]` / `{}`; tracks group depth |
| `EOF` | end of file | signals completion |

**Key properties**:
- **Unicode**: NFC-validate on read; pinned to Unicode 15.1.0 (version mismatch = warning to stderr, parse continues).
- **Group tracking**: `(`, `[`, `{` increment depth; `)`, `]`, `}` decrement; NEWLINE emitted only at depth 0.
- **Regex mode**: Lexer state-machine accepts `/regex/` only immediately after `matches` keyword; elsewhere `/` is an error (parse error, not lex error, to preserve recovery).
- **Interpolation**: `${ref}` inside STRING tracked separately; `ref` must be a valid dotted ident.
- **Comments**: `#` to EOL skipped during tokenization (not pre-stripped); preserves byte offsets for provenance.

---

### 2.2 Parser (`src/parser.zig`)

```
Input: Token stream
└─→ [recursive descent, PEG-ordered per grammar] → [soft-keyword dispatch]
    └─→ Output: AST (decls + imports) with source spans
```

**Responsibility**: Tokens → AST matching vaked v0.3 EBNF exactly.

**Key structures** (Zig types):
```zig
pub const Decl = struct {
    kind: []const u8,           // "fiber", "stream", "index", ...
    name: []const u8,           // decl name
    signature: ?Signature,      // optional typed parameters
    annotations: []Annotation,  // @tag or @tag(args)
    body: []Statement,          // statements inside { }
    span: Span,                 // byteStart, byteEnd, line, col
};

pub const Statement = union(enum) {
    field_decl: FieldDecl,
    grant_decl: GrantDecl,
    order_decl: OrderDecl,
    assignment: struct { name: []const u8, op: []const u8, expr: Expr },
    open_decl: void,
    inherit: struct { names: [][]const u8 },
    edge: Edge,
    node_decl: NodeDecl,
    nested_decl: Decl,
    app: App,
};

pub const Expr = union(enum) {
    literal: Literal,
    list: []Expr,
    record: []struct { name: []const u8, value: Expr },
    app: App,
};

pub const App = struct {
    ref: [][]const u8,           // dotted path: ["foo", "bar", "baz"]
    args: ?[]Expr,               // (arg1, arg2, ...)
    record: ?[]struct { name: []const u8, value: Expr },  // { key = val, ... }
};
```

**PEG-ordered statement dispatch** (soft keywords self-disambiguate):
1. Try `field_decl` (`field` IDENT `:` TYPE)
2. Try `grant_decl` (`grant` IDENT IDENT*)
3. Try `order_decl` (`order` order_chain)
4. Try `assignment` (IDENT assign_op EXPR)
5. Try `open_decl` (`open` at statement boundary, not followed by `=`)
6. Try `inherit_stmt` (`inherit` IDENT+)
7. Try `edge` (REF `->` REF+)
8. Try `node_decl` (`node` NAME BLOCK)
9. Try nested `decl`
10. Try `app` (REF optional-args optional-record)

**Newline semantics** (enforced by parser, not lexer):
- Statement ends at NEWLINE (when not inside open `()` / `[]` / `{}`).
- An `inherit`, `grant`, or `order` list is **line-bounded** (continues only on current line).
- A `;` inside an `order_decl` separates chains; chains may continue across newlines after `;`.

**Span convention** (0012 §6.2):
- `byteStart` = offset of leading keyword (e.g., `f` in `fiber`)
- `byteEnd` = exclusive (one past `}`)
- `line`, `col` = 1-based at `byteStart`

---

### 2.3 Graph Builder / Resolver (`src/graph.zig` + `src/resolver.zig`)

```
Input: AST (decls + imports)
└─→ [instantiate nodes] → [symbol table + forward refs]
    → [resolve all refs] → [emit edges]
    └─→ Output: LPG (nodes + edges) deterministically sorted
```

**Responsibility**: AST → Labeled Property Graph with stable node IDs and resolvable references.

**LPG structures** (Zig):
```zig
pub const GraphNode = struct {
    id: []const u8,             // stable: "<filename>#<path/chain>"
    kind: []const u8,           // "fiber", "stream", "index", ...
    name: []const u8,
    labels: [][]const u8,       // e.g., ["tagged", "parallel"]
    props: StringMap,           // arbitrary key-value properties
    provenance: ?Provenance,
};

pub const GraphEdge = struct {
    source: []const u8,         // from node id (JSON field: "from")
    target: []const u8,         // to node id (JSON field: "to")
    label: []const u8,          // "contains", "imports", "depends_on", ...
    props: StringMap,
};
```

**Canonical JSON mapping** (emit.zig):
```json
{
  "from": "<node-id>",    // source field
  "to": "<node-id>",      // target field
  "label": "contains",
  "props": {}
}
```

pub const Provenance = struct {
    file: []const u8,           // source filename
    decl: []const u8,           // "<kind> <name>"
    span: Span,
};
```

**Node ID derivation**:
```
Top-level:     "file.vaked#operator-field"
Nested:        "file.vaked#fiber/reader/input"
External stub: "external:crabcc.markdown"
```

**Symbol resolution**:
1. Pass 1: Register all declarations (top-level + nested) in scope chain.
2. Pass 2: Resolve all `ref` (dotted paths) to nodes or external stubs.
3. Pass 3: Emit edges:
   - `contains` (nesting)
   - `imports` (use statements)
   - `depends_on` (field/app refs)
   - `requires_capability` (capability lists)
   - `routes_to` (mesh edges `->`)
   - `member_of` (parallel group membership)

**Deterministic output**:
- Nodes sorted by ID.
- Edges sorted by `(source, target, label)`.

---

### 2.4 Emission (`src/emit.zig`)

```
Input: LPG (nodes + edges)
└─→ [canonical JSON with stable key order] → [UTF-8 output]
    └─→ Output: Byte-identical to vakedc reference
```

**Responsibility**: LPG → canonical JSON (stable, deterministic, byte-for-byte matching).

**Format** (per vakedc):
```json
{
  "nodes": [
    {
      "id": "file.vaked#decl",
      "kind": "fiber",
      "name": "reader",
      "labels": ["parallel", "stateless"],
      "props": { "input": "stream.data", "output": "index.results" },
      "provenance": {
        "file": "file.vaked",
        "decl": "fiber reader",
        "span": {
          "byteStart": 42,
          "byteEnd": 123,
          "line": 3,
          "col": 1
        }
      }
    }
  ],
  "edges": [
    {
      "from": "file.vaked#fiber",
      "to": "external:crabcc.markdown",
      "label": "depends_on",
      "props": {}
    }
  ]
}
```

**Key properties**:
- **Stable key order**: deterministic iteration (Zig's StringHashMap must be sorted on emit).
- **Numeric precision**: numbers as-is (no rounding).
- **Null handling**: omit `provenance` if null; include empty `props` / `labels` / `labels` arrays even if empty.

---

## 3. Future Extensions (Post-Phase 3, RFC Pending)

**Ralph loop integration** (speculative): Once Phase 2 lowering is complete, a future RFC will specify how the compiler can expose ralph decision loop output as a queryable memory primitive.

**Syntax** (grammar extension, filed as issue #NNN):

```vaked
memory ralphDecisions {
  source = ralph.decisions      # built-in source: ralph's event ledger
  schema = schema.decisionEntry
  mine = mempalace.ralphloop    # parallel.jq filter
  scope = "track"
  retention = 30d               # keep 30 days of decisions
  emit = [catalog.jsonl, catalog.sqlite]
}
```

**Semantics**:
- `source = ralph.decisions`: a synthetic source that reads `tools/ralph/state/events.jsonl` and materializes decision entries.
- `schema = schema.decisionEntry`: validates against a built-in schema (track, verdict, cost, text, timestamp, etc.).
- `mine = mempalace.ralphloop`: a parallel.jq filter that transforms the event into recall-searchable fields.
- Lowering emits `gen/memory/ralphDecisions.sqlite` (indexed by track + timestamp) and `gen/catalog/ralphDecisions.jsonl`.

**Built-in source registration** (`vaked/schema/builtins.vaked`):
```vaked
# ralph integration (implicit source, no user decl needed)
runtime {
  # … existing fields …
}

# Synthetic sources (built-in refs)
source ralph.decisions {
  # materializes tools/ralph/state/events.jsonl
  # each event → one memory entry (track, decision_id, verdict, cost, text, hash)
}
```

**Why native?**
1. Ralph decisions feed back into language design → compiler should dogfood them.
2. Closure: the compiler describes the system that generated it.
3. Testability: ralph-loop output can be cached, replayed, and version-controlled.

---

## 4. Phase Breakdown

### Phase 1: Parser → JSON (this sprint)

**Goal**: `vakedc-zig parse <file.vaked> --print` produces byte-identical JSON to Python `vakedc`.

| Task | Owner | Subsystem | Tests |
|------|-------|-----------|-------|
| Lexer + token stream | auto | `src/lexer.zig` | 15 examples + provenance oracle |
| Parser + AST | auto | `src/parser.zig` | diff vs ref parser on all 15 examples |
| Graph builder + resolver | auto | `src/graph.zig` + `src/resolver.zig` | golden JSON snapshot |
| Emit canonical JSON | auto | `src/emit.zig` | byte-for-byte vs vakedc |
| CLI + build | auto | `src/main.zig` + `build.zig` | integration tests |
| **Deliverable** | | `.vaked-zig/` directory structure | **all 15 examples parse + JSON matches** |

**Acceptance criteria**:
- `zig build` produces `vakedc-zig` binary.
- `./vakedc-zig parse vaked/examples/primitives/fiber.vaked --print` outputs JSON matching vakedc's output byte-for-byte.
- All 15 examples in `vaked/examples/` parse without errors.
- Provenance spans are byte-exact (matches lexer token positions).

---

### Phase 2: Type Checker + Lowering (next sprint)

**Goal**: `vakedc-zig check` and `vakedc-zig lower` parity with Python reference.

| Task | Subsystem | Purpose |
|------|-----------|---------|
| Catalog loader | `src/catalog.zig` | Parse `builtins.vaked` into schema + capability registry |
| Type checker | `src/check.zig` | 0011 stages 3–4 (conformance, constraints, capability attenuation) |
| Lowering registry | `src/lower.zig` | Per-target emitters (nix.spine, zig.daemoncfg, catalog.jsonl, …) |
| Emitters | `src/emitters/` | Pure functions per target (no IO) |
| Provenance manifest | `src/provenance.zig` | Per-artifact `inputsHash` derivation |
| CLI extensions | `src/main.zig` | `check` and `lower` subcommands |

**Acceptance criteria**:
- `./vakedc-zig check operator-field.vaked` produces zero diagnostics.
- `./vakedc-zig lower operator-field.vaked --out /tmp/test` emits byte-identical `flake.nix` and `gen/` tree to Python reference.
- All 15 examples lower without errors.

---

### Phase 3: LSP + Dogfeeding (later)

**Goal**: IDE integration + self-hosting (vakedos describes itself in Vaked).

| Task | Subsystem | Purpose |
|------|-----------|---------|
| LSP server | `src/lsp.zig` | 3.17 JSON-RPC over stdio (hover, completion, diagnostics) |
| Vakedos self-decl | `hosts/vakedos/vakedos.vaked` | Complete host declaration in Vaked (lowers to NixOS config) |
| Ralph integration | `docs/decisions/` | ralph-loop decisions recorded + dogfooded |

---

## 5. File Structure

```
vaked-base/
├── vakedc-zig/                   # NEW: Zig compiler
│   ├── build.zig                 # Zig build config
│   ├── src/
│   │   ├── main.zig              # CLI entry point
│   │   ├── lexer.zig             # Tokenization
│   │   ├── parser.zig            # Recursive descent parser
│   │   ├── graph.zig             # LPG node/edge structures
│   │   ├── resolver.zig          # Symbol table + ref resolution
│   │   ├── emit.zig              # Canonical JSON emission
│   │   ├── check.zig             # Type checker (Phase 2)
│   │   ├── lower.zig             # Lowering pipeline (Phase 2)
│   │   ├── catalog.zig           # Builtins loader (Phase 2)
│   │   ├── provenance.zig        # Provenance manifest (Phase 2)
│   │   ├── lsp.zig               # LSP server (Phase 3)
│   │   └── emitters/             # Target-specific emitters (Phase 2)
│   │       ├── nix.zig
│   │       ├── zig.zig
│   │       ├── catalog.zig
│   │       └── ...
│   ├── tests/
│   │   ├── test_lexer.zig
│   │   ├── test_parser.zig
│   │   ├── test_graph.zig
│   │   ├── test_emit.zig
│   │   └── golden/               # Reference JSON snapshots
│   │       └── *.json
│   └── README.md
├── vaked/
│   ├── grammar/vaked-v0-plus.ebnf   # (unchanged)
│   └── schema/
│       ├── builtins.vaked           # (add `source ralph.decisions`)
│       └── parallel-types.md        # (add `Memory<DecisionEntry>` type)
└── docs/
    ├── superpowers/specs/
    │   └── 2026-06-13-vakedc-zig-compiler-bootstrap.md  # (this file)
    └── superpowers/plans/
        └── 2026-06-13-vakedc-zig-phase-1.md  # Detailed Phase 1 implementation plan
```

---

## 6. Testing & Verification

### 6.1 Differential Oracle (Parser)

**Test harness**: `vakedc-zig/tests/test_oracle.zig`

For each `.vaked` file in `vaked/examples/`:
1. Run Python `vakedc parse --print > /tmp/ref.json`
2. Run `vakedc-zig parse --print > /tmp/zig.json`
3. Assert `diff /tmp/ref.json /tmp/zig.json` (byte-for-byte)

Failures include: token stream, AST structure, graph JSON, provenance spans.

### 6.2 Determinism Check

Run lowering twice on the same source; assert generated files are byte-identical (same `inputsHash` values, same key order in all JSON).

### 6.3 Dogfeeding Loop

```
vakedos.vaked (NixOS host declaration)
    ↓
vakedc-zig lower --out /tmp/vakedos
    ↓
gen/zig/*.json (daemon configs)
gen/otp/*_sup.erl (supervision tree)
gen/colmena/hive.nix (deployment config)
    ↓
[deployed to bare-metal EPYC 4345P]
    ↓
[observe eBPF policy enforcement + OTel traces]
    ↓
[feed observations back into docs/decisions/*ralph-log.md]
    ↓
ralph loop mines decisions → memory primitive
    ↓
[loop closes]
```

---

## 7. Success Criteria

**Phase 1 complete when**:
- ✅ All 15 examples parse without errors
- ✅ JSON output matches Python reference byte-for-byte
- ✅ Provenance spans are exact (lexer offsets + AST storage)
- ✅ PR review + merge to `main` (or integration branch)

**Phase 2 complete when**:
- ✅ `check` diagnostics match reference (same codes + counts)
- ✅ `lower` artifact tree matches reference byte-for-byte
- ✅ Determinism verified (two lowerings = identical bytes)

**Phase 3 complete when**:
- ✅ vakedos self-describes in Vaked
- ✅ Compilation + deployment succeeds
- ✅ ralph loop integrated + dogfeeding loop closes

---

## Appendix: Grammar Coverage (Phase 1)

The parser must handle all 28 declaration kinds + expressions + type syntax:

```
✓ runtime, engine, host, network, filesystem, mcp, ebpf
✓ budget, observability, runclass, workflow
✓ index, catalog, stream, fiber, surface, mesh, device, mediaPipeline, parallel
✓ schema, capability, service, secret, hostResource, ingress, container, memory

Expressions:
✓ Literals: string (with ${ref}), number, bool, path, duration, bytes, null
✓ List: [expr, expr, ...]
✓ Record: { key = val, ... }
✓ App: ref, ref(args), ref { record }, ref(args) { record }
✓ Ref: plain ident, dotted.path

Type syntax (parsed, not checked in Phase 1):
✓ type_atom: qualname [ < type, ... > ] | (type, ...) -> type
✓ union: type | type | type

v0.3 type layer (parsed, not checked in Phase 1):
✓ field_decl: field name : type { refinement, ... }
✓ grant_decl: grant name name ...
✓ order_decl: order name < name < ... ; name < name ...
✓ open_decl: open (bare statement)
```

---

## References

- **Grammar**: `vaked/grammar/vaked-v0-plus.ebnf`
- **Type system**: `docs/language/0011-type-system.md`
- **Lowering**: `docs/language/0012-lowering.md`
- **Reference**: `vakedc/README.md` (architecture summary)
- **Ralph loop**: `tools/ralph/README.md`, `tools/ralph/PURPOSE.md`
