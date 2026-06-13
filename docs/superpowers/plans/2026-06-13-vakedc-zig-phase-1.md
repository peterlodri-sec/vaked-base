# Phase 1 Implementation Plan: vakedc-zig Parser → JSON

**Duration**: ~2–3 days (6–9 focused hours)  
**Outcome**: Parser outputs byte-identical JSON to Python reference  
**Acceptance**: All 15 examples parse + oracle test passes

---

## 1. Setup: Zig Project Structure

### 1.1 Create Project Directory

```bash
cd /home/user/vaked-base
mkdir -p vakedc-zig/{src,tests/golden}
```

### 1.2 Zig Build Config (`vakedc-zig/build.zig`)

A minimal Zig build that:
- Produces `vakedc-zig` binary
- Links no external deps (stdlib only)
- Enables tests
- Generates deterministic output

### 1.3 Main Entry Point (`vakedc-zig/src/main.zig`)

CLI handler:
```
vakedc-zig parse <file.vaked> [--print]
```

Reads source → lexer → parser → graph → emit → JSON.

---

## 2. Lexer (`src/lexer.zig`) — 4 hours

### 2.1 Token Types & Structures

```zig
pub const TokenKind = enum {
    IDENT,
    STRING,
    NUMBER,
    DURATION,
    BYTES,
    PATH,
    REGEX,
    // Operators
    LBRACE, RBRACE,            // { }
    LBRACKET, RBRACKET,        // [ ]
    LPAREN, RPAREN,            // ( )
    COLON, COMMA, SEMICOLON,   // : , ;
    DOT, DOUBLEDOT,            // . ..
    PIPE,                       // |
    AT,                         // @
    ARROW,                      // ->
    ASSIGN, QASSIGN,           // = ?=
    LT, GT, LTE, GTE,          // < > <= >=
    NEWLINE,
    EOF,
    ERROR,
};

pub const Token = struct {
    kind: TokenKind,
    value: []const u8,         // raw text (for IDENT, STRING, NUMBER, etc.)
    byteStart: u32,            // offset in source
    byteEnd: u32,              // exclusive
    line: u32,                 // 1-based
    col: u32,                  // 1-based
};

pub const Lexer = struct {
    source: []const u8,
    pos: usize,                // current byte offset
    line: u32,
    col: u32,
    depth: usize,              // group nesting: ( [ { count
    tokens: []Token,
};
```

### 2.2 Unicode NFC Validation

On input, validate that source is NFC-normalized (Canonical Composition). Zig stdlib has `std.unicode.utf8ValidateSlice`; use it for sanity check. (Full NFC validation is complex; for MVP, warn if any combining marks detected and proceed.)

### 2.3 Tokenization Loops

**Main loop**:
```zig
fn nextToken(self: *Lexer) !Token {
    self.skipWhitespace();
    if (self.pos >= self.source.len) return Token{ .kind = EOF, ... };
    
    const ch = self.source[self.pos];
    
    return switch (ch) {
        '{' => self.tok1(LBRACE),
        '}' => self.tok1(RBRACE),
        // ... single-char ops
        '"' => self.lexString(),
        '#' => { self.skipComment(); return self.nextToken(); }
        '\n', '\r' => self.lexNewline(),
        '0'...'9' => self.lexNumber(),
        'a'...'z', 'A'...'Z', '_' => self.lexIdent(),
        '.' => self.lexPath(),
        else => error.UnexpectedChar,
    };
}
```

**String interpolation** (`${ref}`):
- Lexer mode: inside STRING, on `$`, emit STRING up to `$`, then parse IDENT chain inside `{}`, then resume STRING.
- Simpler approach: lexer emits STRING token with full value including `${}`; parser extracts interpolation sites.

**Regex mode** (after `matches`):
- Lexer maintains state; parser signals "expect REGEX" after `matches` keyword.
- Alternative: parser re-tokens the string `/…/` when it sees `matches`; simpler.

