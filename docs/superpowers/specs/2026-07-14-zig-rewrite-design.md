# VX.XX.XX — Pure Zig Rewrite Design

**Date:** 2026-07-14  
**Branch:** `VX.XX.XX`  
**Status:** Approved  

## Motivation

Eliminate Python dependency, achieve compile-native performance, and unify the codebase into a single Zig toolchain. The current dual Python (`vakedc`) + Zig (`vakedz`) architecture creates maintenance overhead, divergent implementations, and runtime friction.

## Scope

**In scope for VX.XX.XX:**
- Lexer, parser, type checker, graph builder, JSON/SQLite emit
- LSP 3.17 server
- MLIR-mirror pass pipeline (topology, WAL, AOT index)
- CLI with cache integration
- All 6 daemons rebuilt from scratch
- All Python/Go/Shell tools replaced with compiled Zig binaries

**Out of scope for VX.XX.XX:**
- Lowering (16 emitters) — deferred to VX.XX+1
- MLIR dialect implementation — deferred
- New grammar features — grammar stays at v0.5

## Architecture

**Approach A: Zig workspace monorepo.** Single root `build.zig` orchestrates all packages. Shared `lib/` package imported by compiler, daemons, and tools. One `zig build` compiles everything. One `zig build test` runs all tests.

**Key decisions:**
- `lib/` is a Zig library package (not executable)
- `vakedz/` is the compiler executable (imports `lib/`)
- Each daemon is an independent executable (imports `lib/`)
- Each tool is a small CLI binary (imports `lib/`)
- Output format is clean slate (no backward compatibility with `vakedc` JSON/diagnostics)
- Existing `vakedc/` Python archived to `vakedc-python/` (reference only)
- All 6 daemons deleted and rebuilt from scratch with new patterns
- All Python/Go/Shell tools replaced with compiled Zig binaries

## Directory Structure

```
vaked-base/
├── build.zig              # Workspace root
├── build.zig.zon          # Workspace manifest
├── lib/                   # Shared library package
│   └── src/
│       ├── span.zig       # Span, Provenance
│       ├── diagnostic.zig # Diagnostic, Related, Severity
│       ├── json.zig       # Canonical JSON Value
│       ├── cache.zig      # Content-addressed hash-chained CAS
│       └── graph.zig      # GraphNode, GraphEdge, Graph
├── vakedz/                # Compiler executable
│   └── src/
│       ├── main.zig       # CLI dispatch
│       ├── lexer.zig      # Tokenizer
│       ├── parser.zig     # Recursive-descent PEG parser
│       ├── resolve.zig    # Graph construction from AST
│       ├── check.zig      # Type checker + capability/POLA
│       ├── emit.zig       # Graph serialization (JSON, SQLite)
│       ├── lsp.zig        # LSP 3.17 server
│       ├── passes.zig     # MLIR-mirror passes
│       └── trace.zig      # Langfuse instrumentation
├── daemons/               # Independent executables
│   ├── agent_guardd/      # Network/eBPF membrane
│   ├── eventd/            # Hash-chained event log
│   ├── openrouterd/       # OpenRouter proxy
│   ├── synapsed/          # P2P mesh protocol
│   ├── vaked-cdn/         # Documentation CDN index
│   └── vaked-mobile/      # Mobile edge daemon
├── tools/                 # Compiled Zig binaries
│   ├── vaked-cli/         # CLI wrapper
│   ├── docs-autogen/      # Documentation generator
│   ├── seal/              # Genesis seal verification
│   ├── nocturne/          # GPU provisioning
│   └── landing/           # Landing page generation
├── vakedc-python/         # Archived Python reference
├── vaked/                 # Language spec (unchanged)
├── docs/                  # Design docs (unchanged)
└── .github/               # CI (updated)
```

## Shared Library (`lib/`)

`lib/` exports modules shared across compiler, daemons, and tools. It's a Zig library, not an executable.

### `span.zig`

Source location tracking with byte-exact provenance.

```zig
pub const Span = struct {
    file: []const u8,
    byte_start: usize,
    byte_end: usize,
    line: usize,
    col: usize,
};

pub const Provenance = struct {
    file: []const u8,
    decl: []const u8,  // e.g., "fiber mediaCompress"
    span: Span,
};
```

