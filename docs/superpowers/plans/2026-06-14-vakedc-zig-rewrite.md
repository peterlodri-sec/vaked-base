# vakedc → Zig Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `vakedc` compiler from Python to Zig as a self-hosting `vaked-core` library + thin CLI, proven correct stage-by-stage by an oracle that byte-diffs Zig output against the existing Python implementation.

**Architecture:** Approach B from the spec — a reusable `vaked-core` Zig library (LPG data model, canonical JSON writer, diagnostics types) consumed by a thin `vakedc` CLI. One arena allocator per compile. Hard failures are Zig errors; semantic findings are data (`std.ArrayList(Diagnostic)`). The canonical JSON writer is hand-rolled for exact byte control (no `std.json`). Python `vakedc/` stays untouched as the oracle until 100% green, then is deleted.

**Tech Stack:** Zig **0.16.0** (pinned in `flake.nix`), `zg` Unicode library (NFC, pinned to Python's Unicode data version), libsqlite3 (pinned, via `linkSystemLibrary`), Python 3 (oracle harness in `tests/spec/`).

**Spec:** `docs/superpowers/specs/2026-06-14-vakedc-zig-rewrite-design.md`. Migration order (§6): scaffold → lexer → parser+resolve → check → lower → cutover.

**Scope of THIS plan:** Phase 0 (scaffold + `vaked-core` data model + canonical writer + float-repr test + oracle harness) and Phase 1 (lexer), producing the first oracle-green increment — a Zig `vakedc` that lexes the full corpus identically to Python. Phases 2–4 (parser+resolve, check, lower) each get their own detailed plan after this lands (each is a large, independently testable subsystem per the writing-plans scope rule). Their task outlines are in §"Phases 2–4 outline" for continuity.

**Conventions for every task below:**
- All Zig commands run **inside the dev shell**. Prefix: `nix --extra-experimental-features 'nix-command flakes' develop --command <cmd>`. The plan abbreviates this as `ND <cmd>`. (Define a shell alias `ND` once per session, or substitute the full prefix.)
- Zig binary after build: `zig/zig-out/bin/vakedc`.
- Working dir for Zig commands: `zig/` unless noted.

---

## Phase 0 — Scaffold

### Task 0.1: Pin Zig 0.16.0 + libsqlite3 + zg in flake.nix

**Files:**
- Modify: `flake.nix` (the `buildInputs`/`packages` list around line 21 where bare `zig` is listed)

- [ ] **Step 1: Confirm the current resolved versions**

Run: `nix --extra-experimental-features 'nix-command flakes' develop --command sh -c 'zig version; sqlite3 --version 2>/dev/null || echo "no sqlite3 cli"'`
Expected: prints `0.16.0` and (maybe) a sqlite version. Record both.

- [ ] **Step 2: Pin the toolchain explicitly**

Replace the bare `zig` line and add sqlite. Use the nixpkgs attribute that resolves to 0.16.0 (e.g. `zig_0_16` if available in the pinned nixpkgs, else keep `zig` but pin the `nixpkgs` input rev so it stays 0.16.0). Add `sqlite` (provides libsqlite3 + headers) to `buildInputs`. Document the pinned Unicode data version expectation in a comment (must match `python3 -c 'import unicodedata; print(unicodedata.unidata_version)'`).

```nix
# in the dev shell packages/buildInputs:
zig_0_16              # Zig enforces — pinned 0.16.0 for the vakedc self-hosting port
sqlite                # libsqlite3 + headers — vakedc `parse --sqlite` parity (pinned via nixpkgs rev)
```

If `zig_0_16` is not an attribute in the pinned nixpkgs, instead pin the `nixpkgs` flake input to a rev whose `zig` is 0.16.0 and leave `zig` as-is; record the rev in a comment.

- [ ] **Step 3: Verify**

Run: `nix --extra-experimental-features 'nix-command flakes' develop --command sh -c 'zig version && echo "#include <sqlite3.h>" | cc -E - >/dev/null 2>&1 && echo sqlite-header-ok'`
Expected: `0.16.0` then `sqlite-header-ok`.

- [ ] **Step 4: Commit**

```bash
git add flake.nix
git commit -m "build: pin Zig 0.16.0 + sqlite for the vakedc Zig port"
```

### Task 0.2: Scaffold the Zig project (build.zig, build.zig.zon, empty CLI)

**Files:**
- Create: `zig/build.zig`
- Create: `zig/build.zig.zon`
- Create: `zig/src/cli/main.zig`
- Create: `zig/.gitignore` (`zig-out/`, `.zig-cache/`)

- [ ] **Step 1: Write `zig/build.zig.zon`** (declare the package + the `zg` dependency; fill the exact `zg` URL + hash at impl time via `zig fetch`)

```zig
.{
    .name = .vakedc,
    .version = "0.0.0",
    .fingerprint = 0x0, // replace with the value `zig build` prints on first run
    .minimum_zig_version = "0.16.0",
    .dependencies = .{
        // added in Task 1.1 via: ND zig fetch --save git+https://codeberg.org/atman/zg
    },
    .paths = .{ "build.zig", "build.zig.zon", "src" },
}
```

- [ ] **Step 2: Write `zig/build.zig`** (library `vaked-core` + exe `vakedc` + `test` step; sqlite linked on the exe)

```zig
const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    // vaked-core: the shared library module (daemons import this later).
    const core_mod = b.addModule("vaked-core", .{
        .root_source_file = b.path("src/core/root.zig"),
        .target = target,
        .optimize = optimize,
    });

    // vakedc CLI executable. NOTE: libc + sqlite linking is added in Phase 2
    // (when `parse --sqlite` lands), together with the nix linker-path fix —
    // not at scaffold time, so the scaffold builds with zero system deps.
    const exe = b.addExecutable(.{
        .name = "vakedc",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    exe.root_module.addImport("vaked-core", core_mod);
    b.installArtifact(exe);

    const run = b.addRunArtifact(exe);
    if (b.args) |args| run.addArgs(args);
    const run_step = b.step("run", "Run vakedc");
    run_step.dependOn(&run.step);

    // Unit tests: run tests in every module reachable from core + cli.
    const core_tests = b.addTest(.{ .root_module = core_mod });
    const cli_tests = b.addTest(.{ .root_module = exe.root_module });
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&b.addRunArtifact(core_tests).step);
    test_step.dependOn(&b.addRunArtifact(cli_tests).step);
}
```

- [ ] **Step 3: Write a stub `zig/src/core/root.zig` and `zig/src/cli/main.zig`** so it builds

```zig
// zig/src/core/root.zig
pub const span = @import("span.zig");
test { _ = span; }
```

```zig
// zig/src/cli/main.zig
const std = @import("std");
pub fn main() !void {
    std.debug.print("vakedc (zig) — not yet implemented\n", .{});
}
```

(Also create a placeholder `zig/src/core/span.zig` with `pub const Span = struct {};` so the import resolves; it is fully implemented in Task 0.3.)

- [ ] **Step 4: Build, capture the fingerprint, and verify**

Run (in `zig/`): `nix --extra-experimental-features 'nix-command flakes' develop --command zig build`
Expected: first run prints the required `.fingerprint` value — paste it into `build.zig.zon` and rebuild. Then `zig build` succeeds and `zig-out/bin/vakedc` exists.

Run: `nix --extra-experimental-features 'nix-command flakes' develop --command ./zig-out/bin/vakedc`
Expected: `vakedc (zig) — not yet implemented`

- [ ] **Step 5: Commit**

```bash
git add zig/build.zig zig/build.zig.zon zig/.gitignore zig/src/core/root.zig zig/src/core/span.zig zig/src/cli/main.zig
git commit -m "build: scaffold zig/ — vaked-core lib + vakedc exe + test step"
```

### Task 0.3: Implement the LPG data model in `vaked-core` (port of graph.py)

**Files:**
- Create: `zig/src/core/value.zig` (the `Value` JSON-tree union — created here, imported by both `graph.zig` and `json_canon.zig` so there is no forward reference), `zig/src/core/span.zig`, `zig/src/core/provenance.zig`, `zig/src/core/graph.zig`
- Modify: `zig/src/core/root.zig` (export them)
- Test: in-module `test {}` blocks in `graph.zig`

Reference: `vakedc/graph.py` is the behavioral spec. Mirror `Span`, `Provenance`, `GraphNode`, `GraphEdge`, `Graph`, `ensure_external`, `nodes_sorted`, `edges_sorted`, `node_id`.

- [ ] **Step 1: Write the failing test** (`zig/src/core/graph.zig`, bottom)

```zig
test "node_id derivation matches python format" {
    const a = std.testing.allocator;
    const id = try nodeId(a, "operator-field.vaked", &.{ "operator-field" });
    defer a.free(id);
    try std.testing.expectEqualStrings("operator-field.vaked#operator-field", id);
    const id2 = try nodeId(a, "f.vaked", &.{ "outer", "inner" });
    defer a.free(id2);
    try std.testing.expectEqualStrings("f.vaked#outer/inner", id2);
}

test "ensure_external is idempotent per head path and sets kind/labels/props" {
    const a = std.testing.allocator;
    var g = Graph.init(a, "f.vaked");
    defer g.deinit();
    const n1 = try g.ensureExternal("agentGuardd.ringbuf");
    const n2 = try g.ensureExternal("agentGuardd.ringbuf");
    try std.testing.expectEqual(n1, n2); // same node, not a duplicate
    try std.testing.expectEqualStrings("external:agentGuardd.ringbuf", n1.id);
    try std.testing.expectEqualStrings("external", n1.kind);
}

test "edges_sorted orders by (from,label,to,props)" {
    // Build 3 edges out of order, assert canonical order. See graph.py edges_sorted.
}
```

- [ ] **Step 2: Run to verify it fails**

Run (in `zig/`): `ND zig build test`
Expected: FAIL — `Graph`/`nodeId`/`ensureExternal` not defined.

- [ ] **Step 3: Implement the data model**

`span.zig`:
```zig
pub const Span = struct {
    byteStart: usize,
    byteEnd: usize, // exclusive
    line: usize,    // 1-based
    col: usize,     // 1-based
};
```
`provenance.zig`:
```zig
const Span = @import("span.zig").Span;
pub const Provenance = struct {
    file: []const u8,
    decl: []const u8, // "<kind> <name>"
    span: Span,
};
```
`value.zig` — the JSON-value tree used for props:
```zig
pub const Value = union(enum) {
    null,
    bool: bool,
    int: i64,
    float: f64,
    string: []const u8,
    array: []Value,
    object: []Field, // key/value pairs; written in sorted-key order by json_canon
    pub const Field = struct { key: []const u8, value: Value };
};
```
`graph.zig` — implement `GraphNode{ id, kind, name, labels:[][]const u8, props:Value, provenance:?Provenance }`, `GraphEdge{ from, to, label, props:Value }`, and `Graph` with an id-keyed `std.StringArrayHashMap(GraphNode)` + an edge `std.ArrayList(GraphEdge)`. Props is `value.Value` (defined above), so props serialize canonically via the writer in Task 0.4. Implement:
- `pub fn nodeId(alloc, filename, chain: []const []const u8) ![]u8` — `<filename>#<join(chain,"/")>`.
- `Graph.init/deinit/addNode/getNode/hasNode/ensureExternal`.
- `Graph.nodesSorted()` — by id; `Graph.edgesSorted()` — by `(from,label,to,stablePropsKey)` where `stablePropsKey` is the canonical compact JSON of props (Task 0.4).

All allocations go through the arena the CLI passes in (graph borrows the allocator).

- [ ] **Step 4: Run to verify it passes**

Run (in `zig/`): `ND zig build test`
Expected: PASS.

- [ ] **Step 5: Export from `root.zig` and commit**

```zig
// root.zig
pub const Span = @import("span.zig").Span;
pub const Provenance = @import("provenance.zig").Provenance;
pub const graph = @import("graph.zig");
pub const Graph = graph.Graph;
pub const GraphNode = graph.GraphNode;
pub const GraphEdge = graph.GraphEdge;
test { _ = graph; }
```
```bash
git add zig/src/core/
git commit -m "feat(core): LPG data model (Span/Provenance/Graph) port of graph.py"
```

### Task 0.4: Hand-rolled canonical JSON writer (`json_canon.zig`) — both modes

**Files:**
- Create: `zig/src/core/json_canon.zig` (defines `Value` + `writeGraph` + `writeDiagnostics`)
- Modify: `zig/src/core/root.zig`
- Test: in-module tests

Reference: `vakedc/emit.py` (graph mode) and `vakedc/__main__.py:_diagnostics_json` (diagnostics mode).

The writer takes a `*std.Io.Writer` (0.16 writer interface — confirm exact type via `ND zig std` at impl) and emits bytes directly. **No `std.json`.**

- Reuses `value.Value` (defined in Task 0.3). Object keys are written in **sorted** order for props. Strings are written with JSON escaping but **UTF-8 passthrough** (no `\uXXXX` for non-ASCII; only escape `"`, `\`, and control chars `< 0x20`) to match `ensure_ascii=False`.
- **Graph mode** (`writeGraph`): compact (no spaces), fixed top-level/object key order (`version,source,nodes,edges`; node `id,kind,name,labels,props,provenance`; edge `from,to,label,props`; prov `file,decl,span`; span `byteStart,byteEnd,line,col`), nodes already `nodesSorted`, edges `edgesSorted`, props keys sorted recursively, trailing `\n`.
- **Diagnostics mode** (`writeDiagnostics`): `indent=2` pretty-print, **all** object keys sorted (`sort_keys=True`), trailing `\n`. Document `{"diagnostics":[...]}`.
- `stablePropsKey(alloc, props) ![]u8`: compact canonical JSON of a props value (used by `edgesSorted`).

- [ ] **Step 1: Write failing tests**

```zig
test "graph mode is compact with fixed key order and trailing newline" {
    // Build a tiny Graph with one external node; write to a buffer.
    // Expect exactly:
    // {"version":1,"source":"f.vaked","nodes":[{"id":"external:x","kind":"external","name":"x","labels":["external"],"props":{"external":true},"provenance":null}],"edges":[]}\n
}

test "string escaping: utf-8 passthrough, escape quote/backslash/control only" {
    // input string  he said "hi"\n→ é  → expect  he said \"hi\"\n→ é  with é byte-preserved (no é)
}

test "diagnostics mode is indent-2 with all keys sorted" {
    // One diagnostic; compare against the indented form from rejected.diagnostics.json shape.
}
```

- [ ] **Step 2: Run to verify failure**

Run (in `zig/`): `ND zig build test` → FAIL (writer not defined).

- [ ] **Step 3: Implement the writer** (direct byte emission; recursive `writeValue`; a `sortObjectKeys` helper; int via `std.fmt`, float via Task 0.5's chosen format).

- [ ] **Step 4: Run to verify pass**

Run (in `zig/`): `ND zig build test` → PASS.

- [ ] **Step 5: Export + commit**

```bash
git add zig/src/core/json_canon.zig zig/src/core/root.zig
git commit -m "feat(core): hand-rolled canonical JSON writer (graph + diagnostics modes)"
```

### Task 0.5: Float-repr conformance test (early, before any stage relies on numbers)

**Files:**
- Create: `tests/spec/float_repr_corpus.txt` (the float value forms that appear across `vaked/examples/**` — extract them)
- Test: `zig/src/core/json_canon.zig` (float test) + `tests/spec/test_float_repr.py`

Goal: pin one float format in `writeValue` that reproduces Python's `json.dumps` repr for every float value form in the corpus.

- [ ] **Step 1: Extract the float forms Python emits**

Run: `nix --extra-experimental-features 'nix-command flakes' develop --command python3 - <<'PY'` … iterate `vaked/examples/**/*.vaked` through `vakedc.parse_file` + `to_canonical_json`, regex-collect numeric tokens that contain `.`/`e`, and also run a set of edge values (`0.0`, `1.5`, `1e10`, `0.1`, `100.0`) through `json.dumps`. Write the `value\tpython_repr` pairs to `tests/spec/float_repr_corpus.txt`.
Expected: a small file of `<f64-literal>\t<python-json-repr>` lines.

- [ ] **Step 2: Write the failing Zig test** (`json_canon.zig`)

```zig
test "float repr matches python json.dumps for the corpus" {
    // Read tests/spec/float_repr_corpus.txt at comptime via @embedFile (copy it under zig/ or use a relative embed),
    // for each (value, expected) assert writeFloat(value) == expected.
}
```

- [ ] **Step 3: Run → FAIL**, then implement `writeFloat` to match (Python uses `repr(float)` semantics — shortest round-tripping decimal; Zig: `std.fmt.format` with `{d}` is shortest round-trip in 0.16 — verify each corpus pair; handle integer-valued floats `100.0` → Python emits `100.0`, Zig `{d}` emits `100` so add the `.0` suffix rule to match).

- [ ] **Step 4: Run → PASS** (`ND zig build test`), and add `tests/spec/test_float_repr.py` to `run_all.py` so regressions in the corpus file are caught Python-side too.

- [ ] **Step 5: Commit**

```bash
git add zig/src/core/json_canon.zig tests/spec/float_repr_corpus.txt tests/spec/test_float_repr.py tests/spec/run_all.py
git commit -m "test(core): float-repr conformance — Zig writeFloat matches python json.dumps"
```

### Task 0.6: Oracle harness (`tests/spec/oracle.py`) + run_all wiring

**Files:**
- Create: `tests/spec/oracle.py`
- Modify: `tests/spec/run_all.py` (register an `oracle` mode, opt-in via env `VAKEDC_ZIG=zig/zig-out/bin/vakedc`)

The oracle runs the **same inputs** through Python `vakedc` and the Zig binary for a given stage and byte-compares. It is the correctness spine for every stage.

- [ ] **Step 1: Write `oracle.py`** with:
  - `corpus()` → all `vaked/examples/**/*.vaked` plus the golden-fixture source files.
  - `run_py_stage(stage, file)` and `run_zig_stage(stage, file)` → return the stage artifact **bytes** (stdout for `parse --print` / `check --json`; the token dump for `lex`; a deterministic concatenation of the artifact tree for `lower`).
  - `diff_stage(stage)` → for each corpus file, compare bytes; collect mismatches as `(file, first-differing-offset, py_excerpt, zig_excerpt)`.
  - A `__main__` that takes `stage` argv, prints a PASS/FAIL summary and a non-zero exit on any mismatch. Skips (with a clear message) if `VAKEDC_ZIG` is unset or the binary is missing.

- [ ] **Step 2: Wire into `run_all.py`**: when `VAKEDC_ZIG` is set, run `oracle.diff_stage(s)` for each implemented stage and fail the suite on mismatch. When unset, print `oracle: skipped (set VAKEDC_ZIG to enable)` and pass.

- [ ] **Step 3: Smoke test it** (no stages implemented yet → the only enabled stage is whatever Phase 1 adds; for now assert it runs and skips cleanly without the env var)

Run: `nix --extra-experimental-features 'nix-command flakes' develop --command python3 tests/spec/run_all.py`
Expected: existing suite passes; `oracle: skipped` line present.

- [ ] **Step 4: Commit**

```bash
git add tests/spec/oracle.py tests/spec/run_all.py
git commit -m "test: oracle harness — byte-diff Zig vs Python per stage (opt-in via VAKEDC_ZIG)"
```

---

## Phase 1 — Lexer

Reference: `vakedc/lexer.py` (388 lines) is the behavioral spec — token kinds, NFC normalization, the pinned-Unicode-version warning, error positions. `tests/spec/lex_vaked.py` shows the existing Python lexer test surface.

### Task 1.1 — REVISED: defer `zg`; NFC is passthrough (corpus is 100% NFC-stable)

**Phase-0 finding (2026-06-14):** scanning the corpus, **14/16 `.vaked` files contain
non-ASCII bytes, but ZERO files change under `unicodedata.normalize('NFC', src)`** —
every source (and `builtins.vaked`) is already in NFC. So Python's unconditional
NFC normalization is a **no-op over the entire corpus**.

**Decision:** the Zig lexer implements NFC as **UTF-8 passthrough** (validate UTF-8,
emit bytes unchanged) and reproduces the pinned-Unicode-version **warning** to
stderr. This is byte-identical to Python for all NFC-stable input — i.e. the whole
corpus — so the lexer oracle passes **without the `zg` dependency**. The `zg`
fetch/pin is therefore **deferred** to when a genuinely non-NFC input appears
(the oracle would flag the divergence). This removes a network/dep/API risk from
Phase 1 entirely.

**Documented gap (not silent):** a source that is NOT already NFC would be passed
through unchanged by Zig while Python would compose it — a divergence the oracle
catches. Tracked in the design spec §4 fidelity risk. The original `zg`-based task
is preserved below for when that day comes.

<details><summary>Deferred: original Task 1.1 (add the <code>zg</code> Unicode dependency)</summary>

#### Task 1.1: Add the `zg` Unicode dependency, pinned to Python's Unicode version

**Files:**
- Modify: `zig/build.zig.zon`, `zig/build.zig`

- [ ] **Step 1: Determine Python's Unicode data version** — RESOLVED during Phase 0:
  - `unicodedata.unidata_version` (runtime, what `normalize('NFC')` actually uses) = **16.0.0**.
  - `vakedc/lexer.py:PINNED_UNICODE` = **"15.1.0"** — a *declared* expectation that currently mismatches the runtime, so the lexer emits its version-mismatch warning to **stderr**.
  - **Therefore pin `zg` to Unicode 16.0.0 tables** (match the runtime that drives Python's NFC), NOT 15.1.0. The Zig lexer must also reproduce the stderr warning bytes (warn when its Unicode-data version != `"15.1.0"`), but since the oracle diffs the **stdout** token dump, warning parity is checked separately (stderr compare) and does not affect the token-stream gate.

- [ ] **Step 2: Fetch + pin `zg`**

Run (in `zig/`): `ND zig fetch --save git+https://codeberg.org/atman/zg#<tag-matching-unicode-version>`
Then in `build.zig`, add the dependency to `core_mod`:
```zig
const zg = b.dependency("zg", .{ .target = target, .optimize = optimize });
core_mod.addImport("Normalize", zg.module("Normalize"));
```
(Confirm the exact module name `zg` exposes for NFC via its `build.zig.zon`/README at fetch time.)

- [ ] **Step 3: Verify it builds**

Run (in `zig/`): `ND zig build` → succeeds.

- [ ] **Step 4: Commit**

```bash
git add zig/build.zig zig/build.zig.zon
git commit -m "build(core): add zg Unicode dep (NFC), pinned to python unidata version"
```

</details>

### Task 1.2: Define the canonical token-dump contract in BOTH impls

**Files:**
- Modify: `vakedc/__main__.py` (add a hidden `lex` subcommand: `vakedc lex <file>` → token dump to stdout)
- Create: `zig/src/lex/token.zig` (Token + Kind enum mirroring `lexer.py`)

Dump format (one token per line, `\t`-separated, trailing `\n`), chosen to be byte-stable and to expose every field the Python lexer carries:
```
<KIND>\t<byteStart>\t<byteEnd>\t<line>\t<col>\t<json-escaped-text>
```
`<KIND>` = the token kind name exactly as `lexer.py` names it. `<json-escaped-text>` uses the same UTF-8-passthrough escaping as `json_canon.zig` (so the dumps are comparable byte-for-byte). End the dump with a final `EOF\t...` token if Python emits one.

- [ ] **Step 1: Read `vakedc/lexer.py`** and enumerate the exact `Token` fields + kind names; mirror them in `token.zig` and in the Python `lex` dumper.

- [ ] **Step 2: Implement the Python `lex` subcommand** in `__main__.py` (calls `vakedc.lexer.tokenize`, prints the dump). This only **adds** a command — existing behavior unchanged.

- [ ] **Step 3: Verify the Python dump on one example**

Run: `nix … develop --command python3 -m vakedc lex vaked/examples/operator-field.vaked | head`
Expected: token lines in the format above.

- [ ] **Step 4: Commit**

```bash
git add vakedc/__main__.py zig/src/lex/token.zig
git commit -m "feat: canonical token-dump contract (python `lex` cmd + zig Token types)"
```

### Task 1.3: Port the lexer to Zig (`src/lex/lexer.zig`) + `vakedc lex`

**Files:**
- Create: `zig/src/lex/lexer.zig`
- Modify: `zig/src/cli/main.zig` (add `lex` subcommand → token dump)
- Modify: `zig/src/core/root.zig` (export lex if shared) — or keep lex under cli; decide by whether the parser (Phase 2) needs it from core (it does → put `lex` in core).

- [ ] **Step 1: Write a failing oracle-style Zig test** on a small inline source covering identifiers, strings, numbers, punctuation, comments, and a non-ASCII identifier requiring NFC. Assert the Zig token dump equals a hardcoded expected dump derived from the Python lexer for that snippet.

- [ ] **Step 2: Run → FAIL** (`ND zig build test`).

- [ ] **Step 3: Implement `tokenize`** porting `lexer.py`: NFC-normalize the source via `zg` first (matching `unicodedata.normalize('NFC', src)`), emit the pinned-Unicode-version warning to stderr on version mismatch (match Python's message bytes), produce tokens with byte/line/col spans identical to Python. Wire `vakedc lex <file>` in `main.zig`.

- [ ] **Step 4: Run → PASS** unit test, then **build the binary**: `ND zig build`.

- [ ] **Step 5: Run the oracle gate over the FULL corpus**

Run: `nix … develop --command sh -c 'VAKEDC_ZIG=$PWD/zig/zig-out/bin/vakedc python3 tests/spec/oracle.py lex'`
Expected: `lex: PASS (<N>/<N> files byte-identical)`. Investigate and fix any mismatch (first-differing-offset is reported) until 100%.

- [ ] **Step 6: Commit**

```bash
git add zig/src/lex/ zig/src/cli/main.zig zig/src/core/root.zig
git commit -m "feat(lex): Zig lexer — token stream byte-identical to Python over the corpus"
```

### Task 1.4: Lock the lexer gate into the suite

**Files:**
- Modify: `tests/spec/run_all.py` (enable the `lex` oracle stage when `VAKEDC_ZIG` is set)

- [ ] **Step 1:** Add `lex` to the oracle stages run by `run_all.py`.
- [ ] **Step 2: Verify the whole suite green with the Zig binary present**

Run: `nix … develop --command sh -c 'VAKEDC_ZIG=$PWD/zig/zig-out/bin/vakedc python3 tests/spec/run_all.py'`
Expected: all existing tests pass + `oracle lex: PASS`.

- [ ] **Step 3: Commit**

```bash
git add tests/spec/run_all.py
git commit -m "test: gate the lexer stage in run_all.py via the oracle"
```

**Phase 1 done = the first oracle-green increment:** a Zig `vakedc` that lexes the entire corpus byte-identically to Python.

---

## Phases 2–4 outline (each gets its own detailed plan before execution)

Per the writing-plans scope rule, the three remaining stages are large, independently-testable subsystems and each warrants its own detailed plan written when its predecessor is green. Outline for continuity:

**Phase 2 — Parser + Resolve → `graph.json`.** Port `parser.py` (AST node types + recursive-descent) and `resolve.py` (AST → `Graph`, external stubs, provenance spans per 0012 §6.2). Wire `vakedc parse <file> [--json|--sqlite|--print]` in `main.zig` using `json_canon.writeGraph` + the sqlite emit (Task: `@cImport`/`linkSystemLibrary` sqlite, port `emit.py:to_sqlite`). **Gate:** oracle `parse` stage — `parse --print` bytes vs Python + `tests/spec/golden/operator-field.graph.json`, over the full corpus. Also `--sqlite` via `canonical_dump` textual comparison.

**Phase 3 — Check → `diagnostics.json`.** Port `check.py` (0011 stages 3–4 type system): elaborate, conformance, constraints, capability attenuation, etc. Load + parse `vaked/schema/builtins.vaked` as the catalog (depends on Phase 1+2 being green). Wire `vakedc check <file> [--json] [--builtins PATH]` using `json_canon.writeDiagnostics`, exit codes 0/1/2. **Gate:** oracle `check` stage — `check --json` bytes vs Python + `tests/spec/golden/rejected.diagnostics.json`, over the full corpus (incl. the rejecting examples).

**Phase 4 — Lower → artifact tree + `provenance.json`.** Port `lower.py` (0012 emitters) + the artifact-tree writer from `__main__.py:_write_tree`. Refuse to emit on any diagnostic (0012 §1). Wire `vakedc lower <file> [--out DIR] [--builtins PATH]`, exit codes. **Gate:** oracle `lower` stage — byte-diff the full emitted tree + `provenance.json` vs Python over the corpus.

**Cutover (after Phase 4 green):** repoint `flake.nix`/docs/`.vaked` invocation to the Zig binary; delete Python `vakedc/`; optionally port `tests/spec/run_all.py` to Zig.

---

## Self-review

- **Spec coverage:** §1 goal → plan goal/arch. §2 reference → tasks reference each Python module. §2.1 data model → Task 0.3. §2.2 CLI → `lex` in 1.3, `parse/check/lower` in Phases 2–4. §3 architecture (vaked-core lib + CLI) → Task 0.2/0.3. §3.1 arena → noted in 0.3/build. §3.2 error channels → 0.3/Phase 3. §4 canonical JSON two modes → Task 0.4. §4 float risk → Task 0.5. §5 oracle → Task 0.6 + per-stage gates. §6 migration order → Phases 0–4 + cutover. §7 decisions: Zig pin → 0.1; sqlite pin → 0.1 + Phase 2; float test → 0.5; builtins ordering → Phase 3. §8 out of scope → not planned. §9 testing → oracle + golden + `zig build test` throughout. **No gaps in Phases 0–1; Phases 2–4 deliberately outlined, to be detailed before execution.**
- **Placeholder scan:** Two intentional fill-at-impl values remain and are unavoidable for a fresh Zig project: the `build.zig.zon` `.fingerprint` (Zig prints it on first build — Task 0.2 Step 4) and the `zg` URL/hash/module-name (resolved by `zig fetch --save` — Task 1.1). Both have explicit resolution steps, not vague TODOs.
- **Type consistency:** `Span`/`Provenance`/`GraphNode`/`GraphEdge`/`Graph`/`nodeId`/`ensureExternal`/`nodesSorted`/`edgesSorted` used consistently across 0.3/0.4. `Value` is defined in `core/value.zig` in Task 0.3 and imported by both `graph.zig` (as the props type) and `json_canon.zig` (Task 0.4) — no forward reference. `writeGraph`/`writeDiagnostics`/`writeFloat`/`stablePropsKey` consistent across 0.4/0.5.