**Newline handling**:
- Increment `depth` on `{`, `[`, `(`.
- Decrement on `}`, `]`, `)`.
- Emit NEWLINE token only at depth == 0.
- Suppress NEWLINE inside groups (consumed silently).

### 2.4 Test: Token Stream

Test on one small example (e.g., `fiber.vaked`):
```bash
vakedc-zig lex vaked/examples/primitives/fiber.vaked
```
Output token stream (plain-text). Manually compare to vakedc output (if available, or write a small reference parser).

---

## 3. Parser (`src/parser.zig`) — 5 hours

### 3.1 AST Types

```zig
pub const Decl = struct {
    kind: []const u8,
    name: []const u8,
    annotations: []Annotation,
    signature: ?Signature,
    body: ?[]Statement,
    span: Span,
};

pub const Statement = union(enum) {
    field_decl: FieldDecl,
    grant_decl: GrantDecl,
    order_decl: OrderDecl,
    assignment: struct { name: []const u8, op: []const u8, expr: Expr },
    open_decl: void,
    inherit: struct { names: [][]const u8 },
    edge: Edge,
    node_decl: struct { name: []const u8, body: []Statement },
    decl: Decl,
    app: App,
};

pub const Expr = union(enum) {
    literal: Literal,
    list: []Expr,
    record: []struct { name: []const u8, value: Expr },
    app: App,
};

pub const App = struct {
    ref: [][]const u8,       // e.g., ["crabcc", "markdown"]
    args: ?[]Expr,
    record: ?[]AssignmentExpr,
};
```

### 3.2 PEG-Ordered Statement Dispatch

**Order matters**:

```zig
fn parseStatement(p: *Parser) !Statement {
    if (try p.tryParseFieldDecl()) |fd| return Statement{ .field_decl = fd };
    if (try p.tryParseGrantDecl()) |gd| return Statement{ .grant_decl = gd };
    if (try p.tryParseOrderDecl()) |od| return Statement{ .order_decl = od };
    if (try p.tryParseAssignment()) |a| return Statement{ .assignment = a };
    if (try p.tryParseOpenDecl()) |od| return Statement{ .open_decl = od };
    if (try p.tryParseInherit()) |i| return Statement{ .inherit = i };
    if (try p.tryParseEdge()) |e| return Statement{ .edge = e };
    if (try p.tryParseNodeDecl()) |nd| return Statement{ .node_decl = nd };
    if (try p.tryParseDecl()) |d| return Statement{ .decl = d };
    if (try p.tryParseApp()) |a| return Statement{ .app = a };
    return error.UnexpectedToken;
}
```

Each `tryParseX` checks leading tokens (lookahead) and either:
- Parses successfully and advances cursor, OR
- Resets cursor and returns null (backtrack on failure).

### 3.3 Soft Keyword Detection

**`field`**: lookahead = IDENT `:` → field_decl  
**`grant`**: lookahead = IDENT (IDENT)* → grant_decl  
**`order`**: lookahead = IDENT `<` IDENT → order_decl  
**`open`**: no `=` after → open_decl; `open =` → assignment  

### 3.4 Key Parser Functions

**Block parsing**:
```zig
fn parseBlock(p: *Parser) ![]*Statement {
    p.expect(LBRACE);
    var stmts = ArrayList(Statement).init(p.alloc);
    
    while (!p.check(RBRACE) and !p.check(EOF)) {
        try stmts.append(try p.parseStatement());
        p.skipNewlines();
    }
    
    p.expect(RBRACE);
    return stmts.items;
}
```

**Ref parsing**:
```zig
fn parseRef(p: *Parser) ![][]const u8 {
    var parts = ArrayList([]const u8).init(p.alloc);
    try parts.append(p.expect(IDENT).value);
    
    while (p.check(DOT)) {
        p.advance();
        try parts.append(p.expect(IDENT).value);
    }
    
    return parts.items;
}
```

