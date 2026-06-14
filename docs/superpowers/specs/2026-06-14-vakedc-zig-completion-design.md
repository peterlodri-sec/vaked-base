# vakedc Zig migration — completion to a Python-free toolchain

**Date:** 2026-06-14
**Status:** Design approved (brainstorm); plan + implementation to follow.
**Predecessor:** `docs/superpowers/specs/2026-06-14-vakedc-zig-rewrite-design.md` (the stage-by-stage port). This spec covers the *completion*: full feature parity, the cutover that deletes Python, and porting the test harness to Zig so the entire toolchain is Python-free.

---

## 1. Where we are / what this finishes

Phases 0–4 are done, committed, and green: the four compiler stages (lex → parse+resolve → check → lower) are ported to Zig, **byte-identical to Python over the corpus**, gated by the differential oracle (`tests/spec/oracle.py`, `VAKEDC_ZIG`), with `vaked-core` as a shared library and a `vakedc` CLI. `zig build test` green; Python suite 10/10.

This spec completes the original "e2e rewrite everything, python→zig" goal:
1. **Full parity** — port the three deferred features (SQLite emit, true NFC, `matches` matcher) so Zig is a complete drop-in, not just corpus-equivalent.
2. **Cutover** — delete the Python compiler, make Zig canonical.
3. **Python-free harness** — port the test harness itself to Zig.

## 2. The architectural spine — oracle → golden pivot

Today's correctness proof is the **differential oracle**: run identical inputs through Python and Zig, byte-compare. Its reference is Python. **Cutover deletes Python → the oracle loses its arbiter.** Therefore the migration must, strictly in this order:

1. Close all parity gaps **while Python still arbitrates** (the differential oracle validates each new feature).
2. **Freeze golden fixtures** — capture the agreed canonical output (both impls match) for the full corpus across every stage, committed to the repo.
3. **Cutover** — delete the Python *compiler*; the harness pivots to **golden-mode** (diff Zig vs frozen golden — no Python needed).
4. **Port the harness** to Zig — delete the Python *harness*; drop `python` from the dev shell.

**Freeze-before-delete is non-negotiable.** Two deletions are deliberately separated so each phase stays independently green:
- **Cutover (Phase 7)** removes the Python **compiler** (`vakedc/`). The Python *harness* survives, running golden-mode (it needs only the goldens + the Zig binary, not the Python compiler).
- **Harness port (Phase 8)** removes the Python *harness* too.

## 3. Decomposition — Phases 5–8

Each phase is its own spec→plan→impl cycle and must end independently green (full suite passing). Dependency order is strict: 5 → 6 → 7 → 8.

### Phase 5 — Parity gaps (Python present; differential oracle arbitrates)
Each gap lands as: the Zig implementation + an **oracle gate** proving Zig == Python. 5a (SQLite) needs no new fixture — any existing corpus file with a graph exercises `graph.db`. 5b and 5c require **new fixtures** (added permanently under `vaked/examples/`, per the approved decision — the published corpus carries them), since nothing currently exercises non-NFC input or a `matches`-bound value.

- **5a — SQLite emit** (`vakedc parse --sqlite PATH` / `graph.db`).
  - Zig: `@cImport` libsqlite3; port `emit.py:to_sqlite` (tables `nodes`, `edges` with provenance columns) and the schema verbatim.
  - Build: add `link_libc` + `linkSystemLibrary("sqlite3")` to the CLI module (deferred from Phase 0). Resolve the nix-provided lib/headers: rely on the dev-shell's `NIX_CFLAGS_COMPILE`/`NIX_LDFLAGS` (sqlite is in `buildInputs` since Phase 0); if `zig build` does not pick those up automatically, add explicit `addIncludePath`/`addLibraryPath` derived from the `sqlite` package, or use pkg-config. (Solve at impl; the pin already exists.)
  - **Gate (approved):** a new oracle `sqlite` stage compares the **textual `canonical_dump`** (deterministic `SELECT … ORDER BY` dump), NOT the file bytes (SQLite page layout is not byte-stable). Zig must produce a `canonical_dump`-equivalent string byte-identical to Python's. The Zig binary grows a hidden `--dump-sqlite` (or the oracle dumps via the sqlite CLI deterministically) — decide at impl; the compared artifact is the canonical dump text.

