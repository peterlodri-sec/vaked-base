# AI-lish V1 / ARP — prior-art research (cited)

**Date:** 2026-06-14 · **Method:** deep-research workflow (fan-out search → fetch → 3-vote adversarial verify → synthesize). 111 agents.

## Question

Prior art for compact USER<->LLM agent-reasoning notations and intermediate representations: how do existing structured agent/prompt languages and trace formats (DSPy, LMQL, Guidance/llguidance, Outlines, SGLang, structured-output/JSON-schema tool-use, agent event-log and reasoning-trace formats, ReAct/scratchpad notations, and token-efficiency/compressed-prompt techniques) represent reasoning, tool-use, dataflow, and control flow — and how does an SSA execution-graph notation with explicit dataflow edges, typed atoms, per-register structural rules, and a token-compaction layer (the "AI-lish V1 / ARP" design for human<->LLM communication) compare? What is genuinely novel vs prior art, what are the known pitfalls (e.g. LLMs hallucinating around math-symbol operators), and what evidence exists on token savings from dense notations?

## Summary

Prior art for compact human<->LLM agent-reasoning notations clusters into three layers that an SSA execution-graph notation ("AI-lish V1 / ARP") would touch but not duplicate. (1) Constrained-decoding / structured-output engines (LMQL, SGLang, llguidance, Outlines, Guidance) operate at the token-mask level: they enforce a grammar/regex/JSON-schema on a single LM call and model inter-call dataflow only incidentally (SGLang's async stream/computational graph is the closest prior art to explicit dataflow edges); none of them represent reasoning, and DSPy explicitly positions itself above this layer by optimizing prompts rather than constraining tokens. (2) Reasoning/control notations (ReAct scratchpads, Prompt Decorators) are pattern-matched by the model rather than parsed, which is exactly the documented pitfall for any symbol-operator notation: behavior is non-deterministic across sessions, and a 2024 critique found ReAct's interleaved-reasoning mechanism is largely illusory (performance tracks exemplar-query similarity, not reasoning content). (3) Token-compaction techniques (TOON, LLMLingua) provide the strongest empirical evidence that dense notations save tokens (LLMLingua up to 20x with ~1.5pt loss on GSM8K/BBH; TOON ~26% fewer generated tokens vs JSON), but the savings are structure-dependent and bought at a correctness cost when the format is only prompt-enforced (TOON drops ~39% in generation correctness vs JSON when not natively supported, and loses its edge on deeply nested data). Genuinely novel in the AI-lish/ARP design relative to this prior art appears to be the combination of SSA-form with explicit dataflow edges, typed atoms, and per-register structural rules as a human-readable reasoning IR plus a token-compaction layer; the closest individual analogues are SGLang's compiled computational graph (dataflow) and TOON/LLMLingua (compaction), but no surveyed system unifies SSA reasoning representation with compaction, and the dominant known risk is that LLMs pattern-match rather than deterministically parse symbol operators, producing drift and structural-correctness loss.

## Verified findings

### 1. Constrained-decoding query languages (LMQL) generalize prompting into a text+scripting language with explicit control flow and output constraints, and constraint/control-flow-aware decoding yields measurable compute savings (26-85% on pay-to-use APIs).

- **confidence:** high · **vote:** 3-0 (merged from claims 0,1,2)
- **sources:** https://arxiv.org/abs/2212.06094
- **evidence:** LMQL (arXiv 2212.06094, ETH Zurich, OOPSLA 2023) 'generalizes language model prompting from pure text prompts to an intuitive combination of text prompting and scripting' (LMP), 'allows constraints to be specified over the language model output,' and 'leverages the constraints and control flow from an LMP prompt to generate an efficient inference procedure' producing '26-85% cost savings ... in the case of pay-to-use APIs' via token-level inference masks. This is prior art for a control-flow/scripting layer over prompts, but it constrains/scripts text generation rather than representing reasoning as a typed dataflow graph.

### 2. SGLang represents structured LM programs via a small primitive set (gen with optional regex constraint, select, extend/+=, fork, join), models inter-call dataflow as an asynchronous stream / compilable computational graph with blocking-fetch dependency synchronization, and accelerates constrained decoding via a compressed FSM (1.6x JSON throughput).

- **confidence:** high · **vote:** 3-0 (merged from claims 3,4,5)
- **sources:** https://arxiv.org/html/2312.07104v2
- **evidence:** SGLang (arXiv 2312.07104v2) is an embedded Python DSL whose primitives gen/select/extend/fork/join express reasoning, parallelism, and control flow. It 'manages the prompt state as a stream and submits primitive operations ... for asynchronous execution,' programs 'can be compiled as computational graphs and executed with a graph executor,' and 'Fetching generation results will block until they are ready, ensuring correct synchronization.' Constrained decoding uses a 'compressed finite-state machine' that compresses adjacent singular-transition edges so 'multiple tokens ... can be decoded in one forward pass,' yielding 1.6x JSON throughput. This async stream / computational graph with blocking-fetch dependencies is the closest existing analogue to an explicit-dataflow-edge execution graph, but SGLang's graph is a runtime execution/scheduling graph, not a human-readable typed-atom SSA reasoning IR.

### 3. DSPy positions itself at a higher abstraction layer than constrained-decoding libraries: it frames Guidance/LMQL/Outlines as low-level structured control of a single LM call (JSON-schema enforcement, regex-constrained sampling) and instead automatically optimizes the prompts in programs to align them with task needs, which may include valid structured output.

- **confidence:** high · **vote:** 3-0 (merged from claims 6,7)
- **sources:** https://dspy.ai/faqs/
- **evidence:** DSPy FAQ: these libraries are 'focused on low-level, structured control of a single LM call,' e.g. 'enforce JSON output schema or constrain sampling to a particular regular expression,' whereas 'DSPy automatically optimizes the prompts in your programs to align them with various task needs, which may also include producing valid structured outputs.' Establishes that the prior-art landscape already distinguishes a token-level constraint layer from a higher program-optimization layer; relevant for situating where an SSA reasoning IR sits.

### 4. llguidance implements constrained decoding by enforcing an arbitrary context-free grammar (JSON schemas, regex, Lark CFGs with embedded schemas/regex) on LLM output; its mechanism is per-step token-mask computation that constrains generation toward a valid grammar prefix, and it does not represent reasoning or dataflow.

- **confidence:** high · **vote:** 3-0 (merged from claims 8,9)
- **sources:** https://github.com/guidance-ai/llguidance, https://deepwiki.com/guidance-ai/llguidance, https://arxiv.org/pdf/2502.05111
- **evidence:** llguidance README: 'implements constrained decoding ... for Large Language Models,' 'can enforce arbitrary context-free grammar on the output,' supporting JSON schemas, regular expressions, and Lark-format CFGs. Given a grammar/tokenizer/prefix it 'computes a token mask ... that, when added to the current token prefix, can lead to a valid string in the language defined by the grammar.' Corroborated by arXiv 2502.05111. Confirms structured-output engines constrain generation, not reasoning/dataflow, delimiting what an SSA reasoning notation would NOT be duplicating.

### 5. Prompt Decorators is prior art for a compact, declarative, composable human-to-LLM control notation using prefix control tokens (+++Reasoning, +++Tone(style=formal)) that separate task semantics from behavioral directives and stack modularly; but because behavior depends on LLM pattern-matching rather than deterministic parsing, it is non-deterministic and drifts across sessions/contexts -- a named pitfall for symbol-operator notations.

- **confidence:** high · **vote:** 3-0 (merged from claims 10,11,12)
- **sources:** https://arxiv.org/html/2510.19850v1, https://github.com/smkalami/prompt-decorators
- **evidence:** Prompt Decorators (arXiv 2510.19850v1) use the compact syntax '+++Name(optional_parameters),' 'decoupling task intent from execution behavior,' and 'Allow multiple decorators to be stacked modularly.' Section 6.1 documents the pitfall directly: 'Because decorators rely on pattern recognition rather than deterministic parsing, their behavior can vary across sessions or contexts,' causing 'interpretive drift [that] limits semantic precision and reproducibility.' This is the strongest evidence that any symbol-operator reasoning notation (including math-symbol operators in an SSA scheme) risks LLM hallucination/drift unless backed by deterministic parsing/middleware -- the paper proposes symbolic parsing as the remedy.

### 6. The ReAct scratchpad mechanism (interleaving reasoning traces with action execution) is largely illusory: a critique found performance is minimally influenced by the interleaving or by reasoning-trace content, and is instead driven by similarity between in-prompt example tasks and the query, contradicting the original ReAct paper's claimed mechanism.

- **confidence:** high · **vote:** 3-0 (merged from claims 13,14)
- **sources:** https://arxiv.org/pdf/2405.13966
- **evidence:** 'On the Brittle Foundations of ReAct Prompting' (arXiv 2405.13966, Verma/Bhambri/Kambhampati): 'the performance is minimally influenced by the "interleaving reasoning trace with action execution"' and 'the performance of LLMs is driven by the similarity between input example tasks and queries.' Caveats: single 2024 study, scoped to few-shot ReAct on sequential-decision benchmarks with GPT-family models; the stronger claim that all LLM reasoning is exemplar-retrieval artifact was REFUTED (0-3) in verification. Relevant because it warns that a reasoning-trace notation may not causally drive performance the way its designers assume.

### 7. TOON is a dense JSON-replacement serialization combining YAML-style indentation for nested objects with CSV-style tabular layout for uniform arrays, designed to pass structured data to LLMs with significantly reduced tokens while preserving solid comprehension accuracy.

- **confidence:** high · **vote:** 3-0 (merged from claims 15,17)
- **sources:** https://github.com/toon-format/toon, https://arxiv.org/abs/2603.03306
- **evidence:** TOON 'combines YAML's indentation-based structure for nested objects with a CSV-style tabular layout for uniform arrays' (github.com/toon-format/toon) and 'aims to replace JSON as a serialization format for passing structured data to LLMs with significantly reduced token usage' while 'showing solid accuracy in LLM comprehension' (arXiv 2603.03306). Direct prior art for a token-compaction layer over structured data.

### 8. TOON provides direct empirical evidence of token savings from dense notation: it reduces generated tokens by 26.4% vs JSON, 49.4% vs XML, and 15.3% vs YAML aggregated across LLMs.

- **confidence:** high · **vote:** 3-0 (claim 21)
- **sources:** https://arxiv.org/pdf/2601.12014
- **evidence:** 'Are LLMs Ready for TOON?' (arXiv 2601.12014, Masciari et al., 2026): 'TOON systematically produces more compact outputs, as reflected by a substantially lower number of generated tokens (NT) with respect to JSON, XML, and YAML (26.4%, -49.4%, and -15.3%, respectively),' aggregated across models, statistically significant (Wilcoxon p<0.05). Quantitative support that dense notations cut tokens in generation, not just input.

### 9. TOON's token savings are structure-dependent and offset by a 'prompt tax': instructional/in-context overhead erases savings in short contexts (non-linear scaling, net savings only for larger/uniform structures), and for deeply nested or non-uniform data compact JSON can use fewer tokens than TOON (e.g. 655 vs 568 tokens on a deeply nested config dataset).

- **confidence:** high · **vote:** 3-0 (merged from claims 16,18)
- **sources:** https://arxiv.org/abs/2603.03306, https://github.com/toon-format/toon
- **evidence:** arXiv 2603.03306: TOON's advantage 'is often reduced by the "prompt tax" of instructional overhead in shorter contexts' and 'true efficiency potential likely follows a non-linear curve, shining only beyond a specific point.' The toon-format repo's own benchmark: for 'deeply nested or non-uniform structures (tabular eligibility approx 0%): JSON-compact often uses fewer tokens' (json-compact 568 vs toon 655 tokens). Key caveat for an SSA notation: a dense reasoning IR may not save tokens on non-tabular/irregular graph structures and pays fixed instructional overhead the LLM must be taught.

### 10. TOON's token savings come at a structural-correctness cost when the format is enforced only through prompt-level instructions (not natively supported): generation correctness drops 38.8% vs JSON, 30.9% vs XML, 42.2% vs YAML, a documented pitfall of dense notations the model must pattern-match rather than natively emit.

- **confidence:** high · **vote:** 3-0 (claim 22)
- **sources:** https://arxiv.org/pdf/2601.12014
- **evidence:** arXiv 2601.12014: TOON shows 'reduced robustness in strictly adhering to formal structural constraints (-38.8%, -30.9%, and -42.2% with respect to JSON, XML, and YAML, respectively), which can be attributed to the fact that TOON is not natively supported by the evaluated LLMs and must be enforced exclusively through prompt-level instructions.' Note paper text reports -38.9% vs JSON (0.1pt typo) and that the gap narrows/vanishes on larger models (e.g. Llama 3.3 70B). This is the core pitfall for AI-lish/ARP: a novel symbol-dense SSA notation enforced only via prompt will likely incur a structural-correctness penalty absent native support or deterministic parsing/validation.

### 11. LLMLingua provides strong evidence that heavy token compression need not destroy task accuracy: up to 20x prompt compression (e.g. 2,366 tokens to 117) while preserving reasoning/summarization/dialogue capabilities, with only ~1.5 points lost on reasoning benchmarks (GSM8K/BBH) at 20x.

- **confidence:** high · **vote:** 3-0 (merged from claims 19,20)
- **sources:** https://www.microsoft.com/en-us/research/blog/llmlingua-innovating-llm-efficiency-with-prompt-compression/, https://arxiv.org/abs/2310.05736
- **evidence:** Microsoft Research / EMNLP 2023 (arXiv 2310.05736): LLMLingua can 'compress a complex prompt of 2,366 tokens down to 117 tokens, achieving a 20x compression while maintaining almost unchanged performance,' and 'can achieve up to a 20x compression rate while only experiencing a 1.5-point performance loss' on GSM8K/BBH. Caveat: 20x is best-case for reasoning/ICL; conversation/summarization achieve only 3x-9x. Strongest prior-art evidence that a token-compaction layer is viable, validating the compaction component of the AI-lish/ARP design.

