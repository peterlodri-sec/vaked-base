# Token optimization and compression protocols for LLM agent communication (2024-2026)

Status: **Research synthesis** | Created: 2026-06-14 | Method: web, primary-leaning, abstain-safe
Scope: three areas - (1) grammar/structured-IL compression, (2) tokenizer fragmentation across model families, (3) syntactic-hallucination mitigation + repair-token cost. Relevance to Vaked: the EBNF-first language, the caveman compression mode, and the multi-model swe_af fleet (OpenRouter across Llama/Qwen/DeepSeek).

## Executive summary

Grammar-constrained decoding (EBNF/GBNF/JSON-Schema enforced at the logit level) is now the industry-standard way to guarantee *syntactic* validity of agent output, shipped in every major inference engine and provider. But it buys validity at a measured cost: 10-30% reasoning-quality degradation under hard constraints, driven by distributional shift, token-grammar mismatch, and field-ordering effects. Compressed symbolic formats (TOON and kin) cut tokens ~40% in the favorable (uniform-tabular) case - not the ~90-98% sometimes advertised - and their parse-success depends on the tokenizer: the same compressed string fragments differently across Llama/Qwen/DeepSeek, so a format tuned for one can lose its edge or mis-parse on another. The robust pattern emerging is "draft then constrain" (generate reasoning unconstrained, enforce structure second) plus a validation gate, which preserves reasoning while eliminating the format-failure class.

## Area 1 - Grammar-enforced / structured intermediate languages

Findings (evidence grade in brackets):

- **Constrained decoding is mainstream and engine-default.** [HIGH] XGrammar (persistent parse stack + context-independent pre-checks, reported ~100x faster than prior grammar libs) is the default structured-generation backend in SGLang, vLLM, and TensorRT-LLM; Outlines uses FSM/regex+CFG; GBNF (from llama.cpp) is the lightweight CPU/single-GPU path used by Ollama. OpenAI shipped Structured Outputs "Strict Mode" (constrained decoding) Aug 2024; by 2025-2026 every major provider adopted the same logit-mask approach.
- **It works at the token level: schema-valid by construction.** [HIGH] JSONSchemaBench (Jan 2025) tested 6 frameworks over ~10,000 real-world JSON schemas; constrained decoding guarantees schema-valid output at the token level.
- **Type/grammar guidance helps semantic, not just syntactic, validity - to a point.** [MEDIUM] Mundler et al. (PLDI 2025) report type-constrained decoding cuts compilation errors 74.8% vs 9.0% for syntax-only constraints. But "syntactically valid" is not "functionally correct."
- **Structured IL compresses agent payloads.** [MEDIUM] Reported tool-schema slimming (keep name/description/parameters, drop OpenAPI verbosity + whitespace) ~40% tokens/tool; action-chain bundling (ELHPlan) ~24% of prior token usage; structured action encoding ("[Action: Move North, Reason: ...]") reduces output tokens vs prose.

Vaked implication: Vaked's grammar-first stance (EBNF before code) is exactly the substrate constrained decoding consumes. A `.vaked`/HCP EBNF can be compiled to a GBNF/XGrammar grammar and used to *enforce* agent output, not merely document it. The 0019/0020 dialect verifiers (ODS) are the static analogue; constrained decoding is the generation-time analogue.

## Area 2 - Tokenizer fragmentation across model families

Findings:

- **Same text, different token counts - material, not marginal.** [HIGH] A 10k-character prompt can cost ~30% more on one model than another purely from tokenizer-vocabulary differences. Online counters approximate within ~+/-3% of reference tokenizers for Llama/Mistral/DeepSeek/Qwen.
- **Per-family compression differs sharply, esp. on non-ASCII / symbols / CJK.** [MEDIUM] Reported special-character token shares on one corpus: Llama 14.6%, Qwen2.5 12.1%, DeepSeek-V3 5.1%; DeepSeek-V3 and Qwen3 have stronger CJK compression than peers. A symbol-dense compressed format is therefore *not* tokenizer-neutral.
- **Consequence for compressed symbolic formats.** [MEDIUM, inferred] A format optimized to minimize tokens under one tokenizer can fragment badly under another (heavy punctuation/symbols split into many tokens), eroding the savings and raising mis-parse risk. Compression ratios must be measured per target model, not assumed.

Vaked implication: the caveman wenyan-ultra mode and any HCP wire-shorthand should be token-benchmarked per swe_af target model (Llama/Qwen/DeepSeek on OpenRouter). A symbol-heavy "ultra" form that wins on one tokenizer may lose on another; CJK (wenyan) compresses well on DeepSeek/Qwen but may fragment on Llama. This is a measurable gate, not a guess - mirrors 0024's "measure, do not assume" discipline.

## Area 3 - Syntactic hallucination + repair-token cost

Findings:

- **Constrained decoding eliminates the format-failure class - removing repair cost at the source.** [HIGH] Narrowing the output space to grammar/schema-admissible tokens makes malformed output impossible by construction; this removes the regex/JSON.parse-and-retry repair loop entirely (the repair tokens are never spent because the failure never happens). Pair with a validation gate on everything returned.
- **But hard constraints degrade reasoning 10-30%.** [HIGH] Documented causes: (a) **field ordering** - if the answer field precedes the reasoning field, the model commits before its chain-of-thought, degrading quality; (b) **token-grammar mismatch** - grammars constrain at character level while models emit multi-char tokens, forcing rare/non-canonical tokenizations; (c) **distributional shift** - masking+renormalizing alters the distribution at every token. "Structured outputs create false confidence": syntactically valid != correct.
- **Mitigation = decouple planning from enforcement.** [MEDIUM] Draft-Conditioned Constrained Decoding (DCCD) and CRANE generate an unconstrained reasoning draft first, then apply constraints conditioned on it - preserving reasoning while guaranteeing validity. Earley-driven dynamic pruning and XGrammar-2 attack the throughput cost.

