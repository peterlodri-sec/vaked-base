# AIL-0 bench — design spec (metrics / modes / corpus / model matrix)

## Status

Design (2026-06-14). Author-only; no runnable code. Bench implementation and
model-call execution are deferred to a separate dev-cx53/GHA plan (see
Execution Environment below). This doc is the contract that the implementation
plan must satisfy.

Related artefacts: issue #202 (ARP / AIL-0 control plane), PR #203 (CUC rename
+ five-model bench), `docs/superpowers/research/2026-06-14-ail-0-single-agent-research.md`
(evidence base, hereafter "research doc" with section references §N.N).

---

## Hypothesis to confirm or refute

Issue #202 claims 49-62% savings for ARP/AIL-0 mode compression.
**This is a hypothesis about TOKEN savings, not character savings.** The
research doc finds no direct token-savings evidence for register-tagged
compression: every stylistic-compression source that reports percentages either
counts characters (the wenyan 28% reduction is character-counted, research doc
§3.2) or asserts the figure without a named tokenizer or before/after token
counts (the telegraphic/caveman 40-60% claim is asserted, not measured, §3.2).
Register tags (`[R:plan]`, `[R:tool]`, `[R:artifact]`, etc.) are added tokens
with no measured payback in the evidence base (§2 honest accounting, §3.6). The
bench exists to confirm or refute 49-62% token savings, against a plain-NL
baseline, under honest tag-inclusive accounting.

---

## Execution environment

**All model calls and bench runs execute on dev-cx53 (Linux, Nix, Tailscale,
SSH: `ssh dev-cx53`) or on GitHub Actions. They never run on the developer
machine (M1 MacBook).**

The 3-gate verify-confirm protocol (CLAUDE.md) applies to every build or
model-invocation command:

- Gate 1 -- target verification: confirm dev-cx53 or GHA is the target, is
  reachable, and has the required toolchain and disk.
- Gate 2 -- intent confirmation: present the exact command(s) to the user with
  target host, estimated duration, and risk; require explicit approval.
- Gate 3 -- pre-flight check: on the target, verify repo sync, no dirty working
  tree, and toolchain version.

All three gates must pass in sequence before any model-call or bench run is
issued.

---

## Corpus shape

### Purpose

The corpus provides a stable, reproducible set of prompts whose compression and
output can be measured under each mode. Tasks are chosen to exercise the
distinct registers of AIL-0 (planning, tool intent, artifact production,
causality, risk) and to stress the boundaries the design cares about: literal
preservation, CJK leakage into artifacts, and reasoning-channel fidelity.

### Corpus dimensions

| Dimension | Value |
|-----------|-------|
| Total prompt-response pairs | 200 (minimum); 400 target |
| Prompt length distribution | short (< 200 tokens), medium (200-800 tokens), long (800-2 000 tokens) -- roughly 1/3 each |
| Task categories | planning / tool-intent / artifact / multi-step causality / risk annotation |
| Language of prompt | English only (v0 bench); no multilingual prompts in the initial corpus |
| Ground-truth control | each pair has an expected literal set (paths, symbols, API names, error strings, commit subjects) that must survive compression unchanged |

### Task categories (detail)

**Planning prompts** -- single-step or multi-step plans expressed in natural
language. These exercise `R:plan` and `R:think` registers. The baseline
(normal mode) is the full NL prompt; AIL modes must produce the same plan
content in compressed form.

**Tool-intent prompts** -- prompts that describe one or more tool invocations
(file read, git command, API call) with exact paths and argument literals.
These exercise `R:tool`. The ground-truth literal set for each such prompt
includes every file path, command flag, and API name that appears in the
prompt.

**Artifact prompts** -- prompts that ask the model to produce a final artifact:
a commit subject, an RFC section, a code snippet, a diff. These exercise
`R:artifact` and `R:commit`. The artifact-gate rule (reason free-form, gate
only the final output) is what the bench validates here.

**Multi-step causality prompts** -- prompts that ask the model to reason about a
sequence of steps and explain causality between them. These are the highest-risk
category for CJK leakage and for reasoning-quality loss under strict modes.

**Risk-annotation prompts** -- prompts that ask the model to identify and
annotate failure modes or risks. These exercise `R:risk`.

### What is compressed and measured

For each prompt-response pair, the bench records:

1. The baseline prompt (used as-is, `normal` mode).
2. For each non-normal mode: the mode-transformed prompt and the model response.

Token and character counts are recorded at three points: (a) prompt-in, (b)
model response out, (c) net total (prompt + response). All savings figures are
reported as deltas against the `normal` control for the same pair.

---

## The four modes

`normal` is the explicit control baseline against which all token and character
deltas are measured. Every other mode is measured as a signed delta from `normal`
for the same prompt-response pair.