- **5b — True NFC** (replace the Phase-1 passthrough).
  - Zig: add the `zg` dependency (Unicode **16.0.0**, matching Python's runtime `unicodedata.unidata_version`); normalize source NFC before lexing, matching `unicodedata.normalize('NFC', src)`.
  - Fixture: a `.vaked` containing a **non-NFC codepoint** (a decomposed sequence that composes under NFC) in a position the lexer passes through (e.g. a string/comment). Must remain parseable + checkable.
  - **Gate:** existing lex/parse oracle (the normalized bytes flow into tokens/graph). Keep the pinned-version stderr warning behavior.

- **5c — `matches` runtime matcher.**
  - Zig: port the runtime regex match used by the `matches` constraint in `check.py` (the matcher, plus the dialect well-formedness already handled). Match Python's regex semantics for the dialect Vaked uses.
  - Fixture: a `.vaked` binding a value to a `matches`-constrained field — one passing, one failing (→ the `matches` diagnostic).
  - **Gate:** existing check oracle (diagnostics byte-identical).

### Phase 6 — Golden freeze + golden-mode
- **Freeze**: for every corpus file, capture the canonical output of every stage — tokens (lex dump), `graph.json`, `diagnostics.json`, the lower artifact tree + `provenance.json`, and the sqlite `canonical_dump` — into a committed `tests/spec/golden/<...>` tree. Both impls agree (oracle green), so the frozen bytes are unambiguous. Freeze from the surviving impl (Zig), cross-checked equal to Python at freeze time.
- **Golden-mode**: add a mode to the harness that diffs **Zig output vs frozen golden** (no Python). Keep differential-mode too.
- **Proof gate**: run BOTH modes; require golden-mode ≡ differential-mode, both green. This proves the goldens faithfully capture the agreed contract before Python can be removed.

### Phase 7 — Cutover (delete the Python compiler)
- Delete `vakedc/` (the Python compiler package).
- Repoint everything that invoked it: `flake.nix` comments/usage, `docs/**` references, the `.vaked/` invocation convention, and any scripts/CI calling `python -m vakedc` → the Zig binary (`zig/zig-out/bin/vakedc` or an installed path).
- The harness runs **golden-mode only** (Python compiler gone). Differential-mode code is removed or archived.
- `python` stays in the dev shell (the harness is still Python until Phase 8).
- **Gate:** full suite green in golden-mode with `vakedc/` absent.

### Phase 8 — Full Zig harness (Python-free)
- **Zig conformance runner**: a Zig entry (`zig build conformance`, or folded into `zig build test`) that runs the Zig vakedc over the corpus and diffs every stage's output vs the frozen golden tree. Replaces `oracle.py` golden-mode.
- **Port the repo/doc-integrity checks to Zig**: `test_grammar_selfcontained` (EBNF self-containment) and `test_doc_links` (markdown link integrity) become Zig programs/tests. These don't touch the compiler — they guard the repo — but are ported for a fully Python-free toolchain.
- **Fold** the float-repr conformance and lower-scale perf checks into `zig build test` (Zig versions already exist for float-repr; add a Zig scale/perf test).
- **Delete** the Python harness: `run_all.py`, `oracle.py`, `gen_scale_fixture.py`, `test_*.py`, `float_repr_corpus.txt` (its contract moves into the Zig test).
- **Drop `python`** from the `flake.nix` dev shell. Toolchain Python-free.
- **Gate:** `zig build test` + `zig build conformance` green; no Python in the repo's build/test path; CI (if any) updated.

## 4. Components & boundaries

- `vaked-core` (unchanged role): LPG model, canonical JSON, diagnostics, plus the SQLite emit lands here or in a small `vaked-emit` sibling (decide at impl; keep `vaked-core` focused).
- `vaked-lex` gains a real NFC step (via `zg`); `vaked-check` gains the `matches` matcher; the CLI gains `--sqlite`.
- New: a `conformance` Zig program (Phase 8) + Zig ports of the two repo-doc checks. Keep each as a focused, separately-testable unit.

## 5. Testing strategy across the pivot

- **Pre-cutover (Phases 5–6):** differential oracle (Zig vs Python) remains the spine; new fixtures extend coverage; golden-mode added and proven equal to differential-mode.
- **At cutover (Phase 7):** golden-mode (Zig vs frozen golden) becomes the spine; differential-mode retired.
- **Post-harness-port (Phase 8):** `zig build test` (unit) + `zig build conformance` (corpus vs golden) + Zig repo-doc checks. The frozen goldens are the regression baseline; regenerating them is a deliberate, reviewed act (a `--update-goldens` path on the conformance runner).
- A stage/phase merges only when the full suite is green in the mode appropriate to that phase.

## 6. Risks & mitigations

- **nix sqlite linking** — `zig build` may not auto-consume nix's `NIX_CFLAGS_COMPILE`/`NIX_LDFLAGS`. Mitigation: explicit `addIncludePath`/`addLibraryPath` from the `sqlite` derivation, or pkg-config; prove the C header compiles (already verified in Phase 0).
- **New corpus fixtures must stay valid** — the non-NFC and `matches` fixtures are added to `vaked/examples/` permanently and must parse + check as intended (one passing, one diagnosing) and not perturb existing golden/aggregate tests (e.g. `EXPECTED_VAKED_COUNT` in `test_examples_parse`). Mitigation: update any corpus-count assertions; verify the full suite after adding each.
- **`zg` Unicode version drift** — must match Python's runtime (16.0.0) at freeze time, else NFC could differ. Mitigation: pin `zg` to a Unicode-16 tag; the non-NFC fixture gates it.
- **Doc-link / grammar checks in Zig are fiddly** — markdown/EBNF scanning is easy in Python, more verbose in Zig. Mitigation: keep them minimal and behavior-equivalent to the Python versions they replace; port last (Phase 8), lowest-risk-last.
- **Golden staleness** — frozen goldens drift from intent if regenerated carelessly. Mitigation: golden updates are explicit (`--update-goldens`), reviewed in diff, and never automatic in CI.

## 7. Out of scope

- The OTP/Zig **enforcement daemons** (separate subsystem; they *consume* `vaked-core` later in their own cycle).
- HCP/Litany protocol work.
- Any new language features — this is a migration-completion effort, not a language change.

## 8. Sequencing summary

```
Phase 5 (parity: 5a sqlite, 5b nfc, 5c matches)   ← Python present, differential oracle
   │   each: new fixture + Zig impl + oracle gate
   ▼
Phase 6 (freeze goldens + golden-mode; prove golden ≡ differential)
   ▼
Phase 7 (cutover: delete vakedc/, repoint flake/docs/invocation; golden-mode spine)
   ▼
Phase 8 (Zig conformance runner + port repo-doc checks + delete Python harness + drop python from flake)
   = Python-free toolchain
```
