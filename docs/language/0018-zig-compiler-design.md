# 0018 — vakedc-zig: the Zig compiler-parser (v0.1.0)

Status: **design + implementation** (2026-06-13) · Series: language design notes ·
Issues [#114](https://github.com/peterlodri-sec/vaked-base/issues/114) (build-time cache primitive),
[#115](https://github.com/peterlodri-sec/vaked-base/issues/115) (sequential pipeline strategy) ·
Epic [#17](https://github.com/peterlodri-sec/vaked-base/issues/17)

---

## 1. Motivation

The Python `vakedc` exists and works. Why a Zig compiler?

**Performance.** The Python front-end is fast enough for interactive use today,
but the compiler is the bottleneck in two planned loops: the ralphloop cache
verification path (re-parsing on cache miss) and the eBPF policy pipeline
(parse → check → emit policy BPF on every source change). Both paths tolerate
Python latency at human scale; neither tolerates it at daemon scale. A single
binary that starts in microseconds and holds the lexer/parser in cache has a
different performance envelope.

**Single binary, no runtime.** Zig compiles to a self-contained binary with no
libc requirement, no package manager, no interpreter. The goal for the runtime
plane ([0012](./0012-lowering.md), epic #17) is that every enforcement daemon
is a Zig binary deployed by Nix: `vakedc-zig` belongs to the same distribution
story. A Python dependency in the hot parse path would break that invariant.

**Direct EBNF→types mapping.** Zig's tagged unions and comptime give a near-
isomorphic mapping from the EBNF grammar to AST types: each production rule
becomes a tagged union variant, each terminal becomes a typed field. This is
the same principle as the enforcement daemons — the type system encodes the
spec, not the implementation. The Python parser is a proof of concept; the Zig
parser is the spec artifact.

**Safety without a garbage collector.** The runtime enforcement layer (eBPF,
Zig daemons) is memory-safe by design. `vakedc-zig` demonstrates that the
compiler itself belongs to that safety story: arena allocation for the AST,
no heap fragmentation, deterministic lifetimes.

**Enforcement-layer dogfood.** The single most important axiom in this
architecture is: *describe your own infrastructure in Vaked before describing
anyone else's*. The compiler pipeline is `vaked/examples/compiler/vakedc-zig.vaked`.
Building the compiler forces the language to describe a real build pipeline.
The gaps found during that dogfeed are issues — see §4.

---

## 2. Scope (v0.1.0)

v0.1.0 implements the **parse stage only**:

```
source bytes → lexer (tokenize) → parser (recursive descent) → JSON AST
```

The JSON AST is compatible with the Python `vakedc parse` output. The Python
checker (`vakedc check`) and lowerer (`vakedc lower`) consume it unchanged: the
Zig parser and the Python checker form a working pipeline without any new code
in the Python half.

**In scope:**
- UTF-8 lexer: all token types from the EBNF grammar v0.3
- Recursive-descent parser following the EBNF grammar productions verbatim
- JSON AST with source spans (byte offset + line/col) on every node
- ralphloop-cache (§3): content-addressed parse cache with hash-chained index
- CLI: `vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>`
- Exit codes: 0 = success + JSON AST on stdout, 1 = parse error + diagnostics
  on stderr

**Out of scope (v0.1.0):**
- `check` — type system, schema validation, capability flow (0011). Python
  checker remains authoritative.
- `lower` — artifact generation (0012). Python lowerer remains authoritative.
- LSP integration — the Python `vakedc lsp` bridge is untouched.
- Incremental / partial re-parse.

---

## 3. ralphloop-cache

The immutable parse cache is a direct application of the
[ralph-loop event log pattern](../../tools/ralph/PURPOSE.md) at build time.

### Pattern origin

ralph-loop maintains its decision history as an **immutable, append-only,
hash-chained JSONL ledger**: `tools/ralph/state/events.jsonl`. Each entry
carries `seq` (monotone sequence number), `prev` (SHA-256 of the previous
entry — `0…0` for the genesis entry), a `payload`, and `hash` (SHA-256 of the
entry excluding the `hash` field). The chain is tamper-evident by construction:
any mutation of an entry invalidates all successor hashes.

`vakedc-zig` applies the same shape to parse results. Source bytes → parse
result is a pure function; the cache is the durable evidence that the function
was already evaluated.

### Cache layout

```
.vaked/cache/
  objects/<sha256>          # content-addressed AST blobs (JSON, gzip optional)
  parse.index.jsonl         # the hash-chained ledger
```

### Index entry format

Each line of `parse.index.jsonl` is a JSON object:

```json
{
  "seq":      0,
  "prev":     "0000000000000000000000000000000000000000000000000000000000000000",
  "key":      "<sha256 of source bytes>",
  "artifact": "vakedc-zig/ast/v1",
  "ref":      "<sha256 of AST bytes stored in objects/>",
  "ts_iso":   "2026-06-13T00:00:00Z",
  "hash":     "<sha256 of entry excluding the hash field>"
}
```

Fields:

| Field | Meaning |
|-------|---------|
| `seq` | Monotone integer. Genesis = 0. |
| `prev` | SHA-256 of the previous entry's canonical bytes. Genesis prev = `0…0`. |
| `key` | SHA-256 of the source `.vaked` file bytes. The cache key. |
| `artifact` | Format identifier. `vakedc-zig/ast/v1` for this release. |
| `ref` | SHA-256 of the AST JSON bytes, used to look up `objects/<ref>`. |
| `ts_iso` | ISO 8601 timestamp. Log-only; does not affect cache semantics. |
| `hash` | SHA-256 of the entry serialized without the `hash` field (canonical form: alphabetic key order, no trailing whitespace). Chains the ledger. |

### Cache semantics

**Lookup (O(1) by content address):** given a source file, compute `key =
sha256(bytes)`. If `objects/<key_of_ref>` exists and the most recent index
entry for that key has a matching `ref`, return the stored AST. The ledger is
not scanned on the hot path — the `objects/` directory is the primary store;
the ledger is the audit trail.

**Write:** parse result → write `objects/<sha256(ast_bytes)>` → append one
entry to `parse.index.jsonl` chaining to the previous tail.

**Eviction policy:** none. The cache is append-only and never evicts. Entries
accumulate as long as the cache directory exists. Cache clearing = `rm -rf
.vaked/cache/`.

**This IS the `memory` primitive (0014) applied at build time.** The source
stream is the set of `.vaked` files under compilation; the mine step is the
parse; the durable, replayable store is the cache. The difference from 0014 is
that 0014 describes a *runtime* memory (mined during agent execution); the parse
cache is a *build-time* memory (mined during `vakedc-zig parse`). This
distinction is a language gap — see §4.

---

## 4. Dogfeed loop

The compiler's own pipeline is described in
[`vaked/examples/compiler/vakedc-zig.vaked`](../../vaked/examples/compiler/vakedc-zig.vaked)
before the compiler exists. This is Vaked's rule-2 dogfood obligation: if the
language cannot describe its own tooling, that is a language deficiency.

The dogfeed file uses `fiber` for each compiler stage and `memory` for the
parse cache. Two gaps were found during authoring:

### Gap A — no build-time `memory` variant

`memory` (0014) is designed for *runtime* accumulation: the `source` field
takes a `stream`, the `mine` normalizer distills at runtime, the fold is over
`eventd` entries. The parse cache is semantically identical but operates at
*build time*: `source` is a set of files on disk, `mine` is a pure parse
function, the store is a directory of content-addressed blobs.

The grammar has no `build_memory`, no `cache` kind, and no `scope = "build"`
variant. The dogfeed file uses `memory` with a `# gap:` comment noting the
mismatch. Filing issue to decide: (a) add a `scope = "build"` variant to 0014;
(b) add a separate `cache` kind; or (c) accept that the `memory` primitive
is runtime-only and the parse cache is described as a `memory` with a
non-normative `scope`.

**Issue filed:** [#114](https://github.com/peterlodri-sec/vaked-base/issues/114) — "language gap: build-time memo/cache primitive (vs runtime `memory` 0014)" — references 0014, 0018.

### Gap B — sequential build stages in a `parallel` / `supervised-dag`

`parallel` with `strategy = "supervised-dag"` is designed for parallel runtime
fibers under OTP supervision: fibers fan out, OTP restarts failures. A compiler
pipeline (`parse → check → lower`) is a *sequential* stage chain, not a fan-out
computation. Describing it as a `supervised-dag` stretches the semantics:
the DAG has no parallelism at steady state; the supervision story is about
restart-on-failure, not OTP-style child specs.

The `workflow` kind (0015) is closer — it models a sequential step DAG — but
`workflow` is for agent workflows triggered by events (`on = "github.issue…"`),
not for build-time pipelines. A first-class `pipeline` kind, or a
`strategy = "sequential"` variant on `parallel`, would be the right fix.

The dogfeed file uses `parallel … strategy = "supervised-dag"` with a `# gap:`
comment. Filing issue to decide: add `strategy = "sequential"` as a named
variant or introduce a `pipeline` kind.

**Issue filed:** [#115](https://github.com/peterlodri-sec/vaked-base/issues/115) — "language gap: sequential build pipeline modeling (`supervised-dag` is for parallel runtime, not ordered build stages)" — references 0008, 0018.

---

## 5. Architecture

### Source layout

```
zig/vakedc/
  build.zig           # zig build entry point
  build.zig.zon       # package manifest
  src/
    main.zig          # CLI: argument parsing, dispatch, exit codes
    lexer.zig         # tokenizer: UTF-8 source → token stream
    ast.zig           # AST types (tagged unions) + JSON serializer
    parser.zig        # recursive descent following EBNF grammar
    cache.zig         # ralphloop cache: SHA-256, objects/, parse.index.jsonl
```

### Build

```sh
cd zig/vakedc
zig build          # produces zig-out/bin/vakedc-zig
zig build test     # runs the test suite
```

The `flake.nix` dev shell provides the Zig toolchain via `nix develop`.

### CLI

```
vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>
```

- `--cache-dir DIR` — override cache root (default: `.vaked/cache` relative to
  the source file's directory).
- `--no-cache` — skip cache lookup and write; parse fresh and emit AST on
  stdout without updating the index.
- On success: JSON AST on stdout, exit 0.
- On parse error: diagnostics on stderr (file:line:col: message), exit 1.

---

## 6. JSON AST format

The output of `vakedc-zig parse` matches the Python `vakedc parse` JSON
structure so the Python checker can consume either without modification.

Top-level object:

```json
{
  "source_file": "path/to/file.vaked",
  "items": [ ... ]
}
```

Each item is either a `decl` or an `import`:

```json
{ "type": "import", "path": "...", "span": { "start": 0, "end": 10 } }

{
  "type":   "decl",
  "kind":   "fiber",
  "name":   "parse",
  "span":   { "start": 42, "end": 120 },
  "annotations": [],
  "signature":   null,
  "block": {
    "stmts": [
      {
        "type":   "assignment",
        "ident":  "engine",
        "op":     "=",
        "value":  { "type": "app", "ref": "vakedc-zig", "args": [], "record": null },
        "span":   { "start": 55, "end": 72 }
      }
    ]
  }
}
```

Spans are byte offsets from the start of the source file. The serializer also
emits `line` and `col` (1-based) on every span node for human-readable
diagnostics.

The Python `vakedc parse` command emits an identical structure; the AST schema
is the shared contract between the two implementations.

---

## 7. Provenance chain

Every parse result is content-addressed end-to-end:

```
source bytes
  └─ sha256(source)           = cache key  (objects lookup + index key field)
       └─ parse(source)       = AST bytes
            └─ sha256(AST)    = ref        (objects/<ref>)
                 └─ index entry: { seq, prev, key, artifact, ref, ts_iso, hash }
                      └─ sha256(entry)    = entry hash (chained in next entry's prev)
```

The provenance JSON (stored alongside the AST in `objects/`) records the full
chain: source hash → parser version → AST hash → index seq. Any downstream
consumer can verify the lineage of a cached AST without re-reading the source.

---

## 8. Cross-references

| Document | Relevance |
|----------|-----------|
| [0011 — type system](./0011-type-system.md) | Checker that consumes the JSON AST produced here |
| [0012 — lowering](./0012-lowering.md) | Lowerer that runs after the checker |
| [0014 — memory primitive](./0014-memory-primitive.md) | The runtime shape that ralphloop-cache instantiates at build time |
| [ralph PURPOSE.md](../../tools/ralph/PURPOSE.md) | Origin of the immutable hash-chained event log pattern |
| [vaked-v0-plus.ebnf](../../vaked/grammar/vaked-v0-plus.ebnf) | Grammar the parser implements (v0.3) |
| [vakedc-zig.vaked](../../vaked/examples/compiler/vakedc-zig.vaked) | Dogfeed: the compiler pipeline described in Vaked |
| [ralphloop-cache.vaked](../../vaked/examples/compiler/ralphloop-cache.vaked) | Isolated cache pattern example |
| [0017 — ralphloop primitive](./0017-ralphloop-cache.md) | Proposal to make the cached loop a first-class language kind |

---

## 9. Differential oracle & parity roadmap

A second, independent implementation of the grammar is a cheap, durable
**differential oracle**: `vakedc-zig parse` should accept exactly what the Python
reference `vakedc parse` accepts, and any divergence is a grammar-ambiguity bug
worth investigating. CI now compiles the binary (the `zig-build` job in
`spec-tests.yml`), so a broken `zig build` can no longer pass unnoticed.

Parity roadmap toward replacing the Python front-end on the hot path (the v1.0
native-rewrite line in docs/compiler/OPTIMIZATION_ROADMAP.md, which lands with
the optimization-pass PR #112):

1. **Differential-oracle CI:** assert `vakedc-zig parse` and `python3 -m vakedc
   parse` agree on every committed example; expand coverage as the parser grows.
2. Pin Zig in the flake devshell so `nix develop` provides the exact toolchain
   (today `packages.vakedc-zig` pins it for the build only).
3. Port `resolve` → `check` (0011), then `lower` (0012), incrementally, keeping
   the cache in front of each stage.

> Folds in the design intent from the parallel `vakedc-zig` v0.0.x scaffold (the
> optimization-pass PR): the subset framing and the differential-oracle idea.
> This note (0018) is the canonical v0.1.0 design.