**Expr parsing** (recursive, app is the primary rule):
```zig
fn parseExpr(p: *Parser) !Expr {
    return switch (p.peek().kind) {
        // Literals
        STRING => Expr{ .literal = ... },
        NUMBER => Expr{ .literal = ... },
        // Collections
        LBRACKET => Expr{ .list = try p.parseList() },
        LBRACE => Expr{ .record = try p.parseRecord() },
        // Ref/app
        IDENT => Expr{ .app = try p.parseApp(try p.parseRef()) },
        else => error.UnexpectedExpr,
    };
}
```

### 3.5 Newline Awareness

After each statement, parser expects a NEWLINE (or EOF, or RBRACE). Soft error if missing (recovery: continue).

### 3.6 Test: AST Output

```bash
vakedc-zig parse --ast fiber.vaked
```

Emit AST as pretty JSON (for debugging). Not part of final output, but helps verify parser correctness.

---

## 4. Graph Builder & Resolver (`src/graph.zig` + `src/resolver.zig`) — 3 hours

### 4.1 Node Instantiation

For each top-level `Decl` (and nested decls), create a `GraphNode`:
- **ID derivation**: `"<filename>#<path/chain>"`
- **Provenance**: file, decl string, span

```zig
fn instantiateNode(
    self: *GraphBuilder,
    decl: *const Decl,
    scope: [][]const u8,  // path/chain
) !GraphNode {
    var node_id = ArrayList(u8).init(self.alloc);
    try node_id.appendSlice(getBasename(self.source_file));
    try node_id.appendSlice("#");
    for (scope, 0..) |part, i| {
        if (i > 0) try node_id.appendSlice("/");
        try node_id.appendSlice(part);
    }
    
    return GraphNode{
        .id = node_id.items,
        .kind = decl.kind,
        .name = decl.name,
        .labels = try extractLabels(decl),  // e.g., from annotations
        .props = try extractProps(decl),    // e.g., from body assignments
        .provenance = Provenance{
            .file = self.source_file,
            .decl = try std.fmt.allocPrint(self.alloc, "{s} {s}", .{ decl.kind, decl.name }),
            .span = decl.span,
        },
    };
}
```

### 4.2 Symbol Table

```zig
pub const SymbolTable = struct {
    scope_stack: ArrayList(StringHashMap(*GraphNode)),
    external_stubs: StringHashMap(*GraphNode),
    
    fn resolve(self: *SymbolTable, ref: [][]const u8) !?*GraphNode {
        // Try local scopes first (innermost to outermost)
        // Then try external stubs
        // Return null if unresolvable
    }
};
```

**Resolution strategy**:
1. Pass 1: Declare all top-level + nested nodes.
2. Pass 2: Resolve refs in decls + statements.
3. Create external stub for each unresolvable ref.

### 4.3 Edge Emission

For each statement/field/ref in a decl body:
- Emit `depends_on` edge (ref → resolved node or external stub)
- Emit `contains` edge (parent → child for nested decls)
- Emit `routes_to` for mesh edges
- Emit `requires_capability` for capability lists

```zig
fn emitEdgesForDecl(self: *GraphBuilder, parent_id: []const u8, stmt: *const Statement) !void {
    switch (stmt.*) {
        .assignment => |a| {
            // Parse expr for refs
            try self.emitEdgesForExpr(parent_id, a.expr);
        },
        .app => |app| {
            // app.ref → depends_on
            const target = try self.resolveRef(app.ref);
            try self.graph.addEdge(parent_id, target, "depends_on");
        },
        // ... other statement types
    }
}
```

### 4.4 Test: Graph JSON

Emit LPG as canonical JSON. Compare to vakedc golden snapshots.

---

## 5. Canonical JSON Emission (`src/emit.zig`) — 2 hours

### 5.1 Deterministic Serialization