| Mode | Description |
|------|-------------|
| `normal` | Full natural-language prompt; no compression; no register tags. The control baseline. |
| `cuc-wenyan-ultra` | Classical Chinese (wenyan-style) compression as defined by PR #203's CUC bench. Keep-exact items (paths, symbols, API names, error strings, commit subjects, tool arguments) remain in ASCII. No AIL register tags. |
| `ailish-pidgin` | AIL-0 register tags applied; reasoning channel (`R:think`, `R:plan`) is telegraphic / function-word-dropped English; artifact and tool channels (`R:artifact`, `R:tool`, `R:commit`) are English-only, no CJK, full syntax for keep-exact items. Lossy compression of the reasoning scaffold only. |
| `ailish-strict` | AIL-0 register tags applied; reasoning channel is AIL-grammar-valid compressed form; artifact and tool channels are schema-constrained and grammar-enforced at decode time. This mode has the highest tag overhead and the strictest artifact gate. |

The mode names are kept-exact strings: `normal`, `cuc-wenyan-ultra`,
`ailish-pidgin`, `ailish-strict`.

`ailish-strict` differs from `ailish-pidgin` in that it activates grammar-
constrained decoding for the `R:artifact` and `R:tool` outputs (research doc
§3.5, §3.7). The grammar enforcement overhead (compile time, per-token latency,
empirical coverage) must be measured separately for each mode and reported
alongside token/char savings (see Metrics).

---

## Metric definitions

All metrics are per-mode and per-model. Aggregate across the corpus is the
mean; the bench also reports p25/p75.

Token counts use the target model's tokenizer. Where models differ in tokenizer,
the bench reports each model separately -- never aggregates across tokenizer
families. The minimum tokenizer axis is cl100k\_base (OpenAI GPT family) and
o200k\_base (GPT-4o family); local GGUF models use their SentencePiece/BPE
vocabulary. Token figures and character figures are always reported in separate
columns and are never merged or used as proxies for each other.

### M1 -- net token savings (prompt + response, tag-inclusive)

One-line definition: `1 − (compressed_prompt_tokens + compressed_response_tokens + tag_tokens) / (baseline_prompt_tokens + baseline_response_tokens)`, where `baseline_*` is `normal` mode for the same pair and `tag_tokens` is the token cost of all AIL register tags added in the AIL modes (zero for `cuc-wenyan-ultra` and `normal`).

Accounting rule: register tags (`[R:plan]`, `[R:tool]`, `[R:artifact]`,
`[R:commit]`, `[R:risk]`, `[R:think]`, `[R:review]`, `[R:bench]`) are counted
as tokens in the compressed total. They are a net token tax. The formula above
already embeds them in the numerator. A negative M1 value means the mode costs
more tokens than `normal`.

