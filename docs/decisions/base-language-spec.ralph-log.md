# Ralph decision log — base-language-spec

> Machine-generated, ADVISORY. Each entry is one strategic decision surfaced by the ralph loop (qwen3-235b-thinking → deepseek-v4-flash). A human ratifies; entries are appended, never rewritten.

## 2026-06-13 — Decision #1: Decision / question
- **Track:** base-language-spec · **Models:** stage1 qwen3-235b-a22b-thinking-2507 · stage2 deepseek-v4-pro
- **Context snapshot:** HEAD eaea540, 0 open issues

**Decision / question**  
How should we verify that the lowering process (Goal 3, `docs/language/0012-lowering.md`) covers **all** language features — every declared `kind`, every built‑in schema, and every `capability` domain — so that Vaked reliably “compiles to boring, inspectable artifacts” for *every* primitive, not just the ones we have recently wired?

**Options**  
- **A. Manual completeness matrix.** Write a prose document listing each of the 29 `kind`s, the registered emitter(s) that handle it, and the deferred targets, then review by hand against the registry in `0012-lowering.md` §3.4.  
- **B. Automated completeness verification.** Add a spec‑level test that parses the grammar’s `kind` list (`vaked/grammar/vaked-v0-plus.ebnf`, the `kind` production) and the emitter registry (`0012-lowering.md` §3.4) and asserts that every kind either has at least one `always`/`emit`‑selected/runtime‑plane emitter, is a meta‑kind (`schema`, `capability`) with no direct artifact, or is explicitly documented as deferred with a concrete tracking issue.  
- **C. Wait until deferred targets are resolved, then revisit.** Defer the systematic check and rely on the existing `vakedc check`/`lower` test suite that only covers the already‑implemented emitters.

**Recommendation**  
Adopt **Option B** (automated completeness verification). The grammar already defines an exhaustive list of 29 `kind` keywords (`vaked/grammar/vaked-v0-plus.ebnf`, line `kind = "runtime" | "input" | … | "memory"`), and the lowering spec’s static registry (`0012-lowering.md` §3.4) partitions these into `always`, `emit‑selected`, `runtime plane`, and `deferred` targets. A deterministic test can cross‑reference the two, flagging any kind that is not accounted for. This gives **continuous enforcement** of the “compiles to boring, inspectable artifacts” promise as both the language and the lowering evolve — exactly the bottleneck signalled by the recent OTP supervision (`cbac1cf`) and host deployment (`33a3329`) work, which touched *new* kinds but lacked a central completeness check.

**Risks**  
- The test must be kept in sync with the registry when emitters are added or deferred targets are explained; however, the registry is already a structured table and the grammar is normative — a well‑written test will fail conspicuously until both are aligned.  
- Some kinds (e.g., `budget`, `runclass`) are value‑types referenced by other declarations and produce no stand‑alone artifact; the completeness definition must account for these explicitly (e.g., “no direct emitter – used as a value”).  
- The test cannot validate the *quality* of the lowering, only that a mapping exists, but that is the precise verification needed to close this bottleneck.

**Next actions**  
Open a PR adding a new spec test, e.g. `tests/spec/test_lowering_completeness.py`, that:
1. Extracts the set of `kind` keywords from `vaked/grammar/vaked-v0-plus.ebnf`.
2. Parses the emitter‑target/kind associations from the registry table in `docs/language/0012-lowering.md` §3.4 (or from a machine‑readable copy thereof).
3. Asserts that every grammar kind appears in at least one emitter’s selection set, or is explicitly listed as a meta‑kind / value‑only kind / deferred with a tracking issue.
4. Fails the CI if any kind is missing coverage.

This test directly addresses the “without verified completeness” concern raised in the decision’s `why_now`, and it becomes the living answer for all future language additions.

**Confidence**  
High. The grammar’s `kind` list is unambiguous, the lowering registry in `0012-lowering.md` is manually maintained but well‑bounded, and the test is a straightforward cross‑reference that can be mapped directly to the documents we have. Recent lowering PRs (#38, #51, #33) all explicitly reference the registry, confirming that the mapping is already the touchstone.

