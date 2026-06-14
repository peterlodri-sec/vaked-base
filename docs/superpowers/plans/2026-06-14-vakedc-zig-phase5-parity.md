# vakedc Zig — Phase 5 (Parity Gaps) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three remaining feature-parity gaps so the Zig `vakedc` is a complete drop-in for the Python compiler — each gap landed with a differential-oracle gate proving Zig == Python while Python still arbitrates.

**Architecture:** Phase 5 is the lead sub-project of the completion spec (`docs/superpowers/specs/2026-06-14-vakedc-zig-completion-design.md`, `765e9e3`). It runs with Python present; the differential oracle (`tests/spec/oracle.py`, gated by `VAKEDC_ZIG`) is the correctness spine. Phases 6–8 (golden freeze → cutover → harness port) follow in their own cycles.

**Tech Stack:** Zig 0.16.0 (pinned, `zig/build.zig.zon`), Python 3 reference compiler (`vakedc/`), `libsqlite3` (nix `sqlite`), `zg` Unicode-16 library (NFC). Dev shell entry for every Zig/Python command: `nix --extra-experimental-features 'nix-command flakes' develop --command <cmd>` run from the repo root (`$REPO`).

---

## Context

Phases 0–4 ported the four compiler stages (lex → parse → check → lower) to Zig, byte-identical to Python over the 15-file corpus, oracle-gated. Three features were deliberately deferred and remain Python-only:

- **5a — SQLite emit** (`parse --sqlite PATH`): not in Zig (`build.zig:53` "SQLite is out of scope"; `main.zig:369-371` recognises `--sqlite` then *skips* its PATH).
- **5b — NFC handling**: Zig does UTF-8 passthrough (`lexer.zig:10-15`); real Python behaviour is to **reject** non-NFC source.
- **5c — `matches` matcher**: **already ported** during Phase 3 (see discrepancy); only the oracle gate + fixtures are missing.

This plan closes all three, each behind an oracle gate, and adds permanent corpus fixtures. It does **not** touch Phases 6–8.

### Discrepancies (both forced by the byte-equality-to-Python contract)

1. **5c matcher is done.** `vakedc/check.py`'s `_check_matches` / `_regex_dialect_error` are already mirrored in `zig/src/check/checker.zig`: `checkMatches` (:824, called at :1267), `regexDialectError`→`E-SCHEMA-BAD-REGEX` (:711, emitted :1026), the String/Path-only `E-SCHEMA-REFINEMENT` guard (:1020-1023), and a `Regex` engine (:854+, unit-tested :1767). The comment at :844-848 states the bound-value path is "not byte-gated today" because no corpus file exercises it. **5c = add pass+fail fixtures + assert the existing oracle `check` stage gates them.** No matcher code unless a fixture pattern exceeds the engine's subset (kept simple to avoid that).
2. **5b rejects, does not normalize.** `vakedc/lexer.py:120-141` calls `unicodedata.is_normalized("NFC", src)` and, if false, raises `VakedLexError("source is not Unicode-NFC-normalized (normalize the file to NFC)", filename, line, col)` at the first divergent codepoint. It never transforms bytes. Zig must reproduce this **rejection** (same message, same first-divergence span, exit 1). The new non-NFC `.vaked` is a **negative** fixture (both impls reject). **The spec text says "normalize" — that is wrong; match Python's reject. Flag for spec correction in the PR.** Pin `zg` to **Unicode 16.0.0** to match Python's *runtime* `unicodedata.unidata_version` (16.0.0), not the cosmetic `PINNED_UNICODE="15.1.0"` (stderr-only warning, not oracle-compared). **A pure-Zig minimal-table quick-check is explicitly rejected:** it would only cover the one fixture's combining mark, not arbitrary non-NFC input, breaking true Python parity at the Phase-7 cutover. Correctness over dependency-avoidance here.

---

## File Structure

