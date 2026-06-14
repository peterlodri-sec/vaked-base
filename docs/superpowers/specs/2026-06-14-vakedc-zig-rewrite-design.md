# vakedc → Zig rewrite (self-hosting port)

**Date:** 2026-06-14
**Status:** Design approved (brainstorm); plan + implementation to follow.
**Scope:** Port the entire `vakedc` compiler (lexer → parser → resolve → check → lower → emit), its CLI, and its canonical serialization from Python to Zig, gated stage-by-stage by an oracle that diffs the Zig output against the existing Python implementation.

---

## 1. Goal & motivation

Rewrite `vakedc` (currently ~4,889 lines of Python 3 stdlib across 9 modules) into Zig as a **self-hosting / dogfooding** exercise for the Vaked ecosystem. The point is not a line-by-line transliteration: it is to produce **Zig-idiomatic modules — a `vaked-core` library — that the Zig enforcement daemons can later import directly** (the LPG data model, the canonical JSON contract, and the diagnostics types). "Vaked declares · Zig enforces" converges when the compiler and the enforcement plane share the same Zig types.

Success = the Zig `vakedc` reproduces the Python compiler's behaviour exactly (per the fidelity bar in §4), across the full `vaked/examples/**` corpus and the committed golden fixtures, on all three subcommands; the Python implementation is then deleted.

## 2. Current Python implementation (the reference)

| Module | Lines | Role |
|--------|-------|------|
| `vakedc/lexer.py` | 388 | Tokenizer; NFC normalization; pinned Unicode version warning |
| `vakedc/parser.py` | 844 | Recursive-descent parser → AST items |
| `vakedc/graph.py` | 159 | LPG data model: `Span`, `Provenance`, `GraphNode`, `GraphEdge`, `Graph` |
| `vakedc/resolve.py` | 345 | AST items → resolved `Graph` (nodes + edges, external stubs) |
| `vakedc/check.py` | 1,277 | 0011 type system (stages 3–4): elaborate + check → `Diagnostic` list |
| `vakedc/lower.py` | 1,400 | 0012 lowering: clean graph → artifact tree + provenance manifest |
| `vakedc/emit.py` | 160 | Canonical JSON + SQLite serialization of the LPG |
| `vakedc/__main__.py` | 269 | CLI: `parse` / `check` / `lower` subcommands |
| `vakedc/__init__.py` | 47 | Pipeline wiring (`parse_string`, `parse_file`) |

Pipeline: `source → lex → parse(AST) → resolve(Graph) → check(diagnostics) → lower(artifact tree)`.

