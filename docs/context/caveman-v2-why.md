# Why Caveman Ultra V2? The Case for an AI-Native Language in the Vaked Ecosystem

*A reasoning story — not a spec, not a plan. Just the honest thinking.*

---

## The Problem We Didn't Know We Had

When you run a Claude Code session and watch it work through a complex task, you're watching something genuinely strange: an intelligence that has to describe its own reasoning in a language designed for humans. Every "I'll start by reading the file to understand the structure" is a sentence written for you to follow, not for the model to think. The model already knows it's going to read the file. The explanation is scaffolding. It's politeness. It's convention.

And it costs tokens.

We didn't really reckon with this until we ran the numbers. In a typical reasoning response to a technical question, roughly 35–55% of the output tokens are what you might call structural ceremony — the introductory sentence, the transitional phrases, the hedging qualifiers, the summary at the end that repeats what was just said. This isn't the model being dishonest or lazy. It's the model being a good English writer. English prose has a shape, and large language models have learned that shape from billions of documents. The problem is that shape is expensive when you're running hundreds of tool calls per session.

## The Accidental Discovery

The caveman skill started as a simple quality-of-life improvement. Drop the filler. Be direct. It worked, but incompletely — "full" caveman mode still operated within the rhythms of English, just tighter. The real insight came when someone asked what would happen if we switched the compression substrate entirely.

Classical Chinese — 文言文 — is not a language designed for AI communication. It's a language designed by scholars for permanence, precision, and extreme density. A text that would take a page in vernacular Chinese might take a paragraph in classical Chinese. Characters double as verbs and nouns contextually. Subjects are omitted when obvious. Causality is implied by juxtaposition: you don't write "because A, therefore B" — you write "A, B" and the relationship is understood. It's a writing system that assumes a reader who fills in the gaps.

LLMs are excellent at filling in gaps.

We ran the experiment. We gave the same technical questions to the same model, once with a normal English system prompt and once with a wenyan-ultra instruction. The responses in wenyan-ultra were correct, complete, and sometimes more precise than the English originals — they just didn't have any room for ceremony.

## What the Numbers Actually Say

Across eight prompts spanning reasoning, code analysis, and artifact production:

- **GPT-4o-mini**: 61.8% output token savings, 80.6% character reduction. Artifact gate 100% clean.
- **DeepSeek R1**: 50.8% output token savings, 73.8% character reduction. Artifact gate 100% clean.

The artifact gate result is the one that surprised us most. We worried that a model told to respond in compressed classical Chinese might start writing commit messages in Chinese, or generate file contents with CJK characters embedded. It didn't. Zero leakage across six artifact tests across two models. The normalization to English for gated output — files, commits, PRs — worked cleanly without any post-processing, just from the rule in the skill instructions.

The reasoning tasks showed the biggest savings: 59–87% depending on the model and question. The more the normal response would have been padded with explanation, the more compression was available. The code analysis tasks were similar. Artifact tasks compressed less (0–54%) because they're already constrained to English by the gate — you can't compress English into Chinese if the output must be English.

## Why It Works: Three Mechanisms

The compression comes from three things that compound.

The first is **scaffold elimination**. English-trained models produce answers with a shape: introduction, body, conclusion. The introduction and conclusion often carry no information that isn't already in the body. A wenyan-ultra model doesn't produce these. It starts at the information.

The second is **grammatical filler removal**. Classical Chinese has no articles (a/an/the), minimal auxiliary verbs, reduced prepositions, and omits pronouns when clear from context. In English, these words account for roughly 30–40% of tokens in a typical paragraph. They're obligatory in English grammar. They're absent in Chinese grammar. When you switch the writing system, they evaporate.

The third is **semantic density**. A single Chinese character often encodes what English needs a word (or phrase) for. 連接池 is three characters for "connection pool." 故 is one character for "therefore." This isn't just compression — it's a different relationship between symbol and meaning.