**Used by:** compiler (diagnostics), daemons (event logging), tools (artifact tracking).

### `diagnostic.zig`

Error/warning reporting with deterministic sorting.

```zig
pub const Severity = enum { error, warning, info, hint };

pub const Related = struct {
    file: []const u8,
    decl: []const u8,
    span: Span,
    message: []const u8,
};

pub const Diagnostic = struct {
    code: []const u8,
    message: []const u8,
    file: []const u8,
    line: usize,
    col: usize,
    byte_start: usize,
    byte_end: usize,
    decl: []const u8,
    severity: Severity,
    related: []const Related,

    pub fn sortKey(self: Diagnostic) u64 { ... }
};
```

**Used by:** compiler (type errors), daemons (health checks), tools (validation).

### `json.zig`

Canonical JSON serialization with deterministic output.

```zig
pub const Value = union(enum) {
    null,
    bool: bool,
    int: i64,
    float: f64,
    string: []const u8,
    array: []const Value,
    object: []const Entry,

    pub const Entry = struct {
        key: []const u8,
        value: Value,
    };

    pub fn writeCanonical(self: Value, writer: anytype) !void { ... }
    pub fn sortRecursive(self: *Value, allocator: Allocator) void { ... }
    pub fn toOwned(self: Value, allocator: Allocator) ![]u8 { ... }
};
```

**Properties:**
- Objects emit in insertion order (caller controls canonicalization)
- Strings escape `\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`
- Control chars → `\u00XX`
- `/` not escaped
- `sortRecursive()` for deep key sorting (used on props subtrees)

**Used by:** compiler (graph output), daemons (event logs), tools (artifact manifests).

### `cache.zig`

Content-addressed hash-chained storage.

```zig
pub const Phase = enum { parse, check, lower };

pub const Cache = struct {
    allocator: Allocator,
    root: []const u8,

    pub fn open(allocator: Allocator, root: []const u8) !Cache { ... }
    pub fn lookup(self: *Cache, file: []const u8, source: []const u8, phase: Phase) !?[]u8 { ... }
    pub fn put(self: *Cache, file: []const u8, source: []const u8, phase: Phase, output: []const u8) !void { ... }
    pub fn verify(self: *Cache) !VerifyResult { ... }
};

pub const VerifyResult = struct {
    entries: usize,
    valid_prefix: usize,
    ok: bool,
};

pub fn sha256Hex(bytes: []const u8, out: *[64]u8) void { ... }
pub fn chainHex(prev: [64]u8, payload: []const u8, out: *[64]u8) void { ... }
```

**Disk layout:**
```
.vakedz-cache/
  ledger.jsonl    # Hash-chained append-only ledger
  cas/<sha256>    # Content-addressed output blobs
```

**Used by:** compiler (ralphloop-cache), eventd (ledger), tools (build artifacts).

### `graph.zig`

Labeled property graph with provenance.

```zig
pub const GraphNode = struct {
    id: []const u8,
    kind: []const u8,
    name: []const u8,
    labels: []const []const u8,
    props: json.Value,
    provenance: ?Provenance,
};

pub const GraphEdge = struct {
    source: []const u8,
    target: []const u8,
    label: []const u8,
    props: json.Value,
};

pub const Graph = struct {
    nodes: StringHashMap(GraphNode),
    edges: ArrayList(GraphEdge),
    adjacency: AutoHashMap(struct { []const u8, []const u8 }, ArrayList([]const u8)),

    pub fn addNode(self: *Graph, node: GraphNode) void { ... }
    pub fn getNode(self: *Graph, id: []const u8) ?GraphNode { ... }
    pub fn addEdge(self: *Graph, edge: GraphEdge) void { ... }
    pub fn children(self: *Graph, source: []const u8, label: []const u8) []const []const u8 { ... }
};

pub fn nodeId(filename: []const u8, chain: []const []const u8) []const u8 { ... }
```

**Node ID format:** `"<basename>#<outer>/<inner>/..."`

**Edge labels:** `contains`, `imports`, `depends_on`, `requires_capability`, `routes_to`, `member_of`.

