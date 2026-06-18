# Live experiment report — dogfood lower + RUNTIME.md mesh-grant fix

**Date:** 2026-06-16 · **Root:** `vaked-base` @ `main` · **Scope:** local only, nothing pushed.

## What this was

A prior session authored three Vaked blocks and handed off one open action: "run the
lower." This session reproduced that lowering on the field root, and in verifying the
output found and fixed a real gap in the `docs.runtime` emitter. This report documents
the run, the finding, the fix, and the verification — written for a human reviewer, with
honest calibration of what is proven vs. asserted.

## 1. The lower (reproduce the prior claim)

Tool: `vakedc` (pure-Python, stdlib-only) — `python3 -m vakedc`. This is an interpreter
run, not a compile/build, so it does not trip the project's "never build on the developer
machine" rule. `vakedz` (Zig) was not used (no prebuilt binary; a build is forbidden).

**check** — all three exit 0, zero diagnostics:

| Block | Result |
|---|---|
| `vaked/examples/crabcc-umami.vaked` | no diagnostics |
| `vaked/examples/editorial-pipeline.vaked` | no diagnostics |
| `vaked/examples/session-drive-loop.vaked` | no diagnostics |

One benign warning on each: Unicode data version mismatch (pinned 15.1.0 vs runtime
16.0.0) — affects only edge-case NFC codepoints, none present in these files.

**lower** — all three exit 0, emitting to per-block out-dirs under `.vaked/lower/`:

| Block | Out-dir | Files emitted (first run) |
|---|---|---|
| crabcc-umami | `.vaked/lower/crabcc-umami/` | 7 |
| editorial-pipeline | `.vaked/lower/editorial-pipeline/` | 10 |
| session-drive-loop | `.vaked/lower/session-drive-loop/` | 9 |

Each tree carries `flake.nix`, `provenance.json`, and a `gen/` subtree (nix modules, OTP
supervisors, Zig daemon configs, workflow DAG JSON, catalogs, eventd config). `provenance.json`
is content-addressed: per-artifact `inputsHash` (sha256) + source span + emitter id.

**Conclusion:** the prior session's claim — "each lowered by vakedc, the checker earned its
keep" — reproduces on this root. POLA is enforced at **check** time; lowering is gated to
emit nothing if the checker reports a single diagnostic (0012 §1).

## 2. The finding

The `docs.runtime` emitter that produces `gen/RUNTIME.md` had a hardcoded "Capability
grants" section reading *"No `mesh` or `capability` declarations in this runtime…"* —
emitted unconditionally, regardless of the source. It never iterated the runtime's `mesh`
declarations.

Two of the three blocks (`editorial-pipeline`, `session-drive-loop`) contain full `mesh`
blocks with attenuated POLA grant-sets. Their generated RUNTIME.md therefore *wrongly
stated no grants existed* — the single most security-relevant section of the doc, blank.

**Severity:** doc-emitter only. The functional artifacts were always correct — the workflow
JSON carried the right agent→node bindings, and POLA is a check-time property the checker
already validated. The defect was that the human-facing rendering under-reported. Located
at `vakedc/lower.py` (the section-7 block of `emit_docs_runtime`).

## 3. The fix

Three edits to `vakedc/lower.py`:

1. Added a `meshes` field to `_RuntimeView` (the runtime decomposition dataclass).
2. Populated it in `_runtime_view` via `_by_kind(children, "mesh")`.
3. Rewrote section 7: when `rv.meshes` is non-empty, render a per-mesh grant-set table
   (Principal · Role · Capabilities, source order) using the existing `_render_ref_list`
   and `_children_of` helpers; otherwise keep the original no-mesh fallback verbatim.
4. Added mesh provenance entries to the RUNTIME.md provenance list, mirroring the existing
   per-section pattern.

No grammar, checker, or functional-emitter change — purely the doc renderer.

## 4. Verification

Re-lowered all three blocks (exit 0, same file counts: 7/10/9). The editorial-pipeline
RUNTIME.md now renders the table below — reproduced here with backticks/commas stripped for
readability; the values are verbatim from the generated file:

```
### mesh `field`
| Principal   | Role            | Capabilities                                            |
| editor      | editor-in-chief | fs.repo_rw, network.egress, mcp.github_write, mem.admin |
| researcher  | research        | fs.repo_ro, network.lan, mem.recall                     |
| drafter     | drafting        | fs.repo_ro, mem.append                                  |
| factChecker | fact-check      | fs.repo_ro, network.lan, mem.recall                     |
| publisher   | publish         | fs.repo_rw, mcp.github_write, mem.recall                |
```

This makes the editorial guarantee legible: `publisher` is the sole non-editor holder of
`mcp.github_write`; the read-only roles (researcher/drafter/factChecker) hold no write or
publish grant. `crabcc-umami` (no mesh) still emits the fallback sentence — confirmed the
conditional branches correctly.

## 5. Honest limits (not yet proven)

- Re-lowering was confirmed via the editorial block's rendered table and the crabcc
  fallback. The session-drive-loop table was not separately pasted here (same code path,
  exit 0).
- No automated test was added for the new branch (a `vakedc` test run / build was out of
  scope under the no-build rule; the change was verified by running the lower and reading
  output).
- The fix is unit-untested; correctness rests on the live lower output above, not a
  regression test. Adding a `tests/` case for "mesh present → grant table rendered" is the
  obvious follow-up.

## 6. Status

Local only — no commit, no push, no PR. Source blocks already committed; `.vaked/lower/`
is generated. Carry-forward: add a regression test for the mesh-grant rendering branch.
