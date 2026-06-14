# AIL-0 followup spec (reconciled, evidence-grounded)

> The original input had two halves that contradicted on scope: a full-slice spec (`ctx:::`) and an
> opinion essay (`DO=`) arguing against an implementation storm. This spec reconciles them and
> grounds the design in research runs `wru7qq2ax` (single-agent core) and `wnlq8ckib` (multi-agent
> / adapter). Companion files: `00-repo-ctx.md`, `02-plan.md`, `03-subagent-instructions.md`.

## 1. What AIL-0 is (reconciled)

AIL-0 = a small, ASCII, EBNF-governed, **register-tagged** notation for LLM-agent communication.
It is a *register language*, not a full language (the `DO=` position wins on scope). It is the
formal grammar for the text conventions that ARP (issue #202) carries.

Name stack: **AIL** (Agentic Intermediate Language) / **AIL-0** (experimental v0) / **CUC**
(human-facing compression skill, PR #203) / **ARP** (Agent Register Protocol, issue #202) / **HCP**
(project wire protocol, RFCs 0001-0007).

Core rule: compress what NL wastes (reasoning scaffold, causality, sequencing, confidence, task
state, register transitions); keep EXACT what machines need (paths, symbols, commands, API names,
errors, literals, commit subjects).

## 2. Evidence-grounded design principles (from `wru7qq2ax`)

These are corrections the research forced on the boot spec:

1. **ASCII-canonical operators.** Rare-Unicode/CJK glyph density can *increase* token count
   (byte-fallback). The boot spec's `-> => bc so` etc. are ASCII; Unicode (`→ ⇒ ∵ ∴`) is optional
   non-normative sugar only.
2. **Gate artifacts, not reasoning.** Forcing tight structure on reasoning collapses accuracy
   (rigid JSON: Claude-3-Haiku GSM8K 86.51%→23.44%; mechanism = field-order forcing answer-before-
   reason). NL-then-format recovers it. So `[R:think]`/`[R:plan]` are free-text; only
   `[R:tool]`/`[R:artifact]`/`[R:commit]` are tightly structured + gated. This is the research's
   strongest validation of the register split.
3. **Keep the grammar small.** Grammar-constrained decoding coverage collapses on complex schemas
   (empirical coverage 3-41% on hard grammars). Simplicity is a correctness requirement.
4. **Token savings are a HYPOTHESIS, not a claim.** AIL-0's distinctive mechanism — hand-authored
   register-tagged compression — has *no direct token-savings evidence*. Register tags are pure
   token *tax*. The wins in the literature come from (a) algorithmic low-information removal
   (LLMLingua up to 20x tokens, ~1.5pt accuracy loss) and (b) replacing verbose NL with a genuinely
   more compact structured form (CodeAgents 55-87% input-token cut — but single-source, partly
   definitional). AIL-0 should lean on info-density, and prove net savings on the bench.
5. **Do not conflate turns/chars with tokens.** CodeAct's "fewer actions/turns" is NOT token
   evidence. Per-char savings do not imply per-token savings. The bench measures TOKENS.

## 3. Grammar (ASCII, small)

Registers: `R:think R:plan R:tool R:risk R:artifact R:commit R:review R:bench`.

```
message        ::= frame+
frame          ::= "[" register "]" stmt (";" stmt)*
stmt           ::= atom | relation | action | gate
relation       ::= atom op atom
op             ::= "->" | "=>" | "bc" | "so" | "par" | "merge" | "conflict" | "!=" | "~=" | "<=" | ">="
action         ::= verb "(" args? ")"
gate           ::= "gate(" gate_name ":" gate_state ")"
gate_name      ::= "artifact" | "english" | "no_cjk" | "ci" | "bench" | "parse"
gate_state     ::= "pass" | "fail" | "warn" | "skip"
atom           ::= ident | path | symbol | quoted | number
; --- gate as grammar, OUTPUT registers only ---
artifact-frame ::= "[R:artifact]" english-text     ; no CJK
commit-frame   ::= "[R:commit]" conventional-commit ; English only
; --- reasoning registers stay free-text ---
think-frame    ::= "[R:think]" free-text
```

(Authoritative EBNF is Task 2's `protocol/ail/ail-v0.ebnf`; this is the sketch.)
Placement: `protocol/ail/` (NOT `vaked/grammar/`, which is the Vaked language). AIL is ARP's
register protocol.

## 4. Morpheme table

`docs/language/0025-ail-morphemes.md` (0025 — 0019 is taken). <=80 entries, grouped Registers /
Causal ops / Parallel ops / State / Actions / Safety-gates. Tokenizer-observed, not tokenizer-
perfect: per-provider token cost varies and the bench measures it. Every token here must appear in
the EBNF and vice-versa.

## 5. Bench design (token-honest)

`docs/superpowers/specs/2026-06-14-ail-bench-design.md`. Modes:
`normal / cuc-wenyan-ultra / ailish-pidgin / ailish-strict`. Metrics, each with TOKEN and CHAR
kept SEPARATE: net token savings (incl. the register-tag tax), char reduction, parse-success,
literal-preservation, register-compliance, repair-cost, artifact-CJK-leakage. Model matrix: general
chat / thinking (note: QwQ != DeepSeek-R1) / single-turn-diff / local GGUF. Runs on dev-cx53/GHA
only (NEVER BUILD). Issue #202's 49-62% is a hypothesis to confirm/refute on TOKENS.

## 6. Scope reconciliation (ctx vs DO)

THIS batch (author-only, local): bootstrap doc, EBNF, morpheme table (0025), RFC (0009), bench
DESIGN spec, dock issue under #202. (The `DO=` minimal-bridge discipline.)

DEFERRED (separate plan, dev-cx53/GHA): `tools/cuc-bench/*.py` + the multi-model bench run;
`.claude/skills/cuc/` TODO after PR #203 merges; the ARP driver (Waves 2-3 of the umbrella plan).
(The `ctx:::` full slice, staged — not stormed.)

## 7. Open questions / thin evidence (the bench must settle)

- Does hand-authored register compression net-save TOKENS after the tag tax, per tokenizer? (No
  evidence either way.)
- Does the artifact gate hold on thinking models without an accuracy hit? (Leakage measured on QwQ,
  not R1; generality unknown.)
- Does a small EBNF avoid the constrained-decode coverage cliff in practice?

## 8. ARP / multi-agent context (from `wnlq8ckib`)

Run `wnlq8ckib` (multi-agent / adapter, 5 strands) lands three load-bearing findings:

1. **Conventions do NOT port across providers** — the strongest-supported result, and the empirical
   case for ARP having an *adapter* layer rather than one canonical convention. A prompt tuned for
   one model carries a large penalty to another (PromptBridge: 99.39%→68.70% transferred, a 10.77pp
   "model drift"; FormatSpread: up to 76 accuracy points from format alone, weakly correlated across
   models; IFEval++: 18.3-61.8% reliability decline under convention-preserving paraphrase). The fix
   is measured too: format-recovery alone +6-8 F1, a verifier-driven repair step +14-16 F1, reaching
   ~99.3% of oracle (PromptPort). → **ARP adapter = a bidirectional schema↔target translator with a
   built-in output validator/repair step**, not just an emitter.
2. **KQML / FIPA-ACL failed because their semantics were mentalistic** — defined over the sender's
   private beliefs, so compliance was not third-party-checkable, and dialects drifted until agents
   could not interoperate (Singh 1998). → **AIL-0 register discipline must be publicly checkable
   (defined over observable artifacts — what was written, not what an agent believes) and tight
   enough to prevent dialect drift, with a complete act/intent vocabulary.**
3. **Structured handoffs help; a shared compressed IR at swarm scale is unproven.** Typed handoff
   discipline measurably helps — ReWOO's reasoning/observation channel split cut tokens ~5x
   (9,795→1,986) with a small accuracy gain (the best evidence FOR the register split); MetaGPT's
   structured artifacts hit 85.9% HumanEval Pass@1; AgentAsk's clarification at handoffs recovers
   most of a heavy evaluator's gain at <5% overhead. BUT no located source ablates a *designed shared
   compressed IR* against no-IR at fan-out scale, MAST finds structure alone insufficient for
   inter-agent misalignment, and adding stages that reprocess context without new information
   *degrades* reliability (.907 centralized → .435 at 3 stages). → **AIL-0's shared-IR ambition is a
   hypothesis; the bench must ablate IR vs no-IR, not assume the win.**

These feed the ARP adapter layer (umbrella plan Wave 2 — the `adapters.md` + `validate.py` are now
evidence-backed) and the umbrella plan's honest framing. Full report:
`docs/superpowers/research/2026-06-14-arp-multiagent-research.md`.

## 9. References

- Research: `docs/superpowers/research/2026-06-14-ail-0-single-agent-research.md` (run `wru7qq2ax`),
  `docs/superpowers/research/2026-06-14-arp-multiagent-research.md` (run `wnlq8ckib`).
- Issue #202 (ARP), PR #203 (caveman→cuc + 5-model bench), PR #187 (CUC origin).
- Umbrella plan: `docs/superpowers/plans/2026-06-14-arp-e2e-naive.md`.