**Used by:** compiler (semantic graph), daemons (capability queries), tools (graph operations).

## Compiler (`vakedz/`)

`vakedz/` is the compiler executable. It imports `lib/` and implements the Vaked pipeline: lex → parse → resolve → check → emit.

### `lexer.zig`

Tokenization with byte-exact spans.

**Token kinds:**
```zig
pub const Kind = enum {
    ident, string, number, duration, bytes, path, regex, op, newline, eof,
};

pub const Token = struct {
    kind: Kind,
    value: []const u8,
    byte_start: usize,
    byte_end: usize,
    line: usize,
    col: usize,
};
```

**Key behaviors:**
- NFC normalization gate (rejects non-NFC source)
- NEWLINE suppression inside `(`/`[` (group depth tracking)
- Regex literals only after `matches` keyword
- Path tokens (`./foo`) in leading position
- Multi-char operators matched longest-first (`->`, `<=`, `>=`, `..`, `?=`)
- Duration units: `ns`, `us`, `ms`, `s`, `m`, `h`, `d`
- Bytes units: `B`, `KB`, `MB`, `GB`, `TB`
- `${ref}` interpolation consumed verbatim into STRING

**Errors:** `LexError` with span.

### `parser.zig`

Recursive-descent PEG parser producing AST.

**AST node types:**
```zig
pub const Item = union(enum) {
    decl: *const Decl,
    import: []const u8,
};

pub const Decl = struct {
    kind: []const u8,
    name: []const u8,
    annotations: []const Annotation,
    signature: ?Signature,
    body: []const Stmt,
    span: Span,
};

pub const Stmt = union(enum) {
    field: FieldDecl,
    open: OpenDecl,
    grant: GrantDecl,
    order: OrderDecl,
    assign: Assignment,
    inherit: InheritStmt,
    edge: Edge,
    node: NodeDecl,
    decl: *const Decl,
    app: App,
};

pub const Expr = union(enum) {
    literal: Literal,
    list: ListLit,
    record: RecordLit,
    app: App,
};
```

**PEG-ordered disambiguation:** field → grant → order → member → assign → open → inherit → edge → node → decl → app (first match wins).

**Kind keywords (35 total):** runtime, engine, host, network, filesystem, mcp, ebpf, budget, observability, runclass, workflow, index, catalog, stream, fiber, surface, mesh, device, mediaPipeline, parallel, schema, capability, service, secret, hostResource, ingress, container, memory, namespace, arp_event, dyad, ceremony, arbiter, trust, quorum, probe.

**Errors:** `SyntaxError` with span.

### `resolve.zig`

Graph construction from AST.

**Two-pass algorithm:**
1. **Index pass:** Assign IDs, index every decl by name + kind/name
2. **Build pass:** Construct nodes, edges, imports

**Scope tracking:**
- Lexical scope with parent link
- Forward references resolved via deferred worklist
- External stub nodes for cross-file references

**Edge labels produced:**
- `contains` — parent decl → child decl/node
- `imports` — file → external stub for `use`d path
- `depends_on` — from `input`/`output`/`from`/`source`/`engine` fields
- `requires_capability` — from `capabilities` lists
- `routes_to` — from mesh/workflow `->` edges
- `member_of` — from `parallel`'s `fibers` list

**API:**
```zig
pub fn buildGraph(allocator: Allocator, items: []const Item, sourcePath: []const u8) !Graph { ... }
```

### `check.zig`

Type checker + capability/POLA enforcement.

**Registry:**
```zig
const Registry = struct {
    schemas: StringHashMap(SchemaSpec),
    caps: StringHashMap(CapabilitySpec),
    namespaces: StringHashMap(NamespaceSpec),
};

const SchemaSpec = struct {
    name: []const u8,
    fields: StringHashMap(FieldSpec),
    open: bool,
    origin_file: []const u8,
    decl_span: Span,
};

const CapabilitySpec = struct {
    domain: []const u8,
    grants: []const []const u8,
    order_chains: []const []const []const u8,
    leq: AutoHashMap([]const u8, AutoHashMap([]const u8, bool)),  // reflexive-transitive closure
    origin_file: []const u8,
    decl_span: Span,
};
```

