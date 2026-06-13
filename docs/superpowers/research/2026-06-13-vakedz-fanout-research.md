# vakedz fan-out research — port-specs for the Zig front-end

**Date:** 2026-06-13 · **Author:** vaked-compiler-dev session · **Status:** research
prep for the `vakedz` subsystem (design → plan → implement).

This is the synthesized output of a four-way **fan-out** over the Python
reference (`vakedc/`) and the runtime cache model (`tools/ralph`, `eventd`). Each
strand produced a faithful port-spec for one stage. Together they are the
contract `vakedz` is built against. All file:line refs are into the repo at the
time of writing; treat them as anchors, not eternal truth.

> Why this document exists: the Zig front-end is a new subsystem, and the repo
> convention is **design → plan → implement, spec first** (CLAUDE.md). A from-
> scratch reimplementation that silently diverges from `vakedc` would fork the
> language. This research pins the bytes so the port can be *verified*, not
> trusted.

---

## Strand A — parse (lexer → parser → LPG)

**Reference:** `vakedc/lexer.py`, `vakedc/parser.py`, `vakedc/resolve.py`,
`vakedc/graph.py`, `vakedc/emit.py`. Grammar: `vaked/grammar/vaked-v0-plus.ebnf`
(v0.3, PEG ordered). The parser comment asserts it implements the grammar
"EXACTLY (no extensions)".

### Tokens (`lexer.py`)
`IDENT, STRING, NUMBER, DURATION, BYTES, PATH, REGEX, OP, NEWLINE, EOF`.

- **Newlines** terminate statements but are **queued + deduped** and **suppressed
  inside `(` `)` / `[` `]`** (group-depth counter); a trailing newline is
  stripped; `EOF` is always last.
- **NUMBER → DURATION/BYTES**: after digits (+ optional `.`digits for floats),
  longest-match a unit suffix; the unit must **not** be followed by an ident
  char. Byte units `B KB MB GB TB`; duration units `ns us ms s m h d`.
- **PATH vs `.`**: a `.` begins a PATH only when **not glued** to the preceding
  significant token and followed by `/` or a letter; otherwise it is the DOT
  operator (dotted refs) or `..` (range).
- **REGEX** (`/…/`) is recognized **only** immediately after a `matches` ident;
  a stray `/` is a lex error.
- Multi-char ops `-> <= >= .. ?=` (longest match); singles `=<>.;:,@()[]{}|`.
- Comments `#`→EOL discarded. Byte-exact spans (`byteStart`, `byteEnd`, 1-based
  `line`/`col`). NFC gate pinned to Unicode 15.1.0 (warn-only on mismatch).

### Parser / AST (`parser.py`)
Hand-written recursive descent, **PEG ordered** (first match wins). Statement
order: `field_decl, grant_decl, order_decl, assignment, open_decl, inherit_stmt,
edge, node_decl, decl, app`. Soft keywords `field/grant/order/open` only trigger
in their full shape (lookahead predicates), so v0.2 programs parse unchanged
(grammar §8). Only `edge` uses save/restore backtracking. 28 declaration kinds.
AST nodes: `Decl, Import, Assignment, FieldDecl, OpenDecl, GrantDecl, OrderDecl,
InheritStmt, NodeDecl, Edge, App, Ref, Literal, ListLit, RecordLit, TypeRef`.
Types are captured as **flat text**, not validated (Goal 2).

### Resolve → LPG (`resolve.py`, `graph.py`)
- **Node id** = `<basename>#<chain joined by '/'>` (basename, not full path).
  `provenance.file` is the **full** source path.
- **Node kinds/labels**: real decls `["decl", <kind>]`; a `node` decl; the
  per-import `file` node `["file"]`; unresolved refs become `external` stubs
  `["external"]` with id `external:<dotted>` and props `{"external":true}`.
- **Edges**: `contains` (parent→child nesting), `imports` (file→external),
  `depends_on`, `member_of`, `requires_capability`, `routes_to`.
- **Dep-bearing fields** (a **bare ref** value, or each bare-ref element of a
  list, ⇒ a `depends_on` edge): `source, input, output, engine, from`. A call
  (`github("…")`, `raw.github(…)`) is **not** a bare ref ⇒ no edge. `fibers` ⇒
  `member_of`; `capabilities` ⇒ `requires_capability`.
