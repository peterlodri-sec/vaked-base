# vakedc Python → Zig port (design)

## Status

Design / tracking epic (2026-06-12). Zig is Vaked's actual target implementation
language; the Python `vakedc` is a reference front-end. This is a **reimplementation
to byte-parity**, NOT a language change — the grammar (`vaked-v0-plus.ebnf`), the
0011/0012 semantics, and every golden byte are FROZEN during the port.

## Why a port, and why it's low-risk

`vakedc` is ~5,000 LOC of pure-stdlib Python across 9 modules (lexer→parser→
graph+resolve→check→lower→emit+CLI). The migration's **contract already exists**:
the spec suite is a golden/differential oracle —
`tests/spec/golden/operator-field.graph.json`, `rejected.diagnostics.json`, the
`vaked/examples/lowering/` fixture tree, the EBNF differential recognizer, and the
byte-exact `--json` canonical forms. **Parity = "Zig produces these same bytes."**
That makes parity mechanically checkable, not a judgment call.

## Strategy: strangler + differential, bottom-up

Port one module at a time. Keep **Python as the permanent oracle** until full
parity (and one release). Gate every phase on byte-identical output against the
existing goldens **and** a Python-vs-Zig diff over all 16 examples. Don't
rewrite-and-pray.

## The four determinism dependencies (Phase 0 — de-risk FIRST)

These are where a Zig port silently diverges from Python's bytes:

1. **Unicode 15.1.0 NFC** (#1 risk). Zig std has no normalization. Vendor a
   generated NFC table pinned to 15.1.0 (matching the lexer's `PINNED_UNICODE`).
   Identifier normalization sits under everything — spike this first.
2. **Canonical JSON byte-exactness**. Reproduce Python's
   `json.dumps(separators=(",",":"), ensure_ascii=False)` + sorted keys exactly.
   Canary: `operator-field.graph.json`.
3. **sqlite emit** (`catalog.sqlite`). Decide: vendor the libsqlite3 amalgamation
   (deterministic `canonical_dump`) vs. ship `catalog.jsonl` first and defer the
   sqlite emitter.
4. **sha256** (provenance manifest) → `std.crypto.hash.sha2.Sha256`. Straightforward.

Plus: **pin Zig** in `flake.nix` (currently bare `zig`, 0.16.0 on PATH) for
reproducibility; and confirm no bignum is actually needed (0011 says Int is
arbitrary-precision, but the checker only matches literal *form* and range-checks
via float — Zig can keep numbers as slices + parse to f64; cheap audit).

## Phase ordering (each phase: Zig module + Python-diff gate)

0. **Spikes** (de-risk the four deps above). **This commit lands spike #4 (sha256)
   as the first verified canary** — see `zig/vakedc/`.
1. **lexer** → token stream; diff tokens (carries the Unicode spike).
2. **parser** → AST; diff via the EBNF differential oracle over all examples + probes.
3. **graph + emit(json)** → `to_canonical_json`; gate on `operator-field.graph.json`.
4. **resolve** → LPG/edges + external stubs.
5. **check** → diagnostics; gate on `rejected.diagnostics.json` + all-examples-clean,
   including the `E-REF-UNRESOLVED` closed-world + import-binding behavior.
6. **lower + emit(sqlite/sha)** → gate on `vaked/examples/lowering/` + manifest sha256.
7. **CLI** → `vakedc {parse,check,lower}` single binary mirroring `python -m vakedc`.

## Differential harness (build in Phase 0, runs every phase)

A thin script feeding all 16 examples + fixtures to both `python -m vakedc <cmd>`
and `./zig-out/bin/vakedc <cmd>`, byte-diffing stdout/emitted trees. Keep Python
`tests/spec/run_all.py` as the cross-impl oracle; add Zig as a second backend
behind the same goldens.

## Layout

`zig/vakedc/` (`build.zig`, `src/{lexer,parser,graph,resolve,check,lower,emit,main}.zig`),
wired into the flake so `nix build` produces the binary. Tracking epic +
one sub-issue per phase (mirrors the repo's design→plan→implement convention).

## Cutover

Keep Python as reference through full parity **and one release**, then archive
`vakedc/` (don't delete — it stays the canonical oracle for any future semantic
change).

## Open decisions (settle at kickoff)

- Zig version to pin in the flake (0.16.0 is on PATH).
- sqlite: vendor amalgamation vs. defer the emitter.
- Unicode table: vendor generated-from-15.1.0 vs. a Zig unicode lib.
- Whether the port absorbs the deferred branch-B roster work (#8) or freezes
  behavior exactly at current Python parity (recommend: freeze parity first).