```zig
pub fn toCanonicalJson(graph: *Graph, alloc: Allocator) ![]u8 {
    var buf = ArrayList(u8).init(alloc);
    var writer = buf.writer();
    
    // Sort nodes by id
    var node_ids = ArrayList([]const u8).init(alloc);
    defer node_ids.deinit();
    var node_iter = graph.nodes.keyIterator();
    while (node_iter.next()) |id| {
        try node_ids.append(id.*);
    }
    std.mem.sort([]const u8, node_ids.items, {}, cmpStringLessThan);
    
    // Write JSON
    try writer.writeAll("{\n  \"nodes\": [\n");
    for (node_ids.items, 0..) |id, i| {
        const node = graph.nodes.get(id).?;
        try writeNodeJson(writer, node);
        if (i < node_ids.items.len - 1) try writer.writeAll(",\n");
    }
    try writer.writeAll("\n  ],\n  \"edges\": [\n");
    
    // Sort edges by (source, target, label)
    var edges = ArrayList(GraphEdge).init(alloc);
    var edge_iter = graph.edges.iterator();
    while (edge_iter.next()) |edge| {
        try edges.append(edge.*);
    }
    std.mem.sort(GraphEdge, edges.items, {}, cmpEdgeLessThan);
    
    for (edges.items, 0..) |edge, i| {
        try writeEdgeJson(writer, edge);
        if (i < edges.items.len - 1) try writer.writeAll(",\n");
    }
    try writer.writeAll("\n  ]\n}\n");
    
    return buf.items;
}
```

### 5.2 Key Order (Stable)

For each object in JSON, emit keys in **sorted order**:
```
"byteEnd", "byteStart", "col", "decl", "file", "from", "id", "kind", "labels", ...
```

Use a BTreeMap or sort keys before emitting.

### 5.3 Numeric Precision

Emit numbers as-is (Zig `std.fmt` does this by default for floats).

---

## 6. CLI & Integration (`src/main.zig`) — 1 hour

### 6.1 Subcommand: `parse`

```bash
vakedc-zig parse vaked/examples/fiber.vaked [--print]
```

- Reads file
- Calls lexer → parser → graph builder → emit
- Default: write to `.vaked/graph.json` (create dir)
- `--print`: write to stdout

### 6.2 Subcommand: `lex` (debugging)

```bash
vakedc-zig lex file.vaked
```

Emit token stream (plain text or JSON).

### 6.3 Subcommand: `parse-ast` (debugging)

```bash
vakedc-zig parse-ast file.vaked
```

Emit AST as JSON (helpful for debugging parser issues).

---

## 7. Testing & Verification

### 7.1 Unit Tests

- **`test_lexer.zig`**: Token stream on small snippets (string interpolation, number formats, duration, etc.)
- **`test_parser.zig`**: AST structure on single statements (decl, assignment, app, etc.)
- **`test_graph.zig`**: Node ID derivation, symbol resolution, edge emission

### 7.2 Integration Test: Oracle

```bash
# For each .vaked file in vaked/examples/:
# 1. Run Python reference
python3 -m vakedc parse vaked/examples/fiber.vaked --print > /tmp/ref.json

# 2. Run Zig impl
./vakedc-zig parse vaked/examples/fiber.vaked --print > /tmp/zig.json

# 3. Diff
diff /tmp/ref.json /tmp/zig.json
```

**All 15 examples must produce identical JSON.**

### 7.3 Determinism Check

Run parse twice on the same file; assert identical byte-for-byte output.

### 7.4 Golden Snapshots

Commit expected JSON output (`tests/golden/<example>.json`) to repo. Test runner compares live output to golden.

---

## 8. Debugging Checklist

### Token Stream Mismatches
- [ ] NEWLINE suppression (check depth tracking in lexer)
- [ ] String interpolation (check `${ref}` parsing)
- [ ] Number/duration format (check precision, unit suffix)