**Create**
- `zig/src/emit/root.zig` — entry for a new `vaked-emit` module (re-exports `sqlite.zig`). A **sibling** module, NOT inside `vaked-core`, so `vaked-core` stays dependency-free for the daemons that will consume it (the libc+sqlite3 link lives only in `vaked-emit` + the exe).
- `zig/src/emit/sqlite.zig` — `@cImport("sqlite3.h")` + `emitSqlite(alloc, graph, path)`; ports `vakedc/emit.py:to_sqlite` (schema + inserts) verbatim.
- `vaked/examples/check/matches-pass.vaked` — binds a `matches`-constrained field to a matching value (checks clean).
- `vaked/examples/check/matches-fail.vaked` — binds it to a non-matching value (→ one `E-CONSTRAINT-MATCHES`).
- `vaked/examples/lex/non-nfc.vaked` — contains a decomposed (non-NFC) codepoint; both impls reject at lex.
- **Fixture placement:** new fixtures go in NEW subdirs (`lex/`, `check/`) **outside** `test_examples_parse`'s explicit globs, so `EXPECTED_VAKED_COUNT` stays **15** and that test is untouched. The oracle's recursive `vaked/examples/**/*.vaked` glob covers them automatically.

**Modify**
- `zig/build.zig` — add the `vaked-emit` module with `link_libc = true` + `linkSystemLibrary("sqlite3", .{})`; have the exe import it; add `emit_tests` to the test step. Add the `zg` import to the `vaked-lex` module.
- `zig/build.zig.zon` — add the `zg` dependency (Unicode-16 tag).
- `zig/src/cli/main.zig` — in `cmdParse` (:361-441), capture `--sqlite PATH` (currently skipped at :369-371) and call `emit.emitSqlite` after the graph is built (:433).
- `zig/src/lex/lexer.zig` — replace the UTF-8-passthrough NFC behaviour (:10-15) with a real NFC reject gate via `zg`, producing the same `ErrInfo` Python's `VakedLexError` yields.
- `tests/spec/oracle.py` — add a `"sqlite"` stage to `ENABLED_STAGES` (:61) + a `diff_sqlite` comparator that compares `canonical_dump` text of both impls' DBs.
- `tests/spec/test_vakedc_check.py` — in `_test_all_examples`, extend the clean-check skip-set to `{rejected.vaked, non-nfc.vaked, matches-fail.vaked}`, move the basename-skip **above** the `check_source` call (else `check_source` raises `VakedLexError` on `non-nfc.vaked`), and adjust the summary denominator to exclude skipped files. `test_examples_parse.py` is **unchanged** (count stays 15).

---

## Verification commands (used throughout)

- Build: `nix --extra-experimental-features 'nix-command flakes' develop --command sh -c 'cd zig && zig build'` → `zig/zig-out/bin/vakedc`.
- Zig unit tests: `… develop --command sh -c 'cd zig && zig build test'`.
- Python suite: `… develop --command python3 tests/spec/run_all.py`.
- **Oracle gate (the bar):** `… develop --command sh -c 'VAKEDC_ZIG="$PWD/zig/zig-out/bin/vakedc" python3 tests/spec/run_all.py'`.

---

## Task 5a — SQLite emit + oracle gate

**Files:** Create `zig/src/emit/{root,sqlite}.zig`; Modify `zig/build.zig`, `zig/src/cli/main.zig`, `tests/spec/oracle.py`.

**Python reference (`vakedc/emit.py`) — port verbatim:**

Schema (`emit.py:85-105`):
```sql
CREATE TABLE nodes (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
    labels TEXT NOT NULL, props TEXT NOT NULL,
    prov_file TEXT, prov_decl TEXT,
    byte_start INTEGER, byte_end INTEGER, line INTEGER, col INTEGER
);
CREATE TABLE edges (src TEXT NOT NULL, dst TEXT NOT NULL, label TEXT NOT NULL, props TEXT NOT NULL);
```
- `labels`/`props` serialized by `_dump_json(v) = json.dumps(_canon_value(v), separators=(",",":"), ensure_ascii=False)` — **canonical compact JSON** (recursively sorted keys, lists in order, UTF-8 passthrough). Exactly what `zig/src/core/json_canon.zig`'s compact writer produces for `graph.json`; reuse it (`writeValueCompact` for `props`; encode `labels` `[]const []const u8` as a compact JSON string array).
- Node provenance columns from `prov.file`, `prov.decl`, `prov.span.{byteStart,byteEnd,line,col}`; all `NULL` when `node.provenance == null`.
- Edges: `e.source→src`, `e.target→dst`, `e.label→label`, `_dump_json(e.props)→props`.
- `canonical_dump(path)` (`emit.py:141-160`) — the oracle's comparison text: `SELECT id,kind,name,labels,props,prov_file,prov_decl,byte_start,byte_end,line,col FROM nodes ORDER BY id` → each row `"NODE\t"+tab-join(fields, NULL→"")`; then `SELECT src,label,dst,props FROM edges ORDER BY src,label,dst,props` → `"EDGE\t"+tab-join`; lines joined `"\n"` + trailing `"\n"`. **Zig does not reimplement this** — the oracle runs Python's `canonical_dump` on both DB files.