Externally observable artifacts (the oracle's comparison points):
- `graph.json` — after resolve (`parse` subcommand).
- `graph.db` — SQLite mirror of the graph (`parse --sqlite`).
- `diagnostics.json` — after check (`check --json`).
- artifact tree + `provenance.json` — after lower (`lower --out`).

### 2.1 Data model (to port verbatim into `vaked-core`)
- `Span{ byteStart, byteEnd, line, col }` — 1-based line/col, `byteEnd` exclusive.
- `Provenance{ file, decl, span }` — `decl` = `"<kind> <name>"`.
- `GraphNode{ id, kind, name, labels[], props{}, provenance? }`.
- `GraphEdge{ from, to, label, props{} }`.
- `Graph` — id-keyed node map + edge list; `ensure_external(head_path)` → one `external:<path>` stub per distinct head; `nodes_sorted()` by id; `edges_sorted()` by `(from, label, to, stable_props_key)`.
- Node id: `<filename>#<outer>/<inner>/…`; external: `external:<head-path>`.

### 2.2 CLI surface (to mirror exactly, incl. exit codes)
- `vakedc parse <file> [--json PATH] [--sqlite PATH] [--print]` — writes `.vaked/graph.json` + `.vaked/graph.db` by default; `--print` → canonical JSON to stdout. Exit `0` ok; `1` read/lex/parse error.
- `vakedc check <file> [--json] [--builtins PATH]` — human diagnostics → stderr, or canonical JSON → stdout with `--json`. `--builtins` overrides catalog (default `vaked/schema/builtins.vaked`, resolved relative to the binary). Exit `0` clean; `1` diagnostics present; `2` usage/read/parse error.
- `vakedc lower <file> [--out DIR] [--builtins PATH]` — parse → resolve → check → lower; **refuses to emit on any diagnostic** (0012 §1); writes artifact tree + `provenance.json` at the out root. Exit `0` emitted; `1` diagnostics/read/parse (nothing written); `2` usage.

## 3. Target architecture

**Approach B — `vaked-core` library + thin CLI.** Chosen over a monolith (A) because it is the only layout that delivers the self-hosting goal: the daemons import `vaked-core`. A full multi-package workspace (C) is premature.

```
zig/
  build.zig                 # pinned Zig; builds libvaked-core + vakedc exe + `zig build test`
  build.zig.zon
  src/
    core/                   # vaked-core — the shared library (daemons depend on this)
      span.zig
      provenance.zig
      graph.zig             # LPG model (port of graph.py)
      json_canon.zig        # canonical writer (two modes, see §4)
      diagnostic.zig        # Diagnostic + code enum + severity
    lex/lexer.zig
    parse/parser.zig        # AST node types
    resolve/resolve.zig     # AST -> Graph
    check/check.zig         # 0011 type system; loads builtins.vaked
    lower/lower.zig         # 0012 emitters -> artifact tree + provenance
    cli/main.zig            # parse/check/lower; exit codes mirror Python
```

The Python `vakedc/` package stays in place, **untouched**, as the oracle until the Zig port is 100% green; then it is deleted (migration step 5).

### 3.1 Memory
One **arena allocator per compile**: parse a file → build the graph → emit → free the arena in one shot. Strings are arena-copied or interned. No per-node frees; lifetime is the compilation.

### 3.2 Error handling (two channels, mirroring Python)
1. **Hard failures** (NFC failure, lex error, syntax error, IO error) are Zig errors (`error.LexError`, `error.SyntaxError`, …) carrying a source-mapped message → map to exit `1`/`2` at the CLI boundary. These match Python's `VakedLexError` / `VakedSyntaxError` / `OSError` paths.
2. **Semantic findings are data**, not errors: the checker returns a `std.ArrayList(Diagnostic)` (like Python's list), sorted `(file, byteStart, byteEnd, code)`; the CLI exits `1` iff it is non-empty.

## 4. Fidelity bar — canonical JSON contract

The equality bar for the oracle diff is a **canonical-form contract**, and it already largely exists in `emit.py` / `__main__.py`. We adopt the *existing* form (no reformatting churn) and formalize it in `vaked/schema/`. There are **two** modes; the Zig `json_canon.zig` must reproduce both byte-for-byte:

- **Graph mode** (`graph.json`): compact `separators=(",",":")`, **explicit fixed key order** per object (`node`: `id,kind,name,labels,props,provenance`; `edge`: `from,to,label,props`; `prov`: `file,decl,span`; `span`: `byteStart,byteEnd,line,col`), prop dict keys **recursively sorted**, lists preserve order, nodes sorted by id, edges by `(from,label,to,stable_props_key)`, document `{"version":1,"source":…,"nodes":[…],"edges":[…]}`, trailing `\n`, `ensure_ascii=False` (UTF-8 passthrough, no `\u` escaping).
- **Diagnostics mode** (`diagnostics.json`): `indent=2`, `sort_keys=True`, `ensure_ascii=False`, trailing `\n`, document `{"diagnostics":[…]}`.

Once both modes match Python on the corpus, the JSON form is documented in `vaked/schema/` as the artifact contract daemons rely on. The committed golden fixtures (`operator-field.graph.json`, `rejected.diagnostics.json`) are already in these forms, so fixture regeneration is expected to be a no-op (verified during step 0).

**Fidelity risk — float formatting.** The one real risk is number repr in `props` (e.g. constraint values). Most graph/diagnostic fields are ints/strings, so exposure is small. Mitigation: a targeted float-repr conformance test added in step 0, comparing Zig's float formatting to Python's `json.dumps` for the value forms that appear in the corpus; pick/encode a matching format before relying on it downstream.

## 5. Oracle harness

The migration is gated by an oracle that runs the **same inputs through both impls and `cmp`s the bytes**. `tests/spec/run_all.py` stays Python during the migration and is the natural driver; it is extended with an oracle mode that, per stage:

1. Runs each `vaked/examples/**.vaked` (and the golden-fixture inputs) through the Python `vakedc` and the Zig `vakedc`.
2. Byte-compares the stage's artifact (token dump / `graph.json` / `diagnostics.json` / artifact tree + `provenance.json`).
3. Reports the stage **green only at 100% match** across the corpus + golden fixtures.

A stage is not considered done until its oracle gate is green. The harness itself is ported to Zig **last** (optional; not required for the goal).

## 6. Migration order

Each stage is gated by the §5 oracle on the full corpus + golden fixtures before the next begins.

0. **Scaffold.** Pin Zig in `flake.nix`; create `zig/build.zig` + `build.zig.zon`; stub `vaked-core` + CLI; wire the oracle into `run_all.py`; add the float-repr conformance test; confirm golden fixtures are already canonical (no regen).
1. **lexer** — port `lexer.py`. Gate: a token-dump debug subcommand added to **both** impls, diffed over the corpus (tokens, spans, NFC behaviour, pinned-Unicode warning).
2. **parser + resolve** — port `parser.py` + `resolve.py` + the `vaked-core` graph model. Gate: `parse --print` (`graph.json`) vs Python + `operator-field.graph.json`.
3. **check** — port `check.py` (0011 stages 3–4), incl. loading/parsing `builtins.vaked`. Gate: `check --json` (`diagnostics.json`) vs Python + `rejected.diagnostics.json`.
4. **lower** — port `lower.py` + `emit.py` (0012 emitters). Gate: `lower --out` artifact tree + `provenance.json` byte-diff vs Python.
5. **Cutover.** Repoint `flake.nix` / docs / `.vaked` invocation to the Zig binary; delete Python `vakedc/`; optionally port `run_all.py` to Zig.

## 7. Decisions (locked)

- **Zig version pin — DECIDED: pin the latest stable Zig.** `flake.nix` currently ships bare `zig` (no pin) and Zig is not on `PATH` outside `nix develop`. Step 0 pins the **latest stable** Zig explicitly in `flake.nix` (exact version confirmed via `nix` / ziglang.org at step 0) so `build.zig` syntax and `std` APIs are fixed for the whole port.
- **SQLite (`graph.db`) — DECIDED: keep, and pin it.** Keep `graph.db` parity via `@cImport` of libsqlite3, with the **libsqlite3 version pinned** in `flake.nix` alongside Zig. Only the textual `canonical_dump` is determinism-tested (not file bytes), but the emit path is retained for full CLI parity.
- **Float formatting in props — DECIDED: targeted float-repr test added early (step 0).** Before any stage relies on number serialization, step 0 lands a conformance test comparing Zig's float formatting to Python's `json.dumps` across the value forms in the corpus; the matching format is fixed in `json_canon.zig` up front. (See also §4 fidelity risk.)
- **Builtins catalog.** The checker parses `vaked/schema/builtins.vaked` as its type catalog, so the checker stage depends on the Zig lexer+parser being green first — which the migration order already guarantees.

## 8. Out of scope

- The OTP/Zig **enforcement daemons** — separate subsystem (per `CLAUDE.md` conventions); they *consume* `vaked-core` later, in their own design → plan → impl cycle.
- `tools/specdash` — Python tooling, optional later port.
- Rewriting `tests/spec/run_all.py` and the rest of the Python test harness to Zig — optional, deferred to after cutover.

## 9. Testing strategy

- **Differential (primary):** the §5 oracle — Zig vs Python byte-for-byte over `vaked/examples/**` + golden fixtures, per stage. This is the correctness spine.
- **Golden:** the committed `tests/spec/golden/*.json` fixtures, byte-compared against both impls.
- **Unit (`zig build test`):** in-module Zig tests for `vaked-core` (graph id derivation, edge sort order, canonical JSON both modes, float-repr conformance) and per-stage edge cases.
- A stage merges only when its oracle gate is 100% green and `zig build test` passes.
