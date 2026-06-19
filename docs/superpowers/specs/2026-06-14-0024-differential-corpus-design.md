# 0024 Differential Test Corpus - Design

Date: 2026-06-14
Status: Stage-0 leg implemented and green; Stage-1 leg deferred until Stage-1 exists.
Owner artifact: `tests/corpus/0024-differential/`

## 1. Purpose

`docs/language/0024-mlir-lowering-staged-adoption.md` §11 ("Verification
checklist") gates declaring the Stage-1 MLIR lowering complete. Several of its
boxes are *comparative* - they assert Stage-1 behaves *identically to Stage-0*.
Claim **C14** flagged that no runnable evidence exists for those boxes: there is
no test corpus that (a) pins the Stage-0 baseline and (b) is structured so the
Stage-0↔Stage-1 equality check drops in when Stage-1 lands.

This corpus closes that gap. Today it proves the Stage-0 leg: lowering
determinism and correct rejection of the two illegal topologies. It is wired so
the cross-stage comparison is a small, well-defined addition rather than a
rewrite.

## 2. Topology classes

Five topology classes, each exercising a distinct lowering invariant. (The
depth-bound class is exercised by *two* fixtures - accepting and rejecting -
which is why there are six fixture files for five classes.)

| Class | Fixture(s) | Shape | Invariant exercised |
|-------|-----------|-------|---------------------|
| Single node | `single-agent.vaked` | one node, no edges | degenerate base case; depth = 1; supervisor index for an agent with no deps |
| Linear chain | `linear-chain.vaked` | `A -> B -> C` | strict ordering; Pass 1 depth = 3 (counted in steps); source-order subscriptions |
| Diamond / fan-in | `diamond.vaked` | `A->B, A->C, B->D, C->D` | converging DAG; Pass 1 must de-dup the two equal paths to one depth (3); D records two upstream subscriptions deterministically |
| Depth-bound | `depth-bound-ok.vaked`, `depth-bound-exceeded.vaked` | 3-step chain, depth = 3 | the `depth > bound` boundary. OK fixture sets `maxDepth = 3` (== depth, must pass); exceeded sets `maxDepth = 2` (< depth, must be rejected) |
| Cycle | `cyclic.vaked` | `A->B->C->A` | step edges must form a DAG; back-edge must be rejected |

The depth-bound-ok fixture deliberately sets `maxDepth` **exactly equal** to the
actual critical-path depth. The Stage-0 check is `depth > bound`, so
`depth == bound` is the accepting boundary - more informative than a comfortable
margin.

## 3. Stage-0-now vs Stage-1-later

Stage-1 (the C++/MLIR `vaked`/`hcp` dialects and their passes) does not exist
yet. So the corpus is staged:

- **Stage-0 (now, this harness).** Pure-Python `vakedc` (`parse -> check ->
  lower`). For each should-lower fixture, lower the *same source file* into two
  separate temp dirs and assert the trees are byte-identical (round-trip
  determinism). For each should-reject fixture, run `check --json` and assert
  exit 1 plus the expected diagnostic code. This pins the Stage-0 oracle.
- **Stage-1 (later, drop-in).** When a Stage-1 lowering binary exists, add a
  `lower_stage1()` invocation (it is C++/MLIR - it builds and runs on
  **dev-cx53**, not the dev MacBook). For each should-lower fixture, run both
  stages and compare with a cross-stage comparator (§4). For each should-reject
  fixture, assert Stage-1's verifier/Pass-1 rejects the same input (§13.1
  soundness). The harness already documents this extension point in its module
  docstring and isolates the within-stage comparator so the cross-stage one
  slots beside it.

The Stage-0 leg is environment-independent stdlib Python and runs anywhere. The
future Stage-1 leg MUST run on dev-cx53 (per the project no-build-on-laptop
rule); the harness's Stage-0 assertions remain valid on either host.

## 4. Canonicalization note

Lowering is fully deterministic by construction: no timestamps, no randomness,
no UUIDs; dict keys are sorted and list order follows source order. Therefore
*within a stage* canonicalization is trivial - a direct recursive byte-compare
of the two emitted trees. No normalization layer is needed or built.

There is exactly **one** environment-dependent field, and it matters only for
the future cross-stage comparison. `gen`'s sibling `provenance.json` embeds the
**absolute source path** (`source`, and per-artifact `sourceFile`/`span.file`)
and a derived `inputsHash` (sha256 over inputs including that path). Two
lowerings of the *same* file from the *same* path produce identical
provenance - which is why the within-stage byte-compare is valid as written.

For Stage-1, the absolute path differs by host (local Stage-0 vs dev-cx53
Stage-1), so `provenance.json`'s source-path fields and `inputsHash` will differ
*even when the semantic artifacts are byte-identical*. The cross-stage
comparator therefore must **not** be a naive whole-tree byte-compare. It must
either:

- normalize/exclude the provenance source-path + `inputsHash` fields, or
- compare only the semantic artifacts: `gen/workflow/*.json`,
  `gen/eventd.json`, `flake.nix`, `gen/RUNTIME.md`.

This is the only caveat to "the equality check drops in cleanly", and it is
called out here and in the harness docstring so it is not a future surprise.

## 5. Pass/fail contract per fixture

| Fixture | Contract (Stage-0, today) | Contract (Stage-1, when it lands) |
|---------|---------------------------|-----------------------------------|
| `single-agent` | `lower` exit 0; 2 runs byte-identical | + Stage-0/Stage-1 semantic artifacts equivalent |
| `linear-chain` | `lower` exit 0; 2 runs byte-identical | + cross-stage equivalent |
| `diamond` | `lower` exit 0; 2 runs byte-identical | + cross-stage equivalent |
| `depth-bound-ok` | `lower` exit 0; 2 runs byte-identical | + cross-stage equivalent |
| `depth-bound-exceeded` | `check` exit 1; diagnostics include `E-WORKFLOW-DEPTH`; no artifacts | + Stage-1 Pass 1 rejects the same input |
| `cyclic` | `check` exit 1; diagnostics include `E-WORKFLOW-CYCLE`; no artifacts | + Stage-1 Pass 1 cycle detector rejects the same input |

Diagnostic codes are asserted via `vakedc check --json` (the `code` field), not
by matching human-readable message text, so the contract is stable across
message wording changes.

## 6. What this discharges for §11

Tickable now (Stage-0 leg):

- **Determinism** - byte-identical artifacts across two runs, proven for all
  four should-lower topologies.
- The Stage-0 **rejection oracle** for cycle and depth (the baseline §13.1
  soundness checks compare against).

Not tickable until Stage-1 exists (these are comparative, Stage-0↔Stage-1):

- Dialect verifiers reject the same invalid inputs as Stage-0.
- Pass 1 detects cycles / computes depths *identically to* Stage-0.
- Pass 2 / Pass 3 produce the same WAL / supervisor structures as Stage-0.
- Round-trip equivalence between Stage-0 and Stage-1.

C14 evidence gap is closed in the sense that a runnable oracle now exists, the
Stage-0 leg is green, Determinism is tickable, and the cross-stage boxes flip
when Stage-1 lands by adding the comparator described in §4.
