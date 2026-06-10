# vakedc parser prototype — design

- **Date:** 2026-06-10
- **Status:** Approved (brainstorm) → implementing via subagent-driven execution
- **Goal:** the first executable Vaked front-end — lexer + parser that instantiate the **Labeled Property Graph** (the typed-semantic-graph substrate 0011's checker and 0012's lowering operate on), with provenance attached natively at node instantiation.

## Decisions

1. **Language:** Python 3, stdlib only (prototype; the production parser is Zig later). Lives at top-level `vakedc/`, runnable as `python3 -m vakedc`.
2. **Scope:** 0011 pipeline stages 1–2 — **parse + resolve → LPG**. Schema conformance / constraints / capability POLA checking (stages 3–4) are the next increment on top of this graph. No lowering execution.
3. **Output:** **both** canonical JSON and SQLite.

## Architecture

- **Lexer (`lexer.py`)** — mode-switching DFA: string mode w/ `${ref}` interpolation; regex-literal mode entered only after `matches`; NEWLINE tokens emitted, suppressed inside open `(` `[`; durations (`24h`) / bytes (`4KB`) / paths (`./x`) / dotted-ref-vs-path disambiguation; `#` comments stripped. **NFC gate:** non-NFC source is rejected (source-mapped error); the pinned Unicode version is declared as a constant and checked against the runtime's `unicodedata.unidata_version` (mismatch ⇒ warning, mirroring the `.hcplang` 15.1.0 pin discipline). Every token carries `{byteStart, byteEnd, line, col}` (1-based line/col).
- **Parser (`parser.py`)** — hand-written recursive descent, PEG/ordered-choice per the v0.3 grammar header: soft keywords `field`/`grant`/`order` dispatched before assignment, `open` after; newline-terminated statements; 1–2 token lookahead. Targets `vaked/grammar/vaked-v0-plus.ebnf` v0.3 **exactly** (no extensions). Errors: `file:line:col — expected X, got Y`, explainable + source-mapped.
- **LPG (`graph.py`)** — Node `{id, kind, name, labels[], props{}, provenance{file, decl, span{byteStart, byteEnd, line, col}}}`; Edge `{from, to, label, props{}}`. **Span convention = 0012 §6.2 byte-exact** (byteStart at the decl's leading keyword; byteEnd exclusive one past the closing `}`). Node ids stable + path-derived (e.g. `operator-field.vaked#operator-field/mediaCompress`). Nodes instantiate the moment a decl parses, provenance attached immediately.
- **Resolution (`resolve.py`)** — lexically-scoped symbol table; refs collected on a worklist during parse, resolved at end-of-parse (handles forward refs). Edge labels by source field semantics: `contains` (nesting), `imports` (`use`), `depends_on` (`input`/`output`/`from`/`source`/`engine` refs), `requires_capability` (capability-list refs → `domain.grant`), `routes_to` (mesh `->` edges; edge label string as a prop), `member_of` (`parallel.fibers`). Refs whose head resolves to nothing in-file (e.g. `zigimg`, `agentGuardd.ringbuf`, `artifacts.compressedMedia`) become **external stub nodes** (`kind: "external"`, `external: true`) — the graph is closed, never silently dangling (matches 0012's resolve-boundary note).
- **Emit (`emit.py`)** — (a) **canonical JSON**: stable ordering everywhere (nodes by id, edges by (from,label,to), object keys in fixed schema order); two runs ⇒ byte-identical. (b) **SQLite**: `nodes` / `edges` / `props` tables with provenance columns; determinism asserted via canonical-ordered SELECT dumps (not file bytes).
- **CLI (`__main__.py`)** — `python3 -m vakedc parse <file.vaked> [--json PATH] [--sqlite PATH] [--print]`; default writes both under `.vaked/` (gitignored). Exit non-zero on lex/parse/NFC errors.

## Verification (wired into tests/spec/run_all.py → existing CI + dashboard)

New module `tests/spec/test_vakedc.py`:
1. **Differential oracle:** vakedc and the from-EBNF recognizer must agree on accept/reject for all 15 `.vaked` examples AND the malformed/compat probes (incl. `open = true` as assignment, bare `open` as open_decl).
2. **Golden snapshot:** `operator-field.vaked` → checked-in `tests/spec/golden/operator-field.graph.json`, byte-compared.
3. **Cross-artifact provenance:** node spans for operator-field's decls must equal the spans in `vaked/examples/lowering/provenance.json` (parser ↔ lowering spec locked).
4. **Determinism:** parse twice ⇒ identical JSON bytes; SQLite canonical dump identical.
`.gitignore`: `.vaked/` output dir. CI: no workflow change needed (run_all picks the module up); tag `v0.4.0` after green proves it.

## Deferred

0011 stages 3–4 (conformance/constraint/POLA checking); the Zig production parser; lowering execution; `.hcplang` parsing (separate front-end); incremental parsing/watching.