Vaked implication: two concrete rules. (1) In any Vaked/HCP structured frame, put reasoning/rationale fields *before* the decision field (field-ordering effect) - this also matches the caveman "reason then answer" pattern and argues against ultra-compression that strips the reasoning slot. (2) Prefer draft-then-constrain over hard one-pass constraint for reasoning-heavy agent steps; reserve strict constrained decoding for the final structured emission.

## Claim audit / corrections

- **"Compression up to 98%"** [REFRAME] - traced to marketing/edge-case copy. The peer benchmark (arXiv 2603.03306, TOON vs JSON, plain + constrained decoding) reports ~40% token reduction with 76.4% vs JSON 75.0% accuracy on uniform-tabular data; savings shrink or invert for non-uniform/nested/wide-row data (YAML better when nested, CSV best when flat, JSON better when non-uniform). Treat TOON-class formats as specialized, not universal. Use ~40% (favorable case), not 90-98%, as the planning figure.
- **"Constrained decoding is strictly better"** [REFRAME] - false. JSONSchemaBench / the TOON benchmark find plain JSON generation often has the best one-shot and final accuracy; constrained decoding's only consistent win is lowest token usage, traded against slight-to-significant accuracy degradation per model.

## Evidence quality

- HIGH: industry adoption of constrained decoding; tokenizer count disparity; constrained decoding removes format-failure class; reasoning degradation is real and measured.
- MEDIUM: specific percentage figures (40% tool slimming, 24% action chains, special-char shares, 10-30% degradation) - drawn from individual papers/benchmarks, directionally consistent but corpus-dependent; would firm up with multi-source replication.
- LOW / not independently verified this session: exact arXiv claims not deep-fetched (IDs cited for traceability, not quoted verbatim beyond the search abstracts).

## Open questions

- Does compiling the Vaked/HCP EBNF to GBNF/XGrammar and enforcing it on swe_af agents net-save tokens *after* the reasoning-degradation tax, per target model?
- What is the measured per-tokenizer (Llama/Qwen/DeepSeek) compression of caveman full vs ultra vs wenyan-ultra on representative agent traffic?
- For Vaked frames, does draft-then-constrain beat one-pass constraint on the swe_af task suite, and by how much repair-token saving?

## Recommended next steps

1. Token-benchmark caveman {full, ultra, wenyan-ultra} across Llama/Qwen/DeepSeek tokenizers on a real swe_af transcript sample; record per-model ratios (gate, not assumption).
2. Prototype: compile a small HCP frame EBNF to GBNF, A/B enforce-vs-prompt on one model, measure validity + accuracy + tokens.
3. Adopt the field-ordering rule (reason-before-decision) in any structured Vaked/HCP frame spec.

## Appendix - sources (abstain-safe: all probes returned; none rate-limited; arXiv IDs cited for traceability, not all deep-fetched)

- XGrammar-2 (efficient dynamic structured generation) - arXiv 2601.04426; SynCode - arXiv 2403.01632; Lookahead-then-Verify CFG decoding - arXiv 2602.00612
- [JSONSchemaBench](https://arxiv.org/pdf/2501.10868) (rigorous structured-output benchmark, Jan 2025)
- Mundler et al., type-constrained decoding (PLDI 2025) - via [grammar-constrained generation overview](https://tianpan.co/blog/2026-04-16-grammar-constrained-generation-output-reliability)
- [Structured Outputs | Awesome-LLM-Inference-Engine (DeepWiki)](https://deepwiki.com/sihyeong/Awesome-LLM-Inference-Engine/4.7-structured-outputs)
- TOON vs JSON benchmark - [arXiv 2603.03306](https://arxiv.org/abs/2603.03306); critical analysis - [dev.to](https://dev.to/ikaganacar/toon-benchmarks-a-critical-analysis-of-different-results-5h66); [InfoQ](https://www.infoq.com/news/2025/11/toon-reduce-llm-cost-tokens/); [toon-format/toon](https://github.com/toon-format/toon)
- TOON token reduction / MCP optimization - [MindStudio](https://www.mindstudio.ai/blog/reduce-token-usage-ai-agents-mcp-optimization)
- Tokenizer comparison (Llama/Qwen/DeepSeek special-char + CJK) - [TechEon, Medium](https://atul4u.medium.com/tokenizer-comparison-part2-comprehensive-tokenizer-performance-analysis-a8e0613bed0d); [DeepSeek vs Llama 4 vs Qwen3, Spheron](https://www.spheron.network/blog/deepseek-vs-llama-4-vs-qwen3/)
- Draft-Conditioned Constrained Decoding - [arXiv 2603.03305](https://arxiv.org/pdf/2603.03305); CRANE (reasoning + constrained generation) - [arXiv 2502.09061](https://arxiv.org/html/2502.09061v3); Earley-driven dynamic pruning - [arXiv 2506.01151](https://arxiv.org/pdf/2506.01151)
- "Structured Outputs Create False Confidence" - [BAML blog](https://boundaryml.com/blog/structured-outputs-create-false-confidence)

Method note: abstain-safe applied - no probe was rate-limited or 403'd this session, so nothing was marked refuted-by-abstention; uncertain figures are graded MEDIUM/LOW rather than dropped.
