# AIL-0 (Wave 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development /
> executing-plans. Steps use checkbox (`- [ ]`). Read `00-repo-ctx.md` (same dir) first — it
> holds the binding facts and the NEVER-BUILD constraint. This is Wave 1 of the ARP umbrella
> plan (`docs/superpowers/plans/2026-06-14-arp-e2e-naive.md`).

**Goal:** Author the AIL-0 grammar + spec layer — the formal, EBNF-governed register language
that ARP (issue #202) uses as its wire convention — as a set of committable docs. AUTHOR-ONLY:
nothing compiles or runs on this machine.

**Architecture:** A tiny register grammar (`[R:think] [R:plan] [R:tool] [R:risk] [R:artifact]
[R:commit] [R:review] [R:bench]`) with a keep-exact / compress split and a grammar-level artifact
gate. Five doc deliverables + one GitHub issue.

**Tech stack:** EBNF, Markdown. No code execution.

---

## ✅ Research-resolved design decisions (from run `wru7qq2ax`, see research doc)

1. **Glyph set: ASCII-canonical.** Evidence: rare-Unicode/CJK glyph density can *increase* token
   count (byte-fallback inflation); register tags are already pure token *tax* with no measured
   payback. So operators are ASCII-canonical: `-> => bc so par merge conflict != ~= <= >=`
   (Unicode forms allowed only as optional, non-normative sugar). The EBNF (Task 2) and morpheme
   table (Task 3) encode ASCII as canonical.
2. **Gate artifacts, NOT reasoning.** Forcing tight structure on the *reasoning* channel collapses
   accuracy (rigid JSON dropped Claude-3-Haiku GSM8K 86.51%→23.44%); NL-then-format recovers it.
   So `[R:think]`/`[R:plan]` bodies stay free-text (loosely constrained); only
   `[R:tool]`/`[R:artifact]`/`[R:commit]` carry tight grammar + the gate.
3. **Keep the grammar SIMPLE.** Constrained-decoding coverage collapses on complex schemas
   (empirical coverage 3-41% on hard grammars). A small grammar is a correctness requirement, not
   just taste.
4. **AIL-0 token savings are a HYPOTHESIS.** No direct evidence that hand-authored register
   compression saves tokens; the tags cost tokens. The bench (Task 5) must measure NET tokens
   (incl. the tag tax) per-tokenizer, not characters.

---

## File structure

| File | Responsibility |
|------|----------------|
| `docs/context/cuc-v2-ail-bootstrap.md` | Bridge note: CUC=style, AIL=grammar substrate, ARP=protocol; keeps PR #203 honest |
| `protocol/ail/ail-v0.ebnf` | The AIL-0 grammar (the spine) |
| `protocol/ail/examples/*.ail` | 3-5 worked example frames the EBNF must accept |
| `docs/language/0025-ail-morphemes.md` | ≤80-entry morpheme/register/op table |
| `protocol/rfcs/0009-ail-register-language.md` | RFC, `hcp-rfc-author` structure |
| `docs/superpowers/specs/2026-06-14-ail-bench-design.md` | Bench DESIGN (metrics/modes/matrix) — no Python |

Placement note: AIL-0 lives under `protocol/ail/` (NOT `vaked/grammar/`, which is the Vaked
language). AIL is ARP's register protocol → protocol/ tree. This is a decision; record it in the RFC.

---

## Task 1: Bootstrap / bridge doc

**Files:** Create `docs/context/cuc-v2-ail-bootstrap.md`

- [ ] **Step 1:** Write the doc. Required content:
  - The name stack table (AIL / AIL-0 / CUC / ARP / HCP) from `00-repo-ctx.md`.
  - One paragraph: CUC V1 = compression *style* (wenyan-ultra, PR #203); AIL = grammar-governed
    substrate; ARP (#202) = the model-agnostic protocol that carries AIL frames.
  - The core rule (keep-exact vs compress) with its two lists.
  - A "keeps PR #203 honest" note: #203 stays a rename+bench PR; AIL-0 is the V2 bridge on its own
    branch and references it.
  - A forward-pointer: artifact gate stays English-normalized until the AIL-0 parser exists.
- [ ] **Step 2:** Acceptance (inspection): file exists; name stack matches `00-repo-ctx.md`
  exactly; no claim that the parser/bench already runs; links to #202, #203 present.
- [ ] **Step 3:** Commit `docs(context): add CUC-V2/AIL-0 bootstrap bridge note`.

## Task 2: AIL-0 EBNF grammar + examples  (glyph decision RESOLVED → ASCII-canonical)

**Files:** Create `protocol/ail/ail-v0.ebnf`, `protocol/ail/examples/{plan,risk,artifact}.ail`

- [ ] **Step 1:** Write the EBNF. Start from the boot grammar (message → frame+; frame =
  `[` register `]` stmt (`;` stmt)*; register/stmt/relation/action/gate/atom productions). Operators
  are **ASCII-canonical** (`-> => bc so par merge conflict != ~= <= >=`); Unicode forms are optional
  sugar only, marked non-normative. Registers:
  `R:think R:plan R:tool R:risk R:artifact R:commit R:review R:bench`. gate_name:
  `artifact english no_cjk ci bench parse`; gate_state: `pass fail warn skip`. Keep it SMALL
  (coverage-cliff constraint).
- [ ] **Step 2:** Encode the artifact gate AS grammar but **only on output registers**:
  `artifact-frame ::= "[R:artifact]" english-text` and a `[R:commit]` conventional-commit-English
  rule. `[R:think]`/`[R:plan]` bodies are free-text (a permissive production) — do NOT impose tight
  structure on reasoning (it collapses accuracy; see research). `[R:tool]` preserves exact literals.
- [ ] **Step 3:** Write 3 example `.ail` files (a plan frame, a risk frame, an artifact frame)
  that the grammar must accept — these are the conformance fixtures.
- [ ] **Step 4:** Acceptance (inspection — NO parser run): every example frame is derivable from
  the EBNF by hand-trace; keep-exact atoms (path/symbol) have productions; glyph set matches the
  research decision. **Do not run any parser/generator.**
- [ ] **Step 5:** Commit `feat(ail): AIL-0 v0 EBNF grammar + conformance examples`.

## Task 3: Morpheme table  (depends on Task 2 grammar)

**Files:** Create `docs/language/0025-ail-morphemes.md`  (0025 — 0019 is taken; see 00-repo-ctx)

- [ ] **Step 1:** Write a ≤80-entry table grouped: Registers, Causal ops, Parallel ops, State,
  Actions, Safety/gates. Each row: token, one-atomic-concept gloss, which registers use it.
- [ ] **Step 2:** Add a "tokenizer-observed, not tokenizer-perfect" note: per-provider token cost
  varies; the bench measures it. Cite the research finding on symbol/CJK token cost.
- [ ] **Step 3:** Acceptance: ≤80 entries; every register/op/gate used in the EBNF appears here
  and vice-versa (no orphans); header follows the `docs/language/00NN-*` series style.
- [ ] **Step 4:** Commit `docs(language): 0025 AIL-0 morpheme table`.

## Task 4: RFC stub  (depends on Task 2; use hcp-rfc-author skill)

**Files:** Create `protocol/rfcs/0009-ail-register-language.md`  (0009 — 0008 claimed; see 00-repo-ctx)

- [ ] **Step 1:** Invoke the `hcp-rfc-author` skill and follow its required RFC structure.
- [ ] **Step 2:** Content: AIL-0 core register language. Acceptance criteria (from the boot spec):
  EBNF parses all sample frames; morpheme table ≤80; `[R:artifact]` requires English output; bench
  compares `normal / wenyan-ultra / ailish-pidgin / ailish-strict`; gate reports token savings,
  char reduction, parse success, artifact CJK leakage, literal preservation, register compliance,
  repair cost. Dock to issue #202 (ARP); reference PR #203. Record the `protocol/ail/` placement
  decision and the glyph decision with the research rationale.
- [ ] **Step 3:** Acceptance: matches `hcp-rfc-author` structure; numbered 0009; cross-links #202,
  #203, the EBNF, and the morpheme doc; no off-convention `LFC-` prefix.
- [ ] **Step 4:** Commit `rfc(0009): AIL-0 register language`.

## Task 5: Bench DESIGN spec  (design only — NO Python)

**Files:** Create `docs/superpowers/specs/2026-06-14-ail-bench-design.md`

- [ ] **Step 1:** Specify the bench WITHOUT implementing it: corpus shape, the 4 modes, the metric
  definitions (token savings vs char reduction kept SEPARATE; parse-success; literal-preservation;
  register-compliance; repair-cost; artifact-CJK-leakage), and the model matrix (general chat,
  thinking, single-turn/diff, local GGUF).
- [ ] **Step 2:** Add an explicit "runs on dev-cx53/GHA, never locally" note and a 3-gate pointer.
  State that #202's 49-62% is a hypothesis the bench must confirm/refute on TOKENS not chars.
- [ ] **Step 3:** Acceptance: every metric has a one-line operational definition; token vs char
  separation explicit; no Python; ties each metric to a research finding where one exists.
- [ ] **Step 4:** Commit `docs(spec): AIL-0 bench design (metrics/modes/matrix)`.

## Task 6: GitHub issue  (controller-only; OUTWARD — gated on user confirm)

- [ ] Open an issue "AIL-0: core register language (CUC V2 / AI-lish)" docked under #202, listing
  the Task-4 acceptance criteria and linking the RFC + EBNF. **Do not auto-open**; the controller
  confirms with the user first (outward action).

---

## Execution order (fan-out)

- Resolve the glyph decision from research → then:
- Parallel-safe set A (disjoint files): Task 1, Task 5. Task 2 (spine) authored first or alongside.
- After Task 2 settles: Task 3, Task 4 (they reference the grammar).
- Task 6 last, gated.

## Self-review checklist (controller, before kickoff)

- [ ] Glyph decision resolved from research and reflected in Tasks 2 & 3.
- [ ] Numbering: morphemes=0025, RFC=0009. No `.claude/skills/cuc/` touched.
- [ ] Every task is author-only; no step runs a build/test/parser locally.
- [ ] Each register/op/gate appears in BOTH the EBNF and the morpheme table.
