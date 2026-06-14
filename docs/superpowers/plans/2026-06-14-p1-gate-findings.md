# P1 Research Gate — Findings & Decisions (2026-06-14)

Gate output for the Vaked V1.0 credibility-fix SDD plan
(`docs/superpowers/plans/2026-06-14-credibility-review-fixes-sdd.md`, PR #254).
Three parallel P1 research agents ran read-only; this is the durable ledger of
their decisions so downstream waves survive context compaction.

**Status:** P1 COMPLETE / gate PASS. P2 (Wave-2 spec) in progress on branch
`lang/wave2-runtime-pola` (stacked on `lang/execution-semantics` / PR #257).
P3 code blocks on P2 green per the SDD DAG.

---

## 🔑 Critical-path discovery (independently confirmed ×2)

The **use-check `used(p)` / `E-CAP-USE` is specified but NOT implemented** in
`vakedc/check.py`. Today the checker enforces only:
`E-CAP-UNKNOWN-DOMAIN`, `E-CAP-UNKNOWN-GRANT`, `E-CAP-ORDER-CYCLE`,
`E-CAP-ORDER-DANGLING`, and `E-CAP-ATTENUATION` (mesh edges only).
There is no `used(p)` computation and no `E-CAP-USE` diagnostic.

Consequences:
- `0011 §4.5` soundness clause (2) ("the use check guarantees…") is currently
  **unbacked** — a reviewer greps the checker and finds the gap in minutes.
- Risk-6 negative test #8 (granted-but-unused) is **blocked** on this.
- Mechanizing the POLA proof now would certify a premise the tool doesn't run.

**Sequencing rule:** implement the use-check (a P3 code task) BEFORE negative
test #8 and BEFORE any proof mechanization (RFC 0017).

---

## Decisions per risk

### Risk 1 — POLA soundness proof (CRITICAL) → **(B) now + (A) deferred**
- Claim lives only in `docs/language/0011-type-system.md §4.5` (lines ~381–405).
  README/PROJECT_CONTEXT already hedge ("POLA checked at type-time").
- **(B):** apply honest-wording edits to §4.5 — replace
  "sound / guarantees / proves / certifies" with "informal argument", flag the
  use-check implementation gap, soften the cyclic-case claim. Exact from→to
  pairs captured in the P2 spec task.
- **(A) deferred:** scaffold mechanization as RFC `0017-pola-formalization.md`
  (Lean4/Mathlib or Coq). Abstract model proof ≈4–6 person-days (low risk; the
  cycle-degeneracy lemma is the only soft spot). The model→`check.py` faithfulness
  link is a 2–4 week sink — **keep off the v1.0 critical path**. RFC must state
  the use-check is a prerequisite.

### Risk 5 — runtime enforcement missing (HIGH) → **RFC 0016 design ready**
- Design an `RFC 0016-runtime-enforcement.md`: minimal `agent-guardd` Zig daemon
  + `ebpf.policy` emitter that fills the deferred `0012 §7` registry slot.
- Stage-1 scope = network egress only, via `cgroup_connect` allow-list compiled
  from capability grant-sets; default-deny; verdicts → `eventd` (tamper-EVIDENT).
- Carries PR #249's observe-vs-enforce type law into lowering (refuse to emit an
  enforcing program from an observe-only hook).
- Honest non-goals: tamper-evident ≠ tamper-proof; POLA ≠ semantic correctness;
  DNS name↔IP mismatch is a Stage-1 limitation; compromised root/kernel out of scope.
- Stage-1 acceptance: emitter is a pure projection emitting canonical JSON +
  provenance; manifest→BPF passes the kernel verifier; Zig daemon builds 0 warnings;
  reference example end-to-end (allow granted endpoint, deny others, both logged).

### Risk 2 — determinism data contradicts (HIGH) → **it's a fabrication**
- There is **no 20-iteration oracle** in the code. `tests/spec/*_determinism()`
  run exactly **2×** and byte-compare. The "18/19 vs 20" conflates the
  *differential-oracle* agreement count (`n_match/n_total` over 15 examples +
  v0.2 probes, `test_vakedc.py:_test_differential`) with a fabricated determinism
  story.
- Fix (P3/P4): build a real 100-iteration baseline harness
  (`tests/spec/determinism_baseline.py`) reusing `lower.inputs_hash` /
  `_canonical_projection_json`; emit `tests/spec/golden/baseline-2026-06-14.json`
  with SHA-256 per (example, stage); target ≥99.5% convergence on valid rows.
  Command: `python3 tests/spec/determinism_baseline.py --iters 100 --out …`.
- Paper fix: report the two real numbers separately; footnote the documented
  one-sided EBNF-recognizer newline over-permissiveness
  (`tests/spec/README.md` §Known oracle limitations) and the
  `lexer.py PINNED_UNICODE = "15.1.0"` NFC boundary (warning, not error).

### Risk 4 — scalability super-linear (HIGH) → **bottleneck pinned**
- `vakedc/lower.py:_children_of` (L204–213) full-scans `graph.edges` per parent
  → O(parents × edges) ≈ O(N²). Fix (P3): one-time adjacency index
  `source_id → [contains-children]` built in `graph.py` (single O(E) pass);
  `_children_of` reads the map. `get_node` is already O(1).
- **`schedule.py` is ORTHOGONAL** — it computes a wavefront schedule + cycle
  detection for parallel groups and is consumed by `overlay.py`/`check.py`, NOT
  wired into lowering. It does not address `_children_of`.
- Need a scale-fixture generator (`tests/spec/gen_scale_fixture.py`) — N ∈
  {10,100,500,1K,5K,10K}, independent + chained topologies; `wavefront.vaked`
  (3 fibers) is only a shape template. Publish measured table; re-run after fix
  to show linearization, else publish honest complexity statement.

### Risk 6 — negative POLA tests (MEDIUM) → **5 now, 2 after #251, 1 blocked**
8 negative `.vaked` cases (fixtures under `vaked/examples/types/`, exact-code
goldens like `tests/spec/golden/rejected.diagnostics.json`):
1. receiver exceeds sender on mesh edge → `E-CAP-ATTENUATION` — **now**
2. undeclared domain → `E-CAP-UNKNOWN-DOMAIN` — **now**
3. unknown grant in domain → `E-CAP-UNKNOWN-GRANT` — **now**
4. ordering cycle → `E-CAP-ORDER-CYCLE` — **now**
5. dangling order ref → `E-CAP-ORDER-DANGLING` — **now**
6. holds > needs → `W-POLA-EXCESS` — **after PR #251 merges** (warning)
7. one holder is `->` target of ≥2 callers → `W-CONFUSED-DEPUTY` — **after #251**
8. granted-but-unused → `E-CAP-USE` — **BLOCKED on use-check impl**
Negative-test harness must assert on diagnostic `code`, not just error presence
(cases 6–7 are warnings). Bump `EXPECTED_VAKED_COUNT` in
`tests/spec/test_examples_parse.py` when adding fixtures.

---

## Numbering (resolved)

`0013-traversable-execution`, `0014-typed-capability-graph`,
`0015-inline-arp-compiled-execution` are taken (PR #257). Therefore:
- **`0016-runtime-enforcement.md`** (Risk 5) — new, this wave.
- **`0017-pola-formalization.md`** (Risk 1 deferred-A) — new, this wave (scaffold only).
Both are language-series docs (depend on 0011/0012/0014), so they live in
`docs/language/`, NOT `protocol/rfcs/`. Add both to the design-series index.

## Wave → PR mapping (in-flight)

| PR | Wave / risk |
|----|-------------|
| #254 | the roadmap (P0 ✅) |
| #257 | full-vision language core 0013/0014/0015 (base for this stack) |
| #256 | Wave 1 docs coverage |
| #251 | Wave 2 — `W-POLA-EXCESS` / `W-CONFUSED-DEPUTY` lints (#226) |
| #250 | Wave 2/3 — determinism boundary on control-flow (#224) |
| #249 | Wave 2 — eBPF observe/enforce typing (#225) |

## Next steps

- **P2 (this branch):** author 0011 §4.5 (B) edits + RFC 0016 + RFC 0017 scaffold;
  doc-links + `run_all.py` green. → stacked PR on #257.
- **P3 (next, blocks on P2 green):** worktree fan-out — use-check impl (unlock),
  adjacency-index + scale fixtures, determinism baseline harness, negative tests 1–5.
- **P4/P5:** emitter status matrix, novelty matrix, diagrams, abstract patches,
  stacked-PR integration.