### AST Mismatches
- [ ] Soft keyword dispatch order (field/grant/order/open)
- [ ] Block newline handling (statements should be line-terminated)
- [ ] Ref parsing (dotted paths)
- [ ] App parsing (ref + args + record combinations)

### Graph Mismatches
- [ ] Node ID path derivation (check filename basename + scope chain)
- [ ] Provenance spans (byteStart at leading keyword, byteEnd exclusive)
- [ ] Edge emission (check for all ref sites, both in fields + apps)
- [ ] External stub creation (unresolvable refs)

### JSON Mismatches
- [ ] Key order (must be sorted alphabetically)
- [ ] Null handling (provenance omitted if null; empty arrays included)
- [ ] Numeric precision (no rounding)
- [ ] Newline at EOF (required by vakedc)

---

## 9. Deliverables

**End of Phase 1**:

1. ✅ `vakedc-zig/` directory with all source files
2. ✅ `zig build` succeeds, produces `vakedc-zig` binary
3. ✅ All 15 examples parse without errors
4. ✅ JSON output byte-identical to Python reference
5. ✅ Tests pass: unit + oracle integration
6. ✅ README explaining build, usage, architecture
7. ✅ Commit to branch `claude/zig-vaked-compiler-parser-ahmm23`

**PR Description** (ready for review):

```
# vakedc-zig: Phase 1 — Parser → JSON (Zig implementation)

Bootstrap a native Zig parser for the Vaked language, targeting
parity with the Python reference implementation (vakedc).

## What's included

- **Lexer** (src/lexer.zig): UTF-8 tokenization with NFC validation, 
  exact byte spans, newline group-aware suppression, regex mode, 
  string interpolation tracking.
  
- **Parser** (src/parser.zig): Recursive descent per EBNF v0.3, 
  PEG-ordered soft-keyword dispatch, newline-terminated statements, 
  signature + annotation support.
  
- **Graph Builder** (src/graph.zig, src/resolver.zig): Labeled Property 
  Graph instantiation with stable path-derived node IDs, symbol table, 
  forward-ref resolution, edge emission (contains/imports/depends_on/
  requires_capability/routes_to/member_of).
  
- **Emission** (src/emit.zig): Canonical JSON (stable key order, 
  deterministic, byte-identical to vakedc).
  
- **CLI** (src/main.zig): `parse`, `lex`, `parse-ast` subcommands.

## Testing

- Unit tests per subsystem (lexer, parser, graph)
- Oracle test: all 15 vaked/examples/ parse → JSON matches 
  Python reference byte-for-byte
- Determinism verified (two runs = same bytes)
- Golden snapshots committed (tests/golden/*.json)

## Phase readiness

- ✅ Parser complete (all 28 kinds, all expression forms)
- ✅ Graph builder complete (all edge types, external stub creation)
- ✅ Deterministic JSON emission (stable key order, sorted nodes/edges)
- ⏭ Phase 2: Type checker + lowering (next sprint)

Closes #XXX (github issue TBD)
```

---

## 10. Time Budget

| Task | Hours | Owner |
|------|-------|-------|
| Lexer | 4 | auto |
| Parser (AST + soft keyword dispatch) | 5 | auto |
| Graph + resolver | 3 | auto |
| Emission + testing | 3 | auto |
| **Total** | **15** | ~ 2–3 days (6–9 hrs focused work) |

---

## Next Steps (Phase 2)

Once Phase 1 lands:
1. File issue(s) for schema catalog loading + type checker
2. Plan Phase 2: checker implementation (0011 stages 3–4)
3. Plan Phase 3: lowering emitters (parse → artifact tree)
4. Begin dogfeeding: declare vakedos.vaked in full Vaked

---

## References

- Design spec: `docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md`
- Grammar: `vaked/grammar/vaked-v0-plus.ebnf`
- Reference impl: `vakedc/` (Python)
- Examples: `vaked/examples/` (all 15 test cases)