- [ ] **Step 1: Spike the nix sqlite link.** Add `zig/src/emit/sqlite.zig` with `const c = @cImport({ @cInclude("sqlite3.h"); }); pub fn version() [*:0]const u8 { return c.sqlite3_libversion(); }` and a `test` that prints it. Wire a minimal `vaked-emit` module in `build.zig`: `mod.link_libc = true; mod.linkSystemLibrary("sqlite3", .{});`. Run `… zig build test`. `linkSystemLibrary` uses pkg-config; nix `sqlite` ships `sqlite3.pc`. If header/symbol unresolved, add explicit `mod.addIncludePath`/`mod.addLibraryPath` from `$NIX_CFLAGS_COMPILE`/`$NIX_LDFLAGS`, or set `PKG_CONFIG_PATH`. **Expected:** prints the libsqlite3 version; test passes. (Risk #1 — solve before writing emit logic.)

- [ ] **Step 2: Write `emitSqlite`.** In `zig/src/emit/sqlite.zig`:
```zig
const std = @import("std");
const core = @import("vaked-core");
const json_canon = core.json_canon;
const c = @cImport({ @cInclude("sqlite3.h"); });

const SCHEMA =
    \\CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
    \\  labels TEXT NOT NULL, props TEXT NOT NULL, prov_file TEXT, prov_decl TEXT,
    \\  byte_start INTEGER, byte_end INTEGER, line INTEGER, col INTEGER);
    \\CREATE TABLE edges (src TEXT NOT NULL, dst TEXT NOT NULL, label TEXT NOT NULL, props TEXT NOT NULL);
;

pub fn emitSqlite(alloc: std.mem.Allocator, graph: *core.Graph, path: []const u8) !void {
    const cpath = try alloc.dupeZ(u8, path);
    var db: ?*c.sqlite3 = null;
    if (c.sqlite3_open(cpath.ptr, &db) != c.SQLITE_OK) return error.SqliteOpen;
    defer _ = c.sqlite3_close(db);
    if (c.sqlite3_exec(db, "BEGIN", null, null, null) != c.SQLITE_OK) return error.SqliteExec;
    if (c.sqlite3_exec(db, SCHEMA, null, null, null) != c.SQLITE_OK) return error.SqliteExec;
    // prepared INSERT INTO nodes(...) VALUES(?,...): bind id/kind/name (text);
    // labels = compact-JSON string array; props = json_canon.writeValueCompact(node.props);
    // provenance: sqlite3_bind_int64 for byte_start/byte_end/line/col, sqlite3_bind_text for
    // prov_file/prov_decl, or sqlite3_bind_null for all six when node.provenance == null.
    // Iterate graph.nodes.values() (order irrelevant — canonical_dump re-sorts).
    // prepared INSERT INTO edges(...) over graph.edges.items.
    if (c.sqlite3_exec(db, "COMMIT", null, null, null) != c.SQLITE_OK) return error.SqliteExec;
}
```
Bind text with the SQLITE_TRANSIENT destructor (resolve the exact constant cast in Step 1's spike). Build `labels`/`props` JSON into arena buffers, then bind. Export from `zig/src/emit/root.zig`: `pub const emitSqlite = @import("sqlite.zig").emitSqlite;`.

- [ ] **Step 3: Unit-test emit + readback.** Build a small `core.Graph` (one node WITH provenance + labels + props, one node WITHOUT provenance → all-NULL trailing cols, one edge with props), call `emitSqlite` to a temp path, read back via `c.sqlite3` `SELECT … ORDER BY id`, assert exact column bytes (ints via `sqlite3_column_int64`+`{d}`; NULL→empty). Run `… zig build test`. **Expected:** PASS. (Risk #2 — int/NULL rendering parity.)

- [ ] **Step 4: Wire the CLI.** In `zig/src/cli/main.zig` `cmdParse`, replace the `--sqlite` skip at :369-371:
```zig
} else if (std.mem.eql(u8, a, "--json")) {
    i += 1; // unused here
} else if (std.mem.eql(u8, a, "--sqlite")) {
    i += 1;
    if (i < args.len) sqlite_path = args[i];
}
```
Add `var sqlite_path: ?[]const u8 = null;` near `file`/`print_`. After `buildGraph` (~:433), before `return 0`: `if (sqlite_path) |sp| try emit.emitSqlite(alloc, &graph, sp);`. Add `const emit = @import("vaked-emit");` and `exe.root_module.addImport("vaked-emit", emit_mod);` in `build.zig`.

- [ ] **Step 5: Build + spot-check.** `… zig build`; `zig/zig-out/bin/vakedc parse vaked/examples/primitives/mesh.vaked --sqlite /tmp/m.db`; `sqlite3 /tmp/m.db 'SELECT count(*) FROM nodes;'`. **Expected:** DB written, count matches the graph.

- [ ] **Step 6: Add the oracle `sqlite` stage.** In `tests/spec/oracle.py`: append `"sqlite"` to `ENABLED_STAGES` (:61). Add a comparator reusing Python's `emit.canonical_dump`:
```python
def diff_sqlite(zig_bin):
    from emit import canonical_dump  # vakedc.emit
    results, ok = [], True
    for rel in corpus():
        f = os.path.join(REPO_ROOT, rel)
        with tempfile.TemporaryDirectory() as td:
            pdb, zdb = os.path.join(td, "py.db"), os.path.join(td, "zig.db")
            prc = run([sys.executable, "-m", "vakedc", "parse", f, "--sqlite", pdb])
            zrc = run([zig_bin, "parse", f, "--sqlite", zdb])
            if prc.returncode != zrc.returncode: ok = False; ...; continue
            if prc.returncode != 0:  # both errored (e.g. non-nfc) → no DB to dump
                continue
            if canonical_dump(pdb) != canonical_dump(zdb): ok = False; ...
    return ok, results
```
Guard the stage dispatch so `sqlite` calls `diff_sqlite` (like `lower` calls `diff_lower`), not the generic stdout comparator. `canonical_dump` is impl-independent (reads any sqlite file) → the agreed gate text (spec §3).

- [ ] **Step 7: Run the oracle.** `… develop --command sh -c 'VAKEDC_ZIG="$PWD/zig/zig-out/bin/vakedc" python3 tests/spec/run_all.py'`. **Expected:** `sqlite` byte-identical over all corpus files; suite green.

- [ ] **Step 8: Commit.**
```bash
git add zig/src/emit zig/build.zig zig/src/cli/main.zig tests/spec/oracle.py
git commit -m "feat(vakedc): Zig SQLite emit (parse --sqlite), oracle-gated via canonical_dump"
```

---

## Task 5b — NFC reject gate + negative fixture

**Files:** Modify `zig/build.zig.zon`, `zig/build.zig`, `zig/src/lex/lexer.zig`, `tests/spec/test_vakedc_check.py`; Create `vaked/examples/lex/non-nfc.vaked`.

**Python reference (`lexer.py:120-141`):** reject non-NFC; message `"source is not Unicode-NFC-normalized (normalize the file to NFC)"`; span = first codepoint where `src` diverges from `unicodedata.normalize("NFC", src)` (1-based line/col, advance line on `\n`).

- [ ] **Step 1: Spike the `zg` NFC API.** **Source (codeberg is inaccessible here):** use the GitHub mirror `https://github.com/neurocyte/zg` ("Mirror of codeberg.org/atman/zg"). Pick the tag whose Unicode data is **16.0.0** (matches Python runtime `unicodedata.unidata_version`). Add it: `… develop --command sh -c 'cd zig && zig fetch --save git+https://github.com/neurocyte/zg#<tag>'`. **Fallbacks if git remotes are blocked:** the release tarball `… zig fetch --save https://codeberg.org/atman/zg/archive/<tag>.tar.gz`, or vendor the package under `zig/vendor/zg` and `--save` a `path` dependency. Write a throwaway test that NFC-normalizes `"e\u{0301}"` and asserts it differs from the input and equals `"é"`. Run `… zig build test`. **Expected:** confirms the exact API (`Normalize`/`NormData` init + the normalize call), the shipped Unicode version (must be 16.0.0 — verify in the mirror's README/`build.zig.zon`), and that the corpus stays NFC-stable (all 15 real files normalize to themselves). Record the API for Step 3.

- [ ] **Step 2: Write the negative fixture.** Create `vaked/examples/lex/non-nfc.vaked` — a syntactically valid declaration whose source contains a decomposed codepoint (e.g. `e` + U+0301 instead of precomposed `é`) in a name or string. Confirm Python rejects: `… develop --command sh -c 'python3 -m vakedc lex vaked/examples/lex/non-nfc.vaked; echo exit=$?'`. **Expected:** exit 1 + the NFC error. Note the exact stdout/stderr split — the oracle compares **stdout + exit code**.

- [ ] **Step 3: Implement the NFC gate.** In `zig/src/lex/lexer.zig`, before the scan loop (API from Step 1):
```zig
// NFC reject gate (parity with vakedc/lexer.py): reject non-NFC source,
// pointing at the first divergent codepoint. zg pinned to Unicode 16.0.0
// to match Python's runtime unicodedata.unidata_version.
const nfc = try zgNormalizeNfc(alloc, src);
if (!std.mem.eql(u8, nfc, src)) {
    const span = firstDivergence(src, nfc); // 1-based line/col like Python
    err.* = .{ .msg = "source is not Unicode-NFC-normalized (normalize the file to NFC)",
               .file = file, .line = span.line, .col = span.col };
    return error.LexError;
}
```
`firstDivergence`: walk `src` and `nfc` in parallel by **codepoint**, tracking line/col (advance line on `\n`, reset col to 1), until they differ — matching Python's char-index walk. Ensure the resulting `ErrInfo` is surfaced by `lex`/`parse`/`check`/`lower` byte-identically to Python's `VakedLexError` (exit 1, same stdout).

- [ ] **Step 4: Fix the Python clean-check harness.** The recursive corpus glob means `non-nfc.vaked` now reaches `test_vakedc_check.py:_test_all_examples`, which calls `check_source` (raises `VakedLexError`) and expects clean. Edit `_test_all_examples`:
```python
_SKIP = {"rejected.vaked", "non-nfc.vaked", "matches-fail.vaked"}  # invalid / diagnosing — covered separately
for f in files:
    rel = os.path.relpath(f, REPO)
    if os.path.basename(f) in _SKIP:   # MUST be above check_source (non-nfc raises in lex)
        continue
    diags = vakedc.check_source(open(f, encoding="utf-8").read(), rel, builtins_cache=cache)
    ...
skipped = sum(1 for f in files if os.path.basename(f) in _SKIP)
lines.append(f"  examples: {n_clean}/{len(files) - skipped} non-rejected examples check clean")
```
(`matches-fail.vaked` is added now to avoid a second edit in 5c.)

- [ ] **Step 5: Build + oracle + Python suite.** `… zig build`; oracle gate; `… python3 tests/spec/run_all.py`. **Expected:** `non-nfc.vaked` — both impls exit 1 with identical stdout on lex/parse/check; `diff_sqlite` skips it (both errored); `test_examples_parse` still 15; Python suite green. Confirm `… python3 tests/spec/test_examples_parse.py` reports 15.

- [ ] **Step 6: Commit.** (Squash 5b steps if 5b.1's fixture is transiently red before the gate lands.)
```bash
git add zig/build.zig.zon zig/build.zig zig/src/lex/lexer.zig vaked/examples/lex tests/spec/test_vakedc_check.py
git commit -m "feat(vakedc): Zig NFC reject gate via zg (Unicode 16.0.0), non-nfc negative fixture, oracle-gated"
```

---

## Task 5c — `matches` fixtures + gate (matcher already implemented)

**Files:** Create `vaked/examples/check/matches-{pass,fail}.vaked`. (No harness edit: 5b already added `matches-fail.vaked` to the skip-set; `matches-pass.vaked` checks clean.)

No matcher code. Keep regex inside the dialect BOTH the Zig `Regex` (checker.zig:854+) and Python `re.fullmatch` support identically: literals, `.`, `*`, `+`, `?`, char classes `[...]` (ranges + negation), `\`-escapes; **ASCII only**; **no** `(...)`, `(?:...)`, `|`, `{m,n}` (Zig returns `error.BadRegex` and suppresses → divergence). Chosen, both already proven by `vaked/examples/types/schema-constraints.vaked:22,36`: `/https:\/\/.*/` and `/[a-z0-9-]+/`.

- [ ] **Step 1: matches-PASS fixture.** Create `vaked/examples/check/matches-pass.vaked`:
```
# v0.3 — `matches` runtime matcher, PASSING case (checks clean). Bounded dialect
# only (literals, '.', '*', '+', char classes, '\' escapes). DO NOT add ( ) | { }.
schema firmwareRef {
  field url  : Path   { required matches /https:\/\/.*/ }
  field slug : String { required matches /[a-z0-9-]+/ }
}
firmwareRef zigbee {
  url  = "https://example.com/firmware.bin"
  slug = "zigbee-ota-v2"
}
```
Verify the grammar admits `<user-schema-name> <instance> { … }` (user schemas register their name as a kind, `check.py:328`). If not, fall back to extending an existing schema-constrained kind from `schema-constraints.vaked`. **Run:** `… python3 -m vakedc check vaked/examples/check/matches-pass.vaked --json; echo exit=$?` → iterate until exit 0, `diagnostics: []`.

- [ ] **Step 2: matches-FAIL fixture.** Create `vaked/examples/check/matches-fail.vaked` — same schema, `url = "ftp://example.com/firmware.bin"` (fails `/https:\/\/.*/`; `slug` still passes → exactly one diagnostic). **Run:** `… python3 -m vakedc check vaked/examples/check/matches-fail.vaked --json` → expect one `E-CONSTRAINT-MATCHES`, exit 1.

- [ ] **Step 3: The byte-diff gate (fix-on-divergence).**
```bash
P=vaked/examples/check
for fx in matches-pass matches-fail; do
  python3 -m vakedc check $P/$fx.vaked --json > /tmp/py.json
  ./zig/zig-out/bin/vakedc check $P/$fx.vaked --json > /tmp/zg.json
  diff /tmp/py.json /tmp/zg.json && echo "$fx IDENTICAL"
done
```
(run inside the dev shell). **Expected:** both identical — fail's message `field \`url\`: value "ftp://example.com/firmware.bin" does not match /https:\/\/.*/` byte-for-byte. **If divergent** (Risk #5): check body-slash stripping (`checker.zig:828-829` mirrors `body[1:-1]`), escaped-slash handling (`\/`→`/` both sides). If a genuine matcher bug surfaces (e.g. greedy backtracking in `matchHere`), fix `checker.zig`'s `Regex` to match `re.fullmatch`, add a reproducing Zig unit test, re-run.

- [ ] **Step 4: Full oracle gate.** `… develop --command sh -c 'VAKEDC_ZIG="$PWD/zig/zig-out/bin/vakedc" python3 tests/spec/run_all.py'`. **Expected:** `check` byte-identical for pass (clean) and fail (`E-CONSTRAINT-MATCHES`) — the first byte-gate of the previously-untested matcher path; whole suite green over the 18-file corpus (15 + non-nfc + matches-pass + matches-fail).

- [ ] **Step 5: Commit.**
```bash
git add vaked/examples/check
git commit -m "feat(vakedc): matches pass/fail fixtures byte-gate the Zig regex matcher"
```

---

## End-to-end verification (Phase 5 done)

Run from `$REPO` inside the dev shell:
1. `… develop --command sh -c 'cd zig && zig build test'` → all Zig unit tests pass (emit, sqlite-link, NFC, any new matcher test).
2. `… develop --command python3 tests/spec/run_all.py` → Python suite green; `test_examples_parse` reports **15** (new fixtures live in `lex/`+`check/`, outside its globs); clean-check skip-set updated.
3. **`… develop --command sh -c 'VAKEDC_ZIG="$PWD/zig/zig-out/bin/vakedc" python3 tests/spec/run_all.py'`** → every stage including the new **`sqlite`** stage byte-identical Python vs Zig over the 18-file corpus. **This is the Phase-5 completion bar.**
4. Each task committed independently; suite green after each.
5. PR description **flags the 5b spec contradiction** (Python rejects, spec says normalize) and recommends correcting spec §3.

**Outcome:** Zig `vakedc` is a complete drop-in for the Python compiler (SQLite, NFC, matches at parity, each oracle-gated). Phase 6 (golden freeze + golden-mode) can then proceed.

---

## Risks & mitigations

1. **nix sqlite linking (5a.1).** `zig build` may not auto-consume `NIX_CFLAGS_COMPILE`/`NIX_LDFLAGS`. → try `link_libc`+`linkSystemLibrary` (pkg-config) first; else explicit `addIncludePath`/`addLibraryPath` or `PKG_CONFIG_PATH`. Verify with the version smoke test before any emit logic. `sqlite` is guaranteed by `flake.nix`.
2. **SQLite int/NULL rendering parity (5a.2/3).** Python renders ints via `str(int)`, NULL→`""`. → unit test asserts exact bytes for a no-provenance node (5 trailing empty fields) AND real provenance ints; use `sqlite3_column_int64`+`{d}`. `labels`/`props` share the same `writeValueCompact` bytes.
3. **`zg` Unicode-16 pin (5b).** Must match Python runtime 16.0.0 at freeze time. → pin the Unicode-16 tag; the non-nfc fixture gates it. (Pure-Zig minimal-table quick-check rejected — see Discrepancy 2.)
4. **Fixture-count / clean-check assertions.** Recursive glob hits multiple tests. → new fixtures in NEW subdirs (`lex/`,`check/`) keep `EXPECTED_VAKED_COUNT`=15; `test_vakedc_check` skip-set extended (5b.4); `test_vakedc.py`/`test_lowering_fixtures.py` use explicit sets, unaffected; oracle `corpus()` picks them up (intended).
5. **Zig `Regex` vs `re.fullmatch` divergence (5c).** Zig lacks `(...)`/`|`/`{m,n}`. → fixtures use the shared dialect only; 5c.3 is an explicit byte-diff gate; fix the matcher with a reproducing test if it diverges (not expected — regexes already in the corpus).
6. **Transiently-red fixture (5b).** non-nfc is red until the gate lands. → oracle is opt-in (`VAKEDC_ZIG`); don't push mid-task or squash 5b.

---

## Notes / out of band

- **Plan location:** in-repo copy (swarm-readable). Plan-mode scratch at `~/.claude/plans/robust-marinating-adleman.md`; this committed doc is canonical.
- **`/ruflo-core:init-project full` — NOT run.** Would overwrite the curated project `CLAUDE.md` (Snyk-OFF + patch-doctor notes) and scaffold the `.claude-flow/`/`.swarm/` files the project decided not to commit. Re-issue only if a fresh ruflo scaffold is genuinely wanted.
- **Snyk stays OFF** for this repo (`CLAUDE.md`); no `snyk_code_scan`.
- **Swarm coordination:** one shared working tree. Serialize edits to the shared files — `zig/build.zig`, `zig/build.zig.zon`, `zig/src/cli/main.zig`, `tests/spec/oracle.py`, `tests/spec/test_vakedc_check.py` — through the coordinator. Run the oracle gate after EACH task merges, not only at the end.