- **Ref resolution**: 1 part → in-scope decl by name, else external; `<kind>.<name>`
  → in-file decl of that kind, else external; otherwise external dotted.

### Canonical JSON (`emit.py`) — the byte-parity contract
Structural wrappers are **fixed order**; only the **props subtree** is
recursively key-sorted:
- top-level `version, source, nodes, edges`
- node `id, kind, name, labels, props, provenance`
- edge `from, to, label, props`; provenance `file, decl, span`; span
  `byteStart, byteEnd, line, col`
- **nodes sorted by id**; **edges sorted by `(from, label, to, props)`**
- compact separators `,`/`:`; CPython escaping (`/` **not** escaped; non-ASCII
  passthrough); **trailing newline**.

**Prop value encodings** (verified against golden graphs):
`{"lit":<kind>,"value":<text>}` · `{"ref":<dotted>}` ·
`{"ref":…,"args":[…]}` · `{"ref":…,"record":[…]}` · record entries
`{"assign":n,"op":"=","value":…}` / `{"inherit":[…]}` · signature
`{"params":[{"default":null|…,"name":…,"type":…}],"return":…|null}`. A top-level
`?=` assignment wraps as `{"op":"?=","value":…}`; `=` stores the bare value.

### parse CLI
`vakedc parse <file> [--json PATH] [--sqlite PATH] [--print]`; default writes
`.vaked/graph.json` (+`.db`). Exit 0 ok / 1 on read|lex|parse error.

---

## Strand B — check (the 0011 type system)

**Reference:** `vakedc/check.py` (~1685 L), `vakedc/resolve.py`; normative
`docs/language/0011-type-system.md`; catalog `vaked/schema/parallel-types.md` +
`vaked/schema/builtins.vaked`. Pipeline: **elaborate (load builtins + user) →
closed-world ref resolution → load-time well-formedness → name-collision →
conformance + constraints**. Diagnostics are sorted by `(file, byteStart,
byteEnd, code)`; `check --json` emits `{"diagnostics":[{code, severity, message,
file, decl, span:{byteStart,byteEnd,line,col}, related}]}`. Exit 0 clean / 1 on
any diagnostic; `lower` refuses to emit unless clean.

**22 diagnostic codes** across families:
`E-CONFORM-{MISSING-FIELD,UNKNOWN-FIELD,TYPE}` ·
`E-CONSTRAINT-{NONEMPTY,ONEOF,RANGE,MATCHES}` ·
`E-SCHEMA-{REFINEMENT,BAD-ONEOF,BAD-DEFAULT,BAD-RANGE,BAD-REGEX}` ·
`E-CAP-{UNKNOWN-DOMAIN,UNKNOWN-GRANT,ORDER-DANGLING,ORDER-CYCLE,ATTENUATION}` ·
`E-GENERIC-INCONSISTENT` · `E-REF-UNRESOLVED` ·
`E-WORKFLOW-{CYCLE,DEPTH}` · `E-DECL-NAME-COLLISION`.