Research anchor: §2 (honest accounting), §3.6 (CodeAgents is the only direct
DSL token-savings result; single-source, self-reported, no independent
replication -- M1 is the bench's answer to open-Q#1).

Note: M1 is independent of M2 (char reduction). They can diverge in sign.
See the wenyan case: −13.2% token savings on o200k\_base vs +6.4% token *cost*
on cl100k\_base for the same text (research doc §3.2). Report M1 per tokenizer.

### M2 -- character reduction (prompt + response)

One-line definition: `1 − (compressed_prompt_chars + compressed_response_chars) / (baseline_prompt_chars + baseline_response_chars)`, where `baseline_*` is `normal` mode for the same pair.

M2 is strictly character-based (Unicode code-point count). It is reported
separately from M1 and must never be cited as evidence of token savings.

Research anchor: §3.2 (wenyan 28% is character-counted, not token-counted;
all primary sources that report per-character figures report no corresponding
token figure, making M1 and M2 independently necessary, research doc §3.1 "no
primary source reports any character ratio").

### M3 -- parse-success rate

One-line definition: fraction of responses for which the AIL-0 parser produces a
well-formed parse tree (no syntax error, all declared registers present and
non-empty), evaluated on the response string alone.

Applicable modes: `ailish-pidgin`, `ailish-strict`. (Normal and wenyan have no
AIL register structure to parse.)

Research anchor: §3.5/§3.8 (JSONSchemaBench declared-vs-empirical coverage;
Guidance 41%, XGrammar 28%, Outlines 3% on GitHub-Hard schema complexity --
demonstrates that coverage is a load-bearing measurement for grammar-enforced
modes). M3 is the AIL-0-grammar analogue.

### M4 -- literal-preservation rate

One-line definition: fraction of keep-exact items (file paths, CLI flags,
API names, error strings, command arguments, commit subjects) from the ground-
truth literal set that appear byte-for-byte unchanged in the model response.

Research anchor: repo-ctx core design rule ("keep EXACT: file paths, symbols,
commands, API names, error strings, literals, commit subjects, tool arguments");
§3.7 (`[R:tool]` must preserve exact paths and symbols).

Note: this metric applies to all four modes, including `normal`. `normal` sets
the ceiling; AIL modes should not fall below it.

### M5 -- register-compliance rate

One-line definition: for `ailish-pidgin` and `ailish-strict`, fraction of
responses where every `[R:artifact]` and `[R:commit]` body is English-only (no
CJK codepoints) and every `[R:tool]` body contains no CJK codepoints and no
non-ASCII characters other than those present in the literal inputs.

Research anchor: §3.8 (IFEval strict/loose adherence to format instructions as
the evaluation model for instruction-following; open-Q#7 "frontier models follow
AIL-0 syntax: measure IFEval-style strict/loose adherence"). M5 is the per-
register analogue of strict instruction compliance.

The strict/loose distinction from IFEval applies here: strict requires exact
zero CJK codepoints in gated registers; loose applies minor normalization
(whitespace folding only) before checking.

### M6 -- repair cost (extra tokens to recover malformed output)

One-line definition: mean additional tokens consumed by a repair prompt issued
after a failed parse (M3 = 0 for a response), measured as the token count of
the repair prompt plus the corrected response, summed over all failed-parse
responses.

Applicable modes: `ailish-pidgin`, `ailish-strict`. Reported separately for
each.

Research anchor: §3.5/§3.8 (coverage collapse on complex schemas forces
re-generation; for the hard GitHub schema set, Outlines achieves only 3%
empirical coverage, meaning the majority of responses require re-try or repair).
M6 has no direct primary-source anchor in the research dossier for AIL-0
specifically -- it is a bench-novel extension of the coverage-collapse result.

### M7 -- artifact-CJK-leakage rate

One-line definition: fraction of responses where any CJK codepoint (Unicode
blocks CJK Unified Ideographs U+4E00-U+9FFF, CJK Extension A/B, Katakana,
Hiragana, Hangul) appears inside a `[R:artifact]`, `[R:commit]`, or `[R:tool]`
register body.

This metric applies to all modes, including `normal`. In `normal`, leakage can
occur on thinking models that mix languages in their CoT and let CJK drift into
the final output. In AIL modes, it measures gate effectiveness.

Research anchor: §3.4 (QwQ-32B-Preview officially documents CJK leakage into
final outputs; users report Chinese characters in Russian and Vietnamese
responses -- HF model card and discussion #16; note: QwQ-32B-Preview, NOT
DeepSeek-R1). Repo-ctx key invention: "`[R:artifact]` and `[R:commit]` bodies
must be English-only, no CJK" -- M7 is the operational measurement of that
invariant.

---

## Metric summary table

| ID | Name | Unit | Modes | Token/Char/Both |
|----|------|------|-------|----------------|
| M1 | Net token savings (tag-inclusive) | signed ratio (−1 to 1) | all | Token |
| M2 | Character reduction | signed ratio (−1 to 1) | all | Char |
| M3 | Parse-success rate | [0, 1] | ailish-pidgin, ailish-strict | N/A |
| M4 | Literal-preservation rate | [0, 1] | all | N/A |
| M5 | Register-compliance rate (strict/loose) | [0, 1] x 2 | ailish-pidgin, ailish-strict | N/A |
| M6 | Repair cost | tokens | ailish-pidgin, ailish-strict | Token |
| M7 | Artifact-CJK-leakage rate | [0, 1] | all | N/A |

M1 and M2 are always reported in separate columns. A table that shows only one
of them is incomplete. For M1, the cl100k\_base and o200k\_base columns are
required minimum; omitting either tokenizer is a measurement gap.

---

## Model matrix

The bench runs each (corpus item, mode) pair through every model in the matrix.
Models are grouped by category; a result without its model-and-tokenizer label
is not interpretable.

| Category | Model(s) | Notes |
|----------|----------|-------|
| General chat | GPT-4o (o200k\_base tokenizer); Claude 3.5 Sonnet (cl100k\_base proxy) | Two tokenizer families; enables direct M1 per-tokenizer comparison |
| Thinking / extended reasoning | QwQ-32B-Preview; DeepSeek-R1 | **QwQ and DeepSeek-R1 are distinct models with distinct behaviors.** The −5.6pp MATH500 monolingual-Chinese-reasoning result (research doc §3.4, §3.7) is from QwQ-32B-Preview, not from R1. R1 has its own language-consistency reward and is excluded from the QwQ finding. Report their M7 values separately; do not attribute QwQ results to R1. |
| Single-turn diff / code | GPT-4o in structured-output mode; CodeAct-capable model if available | Tests M4 (literal preservation) and M3 (parse in strict mode) under high-precision output demands |
| Local GGUF | Llama-3.1-8B or equivalent, run via llama.cpp on dev-cx53 | Tests grammar-constrained decoding overhead (M6 repair cost, M3 empirical coverage) against a known low-cost baseline; uses SentencePiece/BPE tokenizer -- report M1 separately from OpenAI-family runs |

For `ailish-strict`, the bench records the grammar-constrained-decoding
framework in use (Guidance/llguidance, XGrammar, Outlines, or llama.cpp GBNF),
the grammar compile time, and the per-token latency (TPOT), alongside M1-M7.
Framework selection is a load-bearing decision (research doc §3.5: Guidance
~0.00s vs Outlines ~3.48s compile; TPOT Guidance 6.37ms vs Outlines 30.33ms vs
unconstrained 15.40ms for Llama-3.1-8B). The AIL-0 EBNF should stay simple
enough to avoid the coverage cliff documented for complex schemas (Outlines 3%
on GitHub-Hard, §3.5).

---

## Research-evidence gaps the bench must close

The following are open questions from the research dossier (§5) that this bench
is specifically designed to answer. No prior source provides the answer; the
bench is the primary measurement.

1. Does AIL-0 register-tagged format net-save tokens vs plain NL on the target
   tokenizer? (§5 open-Q#1 -- the bench answers this as M1.)
2. Does stylistic function-word dropping in `ailish-pidgin` cut tokens
   measurably? (§5 open-Q#2 -- answered as M1 delta for `ailish-pidgin` vs
   `normal`.)
3. Does the artifact gate (`R:artifact`/`R:commit` English-only, `R:plan` free)
   preserve downstream accuracy? (§5 open-Q#3 -- answered as M5, M7, and task
   accuracy per pair.)
4. Does reserving a free reasoning span in AIL-0 help vs hurt? (§5 open-Q#4 --
   ablation: `ailish-strict` with and without free `[R:think]` block.)
5. Is per-char savings a reliable proxy for per-token savings in AIL modes?
   (§5 open-Q#5 -- answered by comparing M1 and M2 columns; the wenyan case
   shows they can diverge in sign.)
6. What is the empirical coverage and TPOT for the actual AIL-0 EBNF under the
   chosen constrained-decoding framework? (§5 open-Q#6 -- answered as M3 and
   the grammar-overhead measurements.)
7. Do frontier models follow AIL-0 syntax reliably? (§5 open-Q#7 -- answered as
   M5 strict/loose, M3, and IFEval-style adherence counts.)

---

## Output format requirements

The bench produces a results table in comma-separated or JSON Lines format with
the following required fields per row:

```
corpus_id, mode, model, tokenizer, prompt_tokens_baseline,
prompt_tokens_compressed, response_tokens_baseline,
response_tokens_compressed, tag_tokens, m1_net_token_savings,
prompt_chars_baseline, prompt_chars_compressed, response_chars_baseline,
response_chars_compressed, m2_char_reduction, m3_parse_success,
m4_literal_preservation, m5_register_compliance_strict,
m5_register_compliance_loose, m6_repair_tokens, m7_cjk_leakage,
grammar_framework, grammar_compile_s, tpot_ms
```

Fields that do not apply to a (mode, model) combination are recorded as `null`,
not omitted. Every row must carry `tokenizer` explicitly because M1 values
from different tokenizer families are not comparable and must not be aggregated
across families.

---

## Acceptance criteria (inspection)

1. Every metric (M1-M7) has exactly one one-line operational definition above.
2. M1 and M2 are in separate sections with separate formulas; nowhere are they
   conflated or used as mutual proxies.
3. The tag-tax (register-tag tokens) is included in the M1 numerator formula
   explicitly; a sentence states that the formula already embeds them.
4. The AIL-0 register sigils (`R:think`, `R:plan`, `R:tool`, `R:risk`,
   `R:artifact`, `R:commit`, `R:review`, `R:bench`) appear verbatim wherever
   referenced; none are paraphrased or abbreviated.
5. The model matrix explicitly states that QwQ-32B-Preview and DeepSeek-R1 are
   distinct models, and that the −5.6pp MATH500 result is attributable to QwQ,
   not R1.
6. The 49-62% savings figure is identified as a hypothesis from issue #202 to
   confirm or refute on tokens (not chars), with a statement that the research
   dossier found no direct token-savings evidence for register-tagged
   compression.
7. The execution environment section states "never on the developer machine" and
   names dev-cx53 and GHA as the only permitted targets with the 3-gate
   protocol.
8. No Python, no runnable code, no language-tagged executable code fence appears
   anywhere in this document.
