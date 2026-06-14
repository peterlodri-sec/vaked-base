# AIL-0 Wave-1 — Subagent dispatch instructions

Per-task prompts for the fan-out batch. Each prompt is self-contained: a fresh subagent has NO
session history. The controller pastes SHARED-PREAMBLE + the task block as the agent prompt.
Source of truth: `00-repo-ctx.md` (facts/constraints) and `02-plan.md` (task detail), same dir.

## Dispatch model

- Mechanism: a Workflow fan-out (disjoint files → low conflict) OR subagent-driven-development
  (sequential implementer + 2-stage review). For author-only doc tasks, a Workflow pipeline is fine
  because there are no local test steps to serialize.
- Order: resolve glyph decision → Task 2 (spine) → then Task 1, 3, 4, 5 (1 & 5 independent of 2).
- Models: Task 2 (grammar design) + Task 4 (RFC) = most capable; Task 1, 3, 5 = standard.
- Agents are AUTHOR-ONLY (write files, no git). The controller commits each file sequentially after
  the agent returns. Task 6 (GitHub issue) is controller-only and user-gated.

---

## SHARED-PREAMBLE (prepend to EVERY task prompt)

```
You are a fresh implementer with no prior context. Read these constraints; they are absolute.

ENVIRONMENT
- Repo: vaked-base. You are on branch worktree-feat+ail-0-bridge (a worktree off origin/main).
- First, READ docs/superpowers/batch/2026-06-14-ail-0/00-repo-ctx.md in full. It defines AIL-0,
  the name stack, the verified numbering, and the scope boundary. Do not contradict it.

HARD CONSTRAINTS (violating any = task failure)
- 🚫 NEVER BUILD / RUN on this machine. This task is AUTHOR-ONLY: write markdown/EBNF text only.
  Do NOT run python, pytest, a parser, a generator, nix, cargo, zig, make, or any build/test.
  If you think you must run code to verify, STOP and report instead — verification is by
  inspection / hand-trace only.
- Numbering is fixed: any docs/language file = 0025 (0019-0024 taken). Any RFC = 0009 (0008 taken).
- Do NOT create or edit .claude/skills/cuc/ — it is PR #203's deliverable; touching it races an
  open PR.
- Keep-exact rule: never alter file paths, symbols, API names, commit subjects, or literals.
- Surgical: create only the file(s) your task names. Do not refactor or touch adjacent files.
- Do NOT run git. Do NOT commit. WRITE your file(s) only and report their paths. The controller
  commits sequentially — a worktree has ONE shared git index, so parallel commits collide on
  `.git/index.lock`. Your "Commit subject" is a SUGGESTION the controller will use.

REPORT FORMAT (your final message = the controller reads it, the user does not)
- Status: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
- Files created (exact paths). The suggested commit subject. (No SHA — you did not commit.)
- For DONE_WITH_CONCERNS/BLOCKED: the specific issue in one or two lines.
```

---

## TASK 1 — bootstrap bridge doc  (model: standard)

```
Create docs/context/cuc-v2-ail-bootstrap.md.
Content required:
1. The name-stack table (AIL / AIL-0 / CUC / ARP / HCP) — copy it from 00-repo-ctx.md verbatim.
2. One paragraph distinguishing: CUC V1 = compression STYLE (wenyan-ultra, shipped in PR #203);
   AIL = grammar-governed substrate; ARP (issue #202) = the model-agnostic protocol carrying AIL
   frames.
3. The core rule with BOTH lists: keep-exact (paths, symbols, commands, API names, errors,
   literals, commit subjects) vs compress (reasoning scaffold, causality, sequencing, confidence,
   task state, register transitions).
4. A "keeps PR #203 honest" note: #203 stays a rename+bench PR; AIL-0 is the V2 bridge on its own
   branch and references it.
5. A forward-pointer: the artifact gate stays English-normalized (prose rule) until the AIL-0
   parser exists.
Acceptance (inspection): file exists; name stack matches 00-repo-ctx.md; no claim that any
parser/bench already runs; links to #202 and #203 present.
Commit subject: docs(context): add CUC-V2/AIL-0 bootstrap bridge note
```

## TASK 2 — AIL-0 EBNF + examples  (model: most capable)