The gap between token savings (62%) and character savings (81%) tells you something interesting: the CL100K tokenizer, which was trained on multilingual data, already includes common Chinese characters as single tokens. They're not penalized at the tokenizer level. The density advantage survives the tokenizer.

## The Embarrassing Limitation

Here's the thing we have to be honest about: we're using a 3,000-year-old human writing system as a compression hack for AI communication. It works — the data is clear — but it's accidental. Classical Chinese was optimized for human scholars preserving knowledge across dynasties, not for AI agents minimizing context usage in 2026. The vocabulary has gaps. There are no classical Chinese characters for "eBPF" or "flake.nix" or "capability graph." Those terms pass through unchanged, which is correct, but it means the compression is uneven. Highly technical content compresses less than conceptual content.

More fundamentally: classical Chinese is a human language. Its grammar, its characters, its particles — all of it was designed around human cognition, human memory, human reading speed. AI cognition is different. An AI doesn't need vowel-like flow. It doesn't benefit from phonological regularity. It processes tokens, and its attention mechanism has specific patterns that have nothing to do with how a Song Dynasty scholar read a memorial to the Emperor.

We borrowed the right idea from the wrong substrate.

## What V2 Could Be

Caveman Ultra V2 isn't really an upgrade to the compression style. It's a question about whether we should design the compression substrate from scratch.

Imagine a small language — call it AI-lish for now — designed with the following constraints:

- **Token-boundary-aware morphemes.** The vocabulary is defined by what modern tokenizers encode efficiently, not by what sounds good or has historical precedent. Each token encodes exactly one atomic concept.
- **Unambiguous grammar.** A context-free grammar that machine-parses without ambiguity. No garden-path sentences. No pragmatic inference required for basic structure.
- **Built-in context switching.** The language has a native concept of "artifact mode" — a declared output register that the grammar enforces, eliminating the need for an external Artifact Gate rule.
- **Causal and temporal operators as first-class citizens.** `→`, `∵`, `∴`, `⊕`, `||`, `»` aren't prose shorthands — they're grammar.
- **Evolvable.** New vocabulary is added via a formal Language Feature Change (LFC) process, versioned and backward-compatible.

This would compress more than wenyan-ultra on technical content. It would compress more uniformly. And it would be teachable to any model through system-prompt bootstrapping without requiring the model to have been trained on classical Chinese.

## Why Vaked Is the Right Home for This

The coincidence is almost too convenient. Vaked is already a grammar-first, formally-specified, domain-specific language with an EBNF grammar file, a type system document, a lowering spec, and a set of RFCs governing protocol evolution. The HCP protocol already has LFCs in the form of `protocol/rfcs/`. The caveman skill already lives in `.claude/skills/`. The infrastructure for defining, versioning, and evolving a language is sitting right here.

An AI-lish V1 in this repo would look like this: a new EBNF grammar at vaked/grammar/ailish-v0.ebnf (not yet created), a core morpheme table at docs/language/0019-ailish-morphemes.md (not yet created), an LFC-0001 proposing the initial vocabulary, and a modified caveman skill that references the grammar instead of describing a style. The compression wouldn't be a convention — it would be a language.

The Artifact Gate would be a grammar production: `artifact-output ::= normal-english-text`. The internal monologue hook would emit AI-lish. The bench would measure compression against the grammar spec.

## The Open Question

The bootstrap problem is real. You can't fine-tune all the models you work with. The wenyan-ultra approach works precisely because the models were already trained on classical Chinese — the behavior is latent, and a system prompt unlocks it. A purpose-built AI-lish would require teaching, not unlocking.

The answer is probably staged. V2 starts as a heavily-annotated pidgin: borrowing from existing high-density languages (Chinese, math notation, logic symbols) but with formal grammar and LFCs to evolve it. Over time, as the grammar stabilizes and models see it in training data (including this repo), it becomes a real language rather than a style.

That's how English got its technical vocabulary too. It borrowed.

---

*Caveman Ultra V1 proved the compression works and the gate holds. V2 is the question of whether we can do it on purpose.*
