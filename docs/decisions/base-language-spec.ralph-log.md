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

## 2026-06-13 — Decision #2: Decision / question
- **Track:** base-language-spec · **Models:** stage1 qwen3-235b-a22b-thinking-2507 · stage2 deepseek-v4-pro
- **Context snapshot:** HEAD f1a3820, 6 open issues

**Decision / question**  
Should we define catalog schemas for the remaining grammar kinds — `network`, `filesystem`, `mcp`, `ebpf`, `observability` — to eliminate the schema‑less gap identified in Issue #28, now that `budget`, `runclass`, and `host` have been handled (slices #28/#47/#49)?

**Options**  
- **A. Concrete schemas + open fallback.**  Define a concrete, closed schema for `network` (calibrated on `vaked/examples/membrane/agent-egress.vaked`) and **open** schemas for `filesystem`, `mcp`, `ebpf`, `observability` (like `device`/`mediaPipeline`). This immediately forbids arbitrary bodies while keeping the kind as a forward‑compatible placeholder for future policy/manifest declarations.  
- **B. Leave schema‑less, defer to usage.**  Keep the five kinds without schemas, accepting anything, and wait until a concrete daily‑use example forces a design — the current `check` gap remains but no new constraints are added prematurely.  
- **C. Remove the redundant kinds.**  Drop `filesystem`, `mcp`, `ebpf`, `observability` from the grammar’s `kind` list entirely (they already exist as capability domains; only `network` has an actual kind‑declaration example). This shrinks the language surface but risks breaking any future intent to declare membranes/policies of those domains.

**Recommendation**  
**Option A** — concrete schema for `network`, open schemas for the rest.  

- The `network` membrane example (`agent-egress.vaked`) gives a clear body shape: `principal`, `default` (allow/deny), a list of egress rules, and an `observe` stream — exactly the shape a catalog schema should enforce (Issue #28 asks “each should either get a schema or be considered for removal”).  
- For `filesystem`/`mcp`/`ebpf`/`observability` there is **no current usage as a top‑level declaration** in the codebase, so a concrete schema would be speculative.  An **open** schema (`open` keyword) is the lightweight middle ground: it marks the kind as *intended for future membrane/policy artifacts* while still rejecting arbitrary bodies (an `open` schema accepts unknown fields, which is precisely the forward‑compatible posture used for `device` and `mediaPipeline` in `vaked/schema/parallel-types.md`).  This aligns with the audit directive in Issue #28 — “audit the rest and decide schema‑vs‑remove per kind.”  

Option B keeps Issue #28 open and violates the urgency (the gap is still “undermines the entire type system’s integrity”).  Option C removes the *grammar* keywords, but `network` already has a working membrane example; removing it would break the vertical slice landed in `395b0d6`.

**Risks**  
- The concrete `network` schema must match the existing membrane usage byte‑for‑byte; any mismatch (e.g., wrong field name) would cause the working `agent-egress.vaked` to fail `vakedc check`.  This is mitigated by deriving the schema directly from that example.  
- Open schemas still admit unknown fields, so they do not enforce structure yet — they are a **holding pattern** documented as deferred.  That is acceptable: it’s the same pattern used for `device` and `mediaPipeline` (mentioned in `vaked/grammar/README.md` and `parallel-types.md`).  
- Adding open schemas might falsely suggest that the kinds are “ready” for lowering; the fact that they carry `open` and belong to the deferred target list (0012-lowering.md §7) makes the status clear.

**Next actions**  
1. Open a PR that adds `schema network` (fields: `principal: String`, `default: String { oneof ["allow","deny"] }`, `allow: List<EgressRule> { optional nonempty }`, `observe: Stream<…>?`) to `vaked/schema/builtins.vaked` and `vaked/schema/parallel-types.md`, along with the necessary auxiliary types (`EgressRule` with `host`/`port`).  
2. In the same PR, add **open** schemas for `filesystem`, `mcp`, `ebpf`, `observability` — a single `open` statement per schema, no fields.  
3. Re‑run `vakedc check` against `agent-egress.vaked` to confirm the membrane example now conforms.  
4. Update the completeness test from Decision #1 (PR #??) so the grammar‑vs‑registry cross‑check accounts for the new schema coverage.

**Confidence**  
**High**.  The `network` kind’s body shape is directly observable in the membrane vertical slice, and the open‑schema pattern is already established and tested for `device`/`mediaPipeline`.  Completing these five schemas closes the last major schema‑less audit item from Issue #28, removing a variance that allowed arbitrary validation behavior.