```
DESIGN IS RESOLVED FROM RESEARCH (see docs/superpowers/research/2026-06-14-ail-0-single-agent-research.md):
- Operators are ASCII-CANONICAL: -> => bc so par merge conflict != ~= <= >=  (Unicode forms are
  OPTIONAL, non-normative sugar only). Rationale: rare-Unicode/CJK glyphs can INCREASE token count.
- Gate OUTPUT registers only; reasoning stays free. Forcing structure on reasoning collapses accuracy.
- Keep the grammar SMALL — constrained-decoding coverage collapses on complex grammars.

Create protocol/ail/ail-v0.ebnf and protocol/ail/examples/{plan,risk,artifact}.ail.

EBNF must define: message ::= frame+ ; frame ::= "[" register "]" stmt (";" stmt)* ; registers
R:think R:plan R:tool R:risk R:artifact R:commit R:review R:bench ; stmt = atom | relation | action
| gate ; relation = atom op atom (op = the ASCII set above) ; action = verb "(" args? ")" ; gate =
"gate(" gate_name ":" gate_state ")" ; atom = ident | path | symbol | quoted | number. gate_name:
artifact english no_cjk ci bench parse ; gate_state: pass fail warn skip.
GATE AS GRAMMAR, OUTPUT ONLY: artifact-frame ::= "[R:artifact]" english-text ; and a [R:commit]
conventional-commit-English rule. [R:think]/[R:plan] bodies = a permissive free-text production
(do NOT tightly constrain reasoning). [R:tool] preserves exact path/symbol literals (real productions).
Write 3 example .ail frames (plan / risk / artifact) the grammar accepts — conformance fixtures.
Acceptance (NO parser run): each example is hand-derivable from the EBNF; ASCII ops canonical;
reasoning registers are free-text; output registers are gated.
Commit subject: feat(ail): AIL-0 v0 EBNF grammar + conformance examples
```

## TASK 3 — morpheme table  (model: standard; needs Task 2's settled grammar)

```
Create docs/language/0025-ail-morphemes.md (0025 — NOT 0019; see 00-repo-ctx).
A table of <=80 entries grouped: Registers, Causal ops, Parallel ops, State, Actions, Safety/gates.
Each row: token | one-atomic-concept gloss | which registers use it. Tokens MUST match the EBNF in
protocol/ail/ail-v0.ebnf exactly (no orphans either direction). Add a short "tokenizer-observed,
not tokenizer-perfect" note and cite the research finding on per-provider symbol/CJK token cost.
Header style follows the existing docs/language/00NN-*.md series.
Acceptance: <=80 entries; every register/op/gate in the EBNF appears here and vice-versa.
Commit subject: docs(language): 0025 AIL-0 morpheme table
```

## TASK 4 — RFC stub  (model: most capable; USE the hcp-rfc-author skill; needs Task 2)

```
Invoke the hcp-rfc-author skill and follow its required RFC structure. Create
protocol/rfcs/0009-ail-register-language.md (0009 — NOT LFC-0001; see 00-repo-ctx).
Subject: AIL-0 core register language. Include acceptance criteria: EBNF parses all sample frames;
morpheme table <=80; [R:artifact] requires English output; bench compares normal / wenyan-ultra /
ailish-pidgin / ailish-strict; gate reports token savings, char reduction, parse success, artifact
CJK leakage, literal preservation, register compliance, repair cost. Record the protocol/ail/
placement decision and the glyph decision with the research rationale. Dock to issue #202; reference
PR #203, the EBNF, and the 0025 morpheme doc.
Acceptance: matches hcp-rfc-author structure; numbered 0009; cross-links present; no LFC- prefix.
Commit subject: rfc(0009): AIL-0 register language
```

## TASK 5 — bench DESIGN spec  (model: standard; design only, NO Python)

```
Create docs/superpowers/specs/2026-06-14-ail-bench-design.md. SPECIFY the bench; do not implement.
Cover: corpus shape; the 4 modes (normal / cuc-wenyan-ultra / ailish-pidgin / ailish-strict); metric
definitions with TOKEN-savings and CHAR-reduction kept SEPARATE; plus parse-success, literal-
preservation, register-compliance, repair-cost, artifact-CJK-leakage; and the model matrix (general
chat / thinking / single-turn-diff / local GGUF). Add an explicit "runs on dev-cx53 or GHA, never
locally; 3-gate protocol applies" note. State that issue #202's 49-62% is a hypothesis to confirm or
refute on TOKENS (not chars). Tie each metric to a research finding where one exists.
Acceptance: every metric has a one-line operational definition; token-vs-char separation explicit;
no Python anywhere.
Commit subject: docs(spec): AIL-0 bench design (metrics/modes/matrix)
```

---

## Controller notes
- Fold research `wru7qq2ax` findings into: the glyph decision (Task 2), the tokenizer note (Task 3),
  the metric-to-evidence ties (Task 5), and the RFC rationale (Task 4).
- 2-3 refine passes target THIS file's prompts before dispatch (clarity, literal-preservation,
  NEVER-BUILD reinforcement, scope-tightness).
- Commit the research docs under docs/superpowers/research/ before/with the kickoff.
```