**Checking pipeline:**
1. Parse builtins → load into registry
2. Parse user source → load into registry (user overrides builtins by name)
3. Collect `use`-imported declaration names (closed-world, one level)
4. Build source maps for builtins + user file
5. Validate schema well-formedness (refinements, regex, oneof, default, range)
6. Validate namespace well-formedness (open + member don't mix)
7. Validate capability well-formedness (dangling grants, acyclicity, transitive closure)
8. Check name collisions (top-level name uniqueness)
9. Walk decl tree: conformance, generics, mesh, workflow, ebpf checks
10. Resolve reference targets (namespace lookup, RFC 0017 branch B)

**Diagnostic codes:**
- Schema: `E-SCHEMA-REFINEMENT`, `E-SCHEMA-BAD-REGEX`, `E-SCHEMA-BAD-ONEOF`, `E-SCHEMA-BAD-DEFAULT`, `E-SCHEMA-BAD-RANGE`
- Capability: `E-CAP-ORDER-DANGLING`, `E-CAP-ORDER-CYCLE`, `E-CAP-UNKNOWN-DOMAIN`, `E-CAP-UNKNOWN-GRANT`, `E-CAP-ATTENUATION`, `E-CAP-USE`
- Conformance: `E-CONFORM-MISSING-FIELD`, `E-CONFORM-UNKNOWN-FIELD`, `E-CONFORM-TYPE`
- Constraints: `E-CONSTRAINT-NONEMPTY`, `E-CONSTRAINT-ONEOF`, `E-CONSTRAINT-RANGE`, `E-CONSTRAINT-MATCHES`
- Generics: `E-GENERIC-INCONSISTENT`
- Names: `E-DECL-NAME-COLLISION`
- References: `E-REF-UNRESOLVED`
- Workflow: `E-WORKFLOW-CYCLE`, `E-WORKFLOW-DEPTH`
- eBPF: `E-EBPF-UNKNOWN-HOOK`, `E-EBPF-BAD-INTENT`, `E-EBPF-ENFORCE-ON-OBSERVE`
- Determinism: `E-DETERMINISM-EFFECT`
- Egress: `E-EGRESS-USE`
- Warnings: `W-POLA-EXCESS`, `W-CONFUSED-DEPUTY`, `W-EGRESS-UNREFINED`

**API:**
```zig
pub fn checkSource(
    allocator: Allocator,
    sourcePath: []const u8,
    source: []const u8,
    builtinsPath: []const u8,
) ![]const Diagnostic { ... }
```

### `emit.zig`

Graph serialization.

**Canonical JSON:**
```zig
pub fn toCanonicalJson(allocator: Allocator, graph: Graph) ![]u8 { ... }
```
- Nodes sorted by `id`
- Edges sorted by `(source, label, target, propskey)`
- Fixed key order, compact separators
- Trailing newline

**SQLite:**
```zig
pub fn toSqlite(allocator: Allocator, graph: Graph, path: []const u8) !void { ... }
```
- `nodes` table: `id`, `kind`, `name`, `labels`, `props`, `provenance`
- `edges` table: `source`, `target`, `label`, `props`

### `lsp.zig`

LSP 3.17 server over stdio (JSON-RPC 2.0).

**Capabilities:**
- `textDocument/completion` — 35 kind keywords + ~30 common field names + ~10 refinement keywords
- `textDocument/hover` — markdown summaries for every kind keyword
- `textDocument/definition` — tokenize source, search for declaration matching hovered word
- `textDocument/publishDiagnostics` — async diagnostic publishing on open/change

**Implementation:**
- Content-Length framed messages
- Handled methods: `initialize`, `initialized`, `shutdown`, `exit`, `didOpen`, `didChange`, `didClose`, `completion`, `hover`, `definition`
- Diagnostics published via daemon thread

### `passes.zig`

MLIR-mirror pass pipeline.

**Pass 1: Topology analysis**
- Cycle detection (iterative DFS with WHITE/GREY/BLACK coloring)
- Critical-path depth computation
- `maxDepth` bound enforcement
- Diagnostics: `E-WORKFLOW-CYCLE`, `E-WORKFLOW-DEPTH`

**Pass 2: WAL injection**
- Write-ahead-log frames for every cross-step dependency edge
- Frame type: `DependencyRegistration`
- Protocol: `hcp.create_registration_token`, `hcp.write_ahead_log`, `hcp.fetch_canonical_data`

**Pass 3: AOT index generation**
- `gen/workflow/<name>.json` per workflow
- Fields: `_generated`, `on`, `budget`, `maxDepth`, `steps`, `edges`, `depth`, `wal`, `log`, `criticalPath`

**API:**
```zig
pub const WorkflowIR = struct {
    node: GraphNode,
    steps: []const GraphNode,
    edges: []const GraphEdge,
    depth: usize,
    critical_path: []const []const u8,
    wal_frames: []const json.Value,
};

pub const PassResult = struct {
    diagnostics: []const Diagnostic,
    workflows: []const WorkflowIR,
    artifacts: StringHashMap([]const u8),  // path → content
};

pub fn runPipeline(
    allocator: Allocator,
    graph: Graph,
    workflowNodes: []const GraphNode,
) !PassResult { ... }
```

### `trace.zig`

Langfuse instrumentation (zero-cost when not configured).

```zig
pub fn traceCompile(cmd: []const u8, file: []const u8) ?Trace { ... }
pub fn recordParse(trace: ?Trace, items: usize, elapsed_ms: u64) void { ... }
pub fn recordCheck(trace: ?Trace, diags: []const Diagnostic, elapsed_ms: u64) void { ... }
pub fn recordError(trace: ?Trace, err: anyerror) void { ... }
```

### `main.zig`

CLI dispatch.

**Subcommands:**
```
vakedz parse <file> [--json PATH] [--print] [--no-cache]
vakedz check <file> [--json] [--builtins PATH]
vakedz lsp
vakedz passes <file> [--json]
vakedz all <file> [--out DIR]
```

**Cache integration:**
- `parse` and `check` use `lib/cache.zig` for ralphloop-cache
- `--no-cache` bypasses cache lookup/store
- `cache verify` validates ledger chain integrity

## Daemons

All 6 daemons deleted and rebuilt from scratch. Each daemon is an independent executable importing `lib/`.

### `agent_guardd/`

Network/eBPF membrane daemon.

**Responsibilities:**
- Deny-by-default egress enforcement
- eBPF programs for traffic filtering, mmap boundary enforcement
- Capability attenuation checks

**Imports:** `lib/diagnostic`, `lib/graph` (for capability queries).

**Patterns:** seccomp, mmap-backed state, atomic slots.

### `eventd/`

Append-only hash-chained event log.

**Responsibilities:**
- Hash-chained ledger (SHA256 chain like ralph/eventd)
- Unix socket interface (`/run/vaked/eventd.sock`)
- JSON event format with provenance

**Imports:** `lib/cache` (hash-chained ledger), `lib/json`, `lib/span`.

### `openrouterd/`

OpenRouter proxy daemon ("Atlas").

**Responsibilities:**
- Raw TCP socket server (port 9090)
- OpenRouter API proxy with SSE streaming
- Telegram bot control interface
- BigArena shared-memory (256MB hugepage)

**Imports:** `lib/json`, `lib/span`.

### `synapsed/`

P2P mesh protocol daemon.

**Responsibilities:**
- UDP gossip, Merkle tree, Raft-lite consensus
- LedgerSlot with cumulative SHA256
- Ghost-in-the-Shell fail-stop/rollback

**Imports:** `lib/cache` (Merkle hashing), `lib/json`.

### `vaked-cdn/`

Documentation CDN index.

**Responsibilities:**
- Ingest doc entries with SHA256 content hashing
- Zone-based lookup (global/repo/zone)

**Imports:** `lib/json`.

### `vaked-mobile/`

Mobile edge daemon.

**Responsibilities:**
- Dense frame dispatcher (1-16KB ceiling)
- Edge compute arbiter (block local compile by default)
- Viewport bus (WireGuard tunnel for binary snapshots)

**Imports:** `lib/span`.

### Common patterns

All daemons follow these patterns:

1. **Genesis Seal** — `GENESIS_SEAL: 7c242080` at top of every file. Validated at compile time and runtime (binary self-verification via SHA256).

2. **mmap-backed state** — All daemon state in page-aligned `mmap` regions (not heap). Shared data structures use `extern struct` with explicit alignment.

3. **Seqlock** — Lock-free reads, single-writer writes without kernel synchronization. `beginWrite()` sets seq odd, `endWrite()` increments to even. `beginRead()` spins while odd, then `endRead()` checks seq unchanged.

4. **Atomic slot acquisition** — Xchg-based spinlock for slot allocation. Status lattice: 0=free, 1=active, 2=completed, 3=consumed.

5. **`extern struct`** — All shared-memory structs declared `extern struct` with explicit alignment (`align(64)` for cache-line boundaries). Comptime size checks.

6. **Seccomp-conscious** — Explicit syscall inventory documenting which syscalls each module needs and whether they're in the allowlist.

7. **Pure/data split** — Syscall-free core logic (portable, testable) separated from Linux-only backend (comptime-guarded).

8. **Zero-allocation hot path** — Fixed-capacity inline buffers, caller-provided buffers via `std.fmt.bufPrint`.

9. **Deterministic crypto** — SHA256 everywhere (Merkle trees, ledger chains, snapshot identification, binary verification).

10. **Comprehensive tests** — Inline tests + separate `_test.zig` files. No syscalls in tests (pure logic only).

## Tools

All Python/Go/Shell tools replaced with compiled Zig binaries. Each tool is a small CLI executable importing `lib/`.

### `tools/vaked-cli/`

Replaces `tools/vaked-cli` (Go, 765 lines).

**Subcommands:** `parse`, `check`, `graph`, `lower` (stub).

**Imports:** `vakedz/lexer`, `vakedz/parser`, `vakedz/check`, `lib/graph`, `lib/json`.

### `tools/docs-autogen/`

Replaces `tools/docs-autogen.py` (322 lines).

**Responsibilities:**
- Scan `docs/` and `vaked/examples/` for source files
- Generate HTML/Markdown documentation index
- Extract code snippets, cross-references

**Imports:** `lib/json`, `lib/span`.

### `tools/seal/`

Replaces `tools/vaked-seal.py` (230 lines).

**Responsibilities:**
- Genesis seal verification (0x7C242080)
- Binary self-verification via SHA256
- Seal injection into compiled binaries

**Imports:** `lib/cache` (SHA256).

### `tools/nocturne/`

Replaces `tools/nocturne/provision.sh` (13 lines).

**Responsibilities:**
- Vast.ai GPU instance provisioning
- SSH key injection, environment setup
- Teardown on completion

**Imports:** `lib/json` (API responses).

### `tools/landing/`

Replaces `scripts/landing-guru.sh` (4 lines changed).

**Responsibilities:**
- Landing page generation from templates
- Cache validation and freshness checks
- Slack alerting on drift

**Imports:** `lib/json`.

## Build System

Single root `build.zig` orchestrates all packages.

### Workspace layout

```
vaked-base/
├── build.zig              # Workspace root
├── build.zig.zon          # Workspace manifest
├── lib/build.zig.zon      # Package: lib (Zig library)
├── vakedz/build.zig.zon   # Package: vakedz (executable, depends on lib)
├── daemons/
│   ├── agent_guardd/build.zig.zon
│   ├── eventd/build.zig.zon
│   ├── openrouterd/build.zig.zon
│   ├── synapsed/build.zig.zon
│   ├── vaked-cdn/build.zig.zon
│   └── vaked-mobile/build.zig.zon
└── tools/
    ├── vaked-cli/build.zig.zon
    ├── docs-autogen/build.zig.zon
    ├── seal/build.zig.zon
    ├── nocturne/build.zig.zon
    └── landing/build.zig.zon
```

### Build steps

**`zig build`** — Compile all packages
- Builds `lib/` (library)
- Builds `vakedz/` (compiler executable)
- Builds all 6 daemons (executables)
- Builds all 5 tools (executables)
- Output: `zig-out/bin/vakedz`, `zig-out/bin/agent_guardd`, etc.

**`zig build test`** — Run all tests
- Unit tests in `lib/src/*.zig`
- Unit tests in `vakedz/src/*.zig`
- Unit tests in each daemon's `src/*.zig`
- Unit tests in each tool's `src/*.zig`
- Inline tests + comprehensive `_test.zig` files

**`zig build check`** — Lint/format check
- `zig fmt --check` on all `.zig` files
- No compile, fast feedback

**`zig build run -- <args>`** — Run vakedz with arguments
- Convenience wrapper for `zig-out/bin/vakedz <args>`

**`zig build -Dtarget=<triple>`** — Cross-compilation
- Zig's native cross-compilation support
- Target Linux x86_64 for deployment, macOS for development

### Build flags

- `-Doptimize=ReleaseFast` — production builds (strip, LTO)
- `-Doptimize=Debug` — development builds (assertions, debug info)
- `-Dtarget=x86_64-linux` — cross-compile for Linux deployment

### Package dependencies

```
lib (no dependencies, stdlib only)
  ↑
  ├── vakedz (imports lib)
  ├── agent_guardd (imports lib)
  ├── eventd (imports lib)
  ├── openrouterd (imports lib)
  ├── synapsed (imports lib)
  ├── vaked-cdn (imports lib)
  ├── vaked-mobile (imports lib)
  ├── tools/vaked-cli (imports lib + vakedz modules)
  ├── tools/docs-autogen (imports lib)
  ├── tools/seal (imports lib)
  ├── tools/nocturne (imports lib)
  └── tools/landing (imports lib)
```

## Testing Strategy

Comprehensive testing across all packages.

### Unit tests

Inline in every module:
```zig
test "tokenize dotted ref vs path" {
    const allocator = testing.allocator;
    var lexer = Lexer.init(allocator, "foo.bar");
    try lexer.run();
    // ...
}
```

Comprehensive `_test.zig` files for complex modules (lexer, parser, check, graph).

Run via `zig build test`.

### Golden tests

Use `vaked/examples/` as test corpus (54 files):
- Each `.vaked` file produces deterministic JSON graph output
- Store expected output in `vakedz/test/golden/` (committed)
- CI compares `vakedz parse <file>` output against golden files
- Type system fixtures: `conformant.vaked` (zero diagnostics), `rejected.vaked` (specific error codes)

### Integration tests

End-to-end pipeline:
- `vakedz all <file>` runs parse → check → passes
- Verify no crashes, correct diagnostic counts, valid JSON output
- Test CLI flags: `--json`, `--print`, `--no-cache`
- Test LSP server: JSON-RPC handshake, completion, diagnostics

### Property tests

Fuzzing and edge cases:
- Fuzz lexer with malformed UTF-8, unterminated strings, deep nesting
- Fuzz parser with invalid grammar, missing braces, ambiguous edges
- Fuzz type checker with cyclic schemas, infinite refinements, capability escalation
- Use `std.testing.allocator` to catch leaks

### Benchmark tests

Performance regression:
- Parse 100k-worker scalability fixture (`swe-swarm-100k-workers.vaked`)
- Check 1M-worker fixture (`swe-swarm-1m-workers.vaked`)
- Target: <100ms for 100k workers, <1s for 1M workers
- Run via `zig build test -Dbenchmark=true`
- Track in CI, fail on >20% regression

### Test infrastructure

- `vakedz/test/` — test utilities, golden file loader, fixture paths
- `vakedz/test/golden/` — expected JSON output for each example
- `vakedz/test/fixtures/` — additional test cases (malformed input, edge cases)
- `lib/test/` — shared test helpers (allocator wrappers, assertion macros)

### CI integration

- `.github/workflows/zig-build.yml` — run `zig build` on every push
- `.github/workflows/spec-tests.yml` — run `zig build test` on every push
- Fail on: compile errors, test failures, format violations, performance regression
- Pass on: all green, golden files match, benchmarks within tolerance

## What Gets Deleted

Explicit removal list. Everything not mentioned here stays.

### Archived (moved, not deleted)

- `vakedc/` → `vakedc-python/` (reference only, excluded from build)

### Deleted — compiler

- `vakedz/src/check.zig` (replaced by new implementation importing `lib/`)
- `vakedz/src/lower.zig` (scaffold removed, not in VX.XX.XX scope)
- `vakedz/build.zig` and `build.zig.zon` (replaced by workspace root)

### Deleted — daemons (all 6 rebuilt from scratch)

- `daemons/openrouterd/src/*.zig` (28 files)
- `daemons/sandboxd/src/*.zig` (3 files) + `.zig-cache/` + `zig-out/`
- `daemons/synapsed/*.zig` (14 files)
- `daemons/vaked-cdn/src/*.zig` (1 file)
- `daemons/vaked-mobile/src/*.zig` (3 files)
- `daemons/vaked-ebpf/*.bpf.c` (2 files)
- All `daemons/*/build.zig` and `build.zig.zon`

### Deleted — tools (replaced by compiled Zig)

- `tools/vaked-cli/` (Go source: main.go, graph.go, go.mod)
- `tools/docs-autogen.py` (322 lines)
- `tools/vaked-seal.py` (230 lines)
- `tools/vaked-mlir.py` (283 lines)
- `tools/build-mlir-stage1.sh` (83 lines)
- `tools/nocturne/provision.sh` (13 lines)
- `scripts/landing-guru.sh` (4 lines changed)

### Deleted — cruft

- `hugo-site/` (entire directory — old Hugo site)
- `site/` (entire directory — old generated docs site)
- `deploy/vaked.dev/` (old deployment config)
- `sites/beat-vaked-dev/`, `sites/protocol-vaked-dev/` (old static sites)
- `AG-UI/` (Swift UI files — not part of Zig rewrite)
- `internal/`, `internal_tui_model_prompt.go` (Go TUI)
- `statusline/`, `superpowers/`, `repomap/` (Go plugins)
- `blocks_adapter.go`, `hooks_agent.go` (Go adapters)
- `web/github.zip`, `web/Vaked Sentinel Console*.html`
- `vakedc.egg-info/` (Python packaging artifacts)
- `pyproject.toml` (Python project config)
- Orphan files: `fix_indent.py`, `patch_infra.py`, `patch_self.py`, `crabcc-cleanup-dirs.sh`, `pr-reviews-0620`

### Deleted — docs/specs (superseded)

- `docs/superpowers/plans/2026-06-23-protocol-vaked-dev.md` (old protocol plan)
- `docs/superpowers/specs/2026-06-23-protocol-vaked-dev-design.md` (old design)

### Stays (untouched)

- `vaked/` — language spec, grammar, schema, examples
- `docs/` — design docs, language specs, protocol RFCs (except superseded ones)
- `.github/` — CI workflows (updated for new build)
- `hosts/` — NixOS host configuration
- `flake.nix` — dev shell (updated for Zig-only)
- `CLAUDE.md`, `AGENTS.md`, `README.md` — project docs (updated)
- `protocol/` — HCP/Litany protocol RFCs
- `.worktrees/` — git worktrees (managed by git)

## Success Criteria

VX.XX.XX ships when:

1. **Compiler complete:** `vakedz parse`, `vakedz check`, `vakedz lsp`, `vakedz passes` all working
2. **All tests pass:** Unit tests, golden tests, integration tests, benchmarks within tolerance
3. **All daemons built:** 6 daemons compile and pass their test suites
4. **All tools built:** 5 tools compile and pass their test suites
5. **No Python/Go runtime:** Zero Python or Go dependencies at runtime (Python archived, Go deleted)
6. **Single build:** `zig build` compiles everything, `zig build test` runs all tests
7. **CI green:** All workflows pass on every push

## Timeline

No deadline. Quality over speed. Ship when ready.

## Next Steps

1. Set up workspace root (`build.zig`, `build.zig.zon`)
2. Implement `lib/` package (span, diagnostic, json, cache, graph)
3. Port `vakedz/` compiler modules (lexer, parser, resolve, check, emit, lsp, passes, trace)
4. Rebuild daemons one at a time (agent_guardd, eventd, openrouterd, synapsed, vaked-cdn, vaked-mobile)
5. Build tools (vaked-cli, docs-autogen, seal, nocturne, landing)
6. Set up golden tests and CI
7. Archive `vakedc/` to `vakedc-python/`
8. Delete cruft
9. Update documentation (CLAUDE.md, README.md)
10. Tag VX.XX.XX release