**Type system**: structural; scalars `String Int Float Bool Path Duration Bytes
Null` (with `Int◁Float` widening and string-form acceptance for Path/Duration/
Bytes); `List<T>`, records (per-kind schema, five-clause conformance), unions
(left-to-right), generic params `T I O Node Edge` (unconstrained). **Capabilities**:
6 built-in domains (`fs network mcp ebpf process mem`) with reflexive-transitive
attenuation closure; mesh delegation `sender→receiver` requires
`receiver.grant ≤ sender.grant` per domain (POLA). **Built-in catalog**: 16
primary kinds + 6 nested record schemas (`fiberPolicy, meshNode, workflowStep,
…`), loaded from `builtins.vaked`. **Deferred** (branch B, #7/#8): bare refs
outside `runtime`, namespace refs (`pkgs.x`, daemon channels). **Stubbed**: fiber
input/output consistency.

---

## Strand C — lower (the 0012 emitters)

**Reference:** `vakedc/lower.py` (~2442 L), `vakedc/emit.py`; normative
`docs/language/0012-lowering.md`; fixtures `vaked/examples/lowering/` (7 files,
operator-field) and `lowering-agentfield/` (11 files). Lowering is a **pure,
total, hermetic** function of `(validated graph + pinned inputs)`: same graph ⇒
byte-identical artifacts; no IO/clock/randomness.

**Emitter registry (~16)**: always-on `nix.spine`→`flake.nix`,
`docs.runtime`→`gen/RUNTIME.md`; presence/`emit`-gated `zig.daemoncfg`→
`gen/zig/<fiber>.json`, `catalog.jsonl`→`gen/catalog/<idx>.jsonl`,
`otp.supervision`→`gen/otp/*_sup.erl`+`vaked_fiber_worker.erl`, plus the NixOS
cohort (`sops.secrets, nixos.service, host.resources, caddy.ingress,
oci.containers`), runtime plane (`eventd.config, memory.store, workflow.spec`),
`colmena.hive`, `ebpf.policy`; a few `emit_deferred` no-ops.

**Provenance** (`provenance.json`): `{version, source, artifacts:{<path>:[{region?,
sourceFile, decl, span, emitter, inputsHash}]}}`. `inputsHash =
"sha256-" + sha256(canonical_projection_json)` — **per-projection** (node /
engine / workflow), canonical JSON (sorted keys, compact, ensure_ascii=False).
Artifact paths lexicographic; entries in emission order. Every artifact carries
`generated by Vaked from <basename>:<kind> <name> — do not edit` (no timestamp).

**Smallest v0.1 slice** (the first port target): reproduce the **operator-field**
fixture set — `nix.spine, docs.runtime, zig.daemoncfg, catalog.jsonl,
otp.supervision` over kinds `runtime, index, stream, fiber, surface, parallel` →
7 files, byte-identical to `vaked/examples/lowering/`.

**lower CLI**: `vakedc lower <file> [--out DIR] [--builtins PATH]`; check-first,
refuses on any diagnostic; writes the tree + `provenance.json`. Exit 0/1/2.

---

## Strand D — toolchain & the ralphloop-cache

**Zig toolchain**: `flake.nix:26` provides `zig` from nixpkgs (unpinned). New
subsystems are **top-level self-contained packages** (`vakedc/`, `eventd/`,
`agent_guardd/`). Recommendation realized: a new top-level `vakedz/` mirroring
`vakedc/`, pinned in CI to the `build.zig.zon` floor.

**The cache model** — ralph's **frozen, hash-chained ledger**
(`tools/ralph/ralphcore.py:465–514`, mirrored in `eventd/core.py:1–80`,
cross-verified in `tests/spec/test_eventd.py`):

```
one JSON object per line, append-only:
  {"seq":N, "prev":<hex sha256 of prev, GENESIS="0"*64>,
   "payload":<canonical JSON>, "hash":sha256(prev_hex ++ canonical_json(payload))}
```
Canonical JSON = sorted keys, compact, `ensure_ascii=False`. `seq` is 0,1,2…;
any tamper breaks the chain; `longest_valid_prefix` gives torn-tail recovery.
SHA-256 is the repo standard (also `vakedc/lower.py` `inputsHash`); no blake3.

**Cache key/value design (realized in `src/cache.zig`)**: key = the deterministic
subset `{event(phase), file, source_sha256, grammar_version}`; value =
`output_sha256`, with the output bytes stored content-addressed under
`.vakedz-cache/cas/<sha256>` and the binding appended to
`.vakedz-cache/ledger.jsonl`. A lookup hashes the source, finds the latest
matching ledger entry, and replays the CAS blob — **never recomputes**. The
payload is **clock-free**, so identical source ⇒ identical entry: the loop is
content-addressed, replayable, and tamper-evident — ralph's bet, made a compiler
primitive.

---

## How this maps to v0.1

- **parse + ralphloop-cache** are implemented and gated byte-for-byte against the
  goldens (`vakedz/test/crossverify.sh`, `.github/workflows/vakedz-ci.yml`).
- **check + lower** are scaffolded (pipeline wired, honest "not yet ported"
  verdicts) and become the issue-tracked backlog — the diagnostic table (Strand
  B) and the emitter slice (Strand C) are the unit of work.
