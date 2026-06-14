# RFC 0009 — AIL-0 (Agentic Intermediate Language, core register language)

- **Status:** Draft / exploration
- **Created:** 2026-06-14
- **Track:** Protocol
- **Relationship note:** AIL-0 is the formal grammar for the text conventions
  that **ARP** ([issue #202](https://github.com/peterlodri-sec/vaked-base/issues/202))
  carries; it is a register *notation*, not an HCP Votive Frame schema. It does
  not introduce a wire format and does not change the HCP roster
  ([RFCs 0001–0007](./0001-hcp.md)). See §6.

## Abstract

This RFC defines **AIL-0** (Agentic Intermediate Language, v0): a small,
ASCII, EBNF-governed, **register-tagged** notation for LLM-agent
communication — planning, tool-intent, causality, risk, artifacts, and state.
AIL-0 is a *register language*, not a full programming language. Its single
design rule is **compress what natural language wastes; keep EXACT what
machines need**: reasoning scaffold, causality chains, sequencing, confidence,
and register transitions are compressed; file paths, code symbols, commands,
API names, error strings, literals, and commit subjects are preserved
byte-for-byte.

The distinctive mechanism is **gate-as-grammar on output registers**: the
artifact-discipline check is a production in the grammar, not a prose
convention. `[R:artifact]` and `[R:commit]` bodies reduce to an English-only
character class that *excludes the CJK Unicode blocks*, so a CJK glyph in an
artifact body is a parse rejection. This directly targets the
[PR #203](https://github.com/peterlodri-sec/vaked-base/pull/203) finding that
Chinese reasoning leaked into artifact outputs on thinking models. Reasoning
registers (`[R:think]`, `[R:plan]`) carry free text and are deliberately
*not* constrained.

The normative artifacts are the grammar at
[`protocol/ail/ail-v0.ebnf`](../ail/ail-v0.ebnf) and the morpheme table at
[`docs/language/0025-ail-morphemes.md`](../../docs/language/0025-ail-morphemes.md).
This RFC formalizes them and records the acceptance criteria, design
decisions, and an explicit honest caveat: **AIL-0's token savings are a
hypothesis, not a claim** (§5).

## Terminology

| Term | Definition |
|------|------------|
| AIL | Agentic Intermediate Language — the repo-native name for this register notation. |
| AIL-0 | The experimental v0 register grammar this RFC formalizes. |
| Register | A tagged channel selecting a frame shape: `R:think`, `R:plan`, `R:tool`, `R:risk`, `R:artifact`, `R:commit`, `R:review`, `R:bench`. |
| Frame | One line: a register tag followed by a body, terminated by end-of-line. |
| Reasoning register | `R:think` / `R:plan` — free-text body, unconstrained (§3). |
| Output register | `R:artifact` / `R:commit` — gated, English-only body, no CJK (§4). |
| Structured register | `R:tool` / `R:risk` / `R:review` / `R:bench` — a `;`-separated statement list (§3). |
| Gate-as-grammar | The artifact / English / no-CJK discipline encoded as productions, so violations are parse failures, not style notes (§4). |
| Keep-exact | The property that path/symbol/quoted/number literals round-trip byte-for-byte through `[R:tool]` (§3). |
| Morpheme | A reserved AIL-0 token (register, operator, gate name, gate state) catalogued in `0025-ail-morphemes.md`. |
| ARP | Agent Register Protocol — the model-agnostic primitive layer AIL-0 docks under ([issue #202](https://github.com/peterlodri-sec/vaked-base/issues/202)). |
| CUC | The human-facing compression skill ([PR #203](https://github.com/peterlodri-sec/vaked-base/pull/203)); a presentation style, not this grammar. |
| HCP | The project wire protocol ([RFCs 0001–0007](./0001-hcp.md)); orthogonal to AIL-0. |

## 1. Scope and non-goals

AIL-0 defines a *notation*: a line-oriented, UTF-8, ASCII-operator grammar for
agent-to-agent and agent-to-log text. It is the smallest layer that lets the
text conventions ARP carries be parsed, validated, and benchmarked.

**In scope (this RFC):** the register set, the frame shapes, the ASCII operator
set, the structured-statement grammar, and the output-discipline gates,
referencing the normative EBNF and morpheme table.

**Non-goals.** AIL-0 is **not** a wire protocol — it has no framing header,
no transport, no Votive Frame class. It is **not** a full programming language
— no control flow, no types, no evaluation. It does **not** alter HCP or its
roster. Binary encoding, transport, and authority remain HCP's concern
([RFCs 0001–0007](./0001-hcp.md)); AIL-0 text may *appear inside* an HCP
payload but is not coupled to it.

## 2. Registers

AIL-0 has eight registers, dispatched by tag. The frame shape is chosen by the
register, with three body arms:

| Register | Arm | Body | Discipline |
|----------|-----|------|------------|
| `R:think` | reasoning | free text | none — unconstrained |
| `R:plan` | reasoning | free text | none — unconstrained |
| `R:tool` | structured | `;`-separated statements | keep-exact path/symbol literals |
| `R:risk` | structured | `;`-separated statements | — |
| `R:review` | structured | `;`-separated statements | — |
| `R:bench` | structured | `;`-separated statements | — |
| `R:artifact` | output | English text | **no CJK** (gate-as-grammar) |
| `R:commit` | output | Conventional-Commit subject | English-only (no CJK) |

The split is the load-bearing design choice (§4): reasoning is free, output is
gated. Every register is reached by exactly one frame arm in the EBNF, so the
dispatch is deterministic.

## 3. Frames and statements

A `message` is one or more `frame`s. AIL-0 is **line-oriented**: a newline
terminates a frame, so each frame occupies exactly one line and a `[R:think]`
body cannot swallow the following frame. Within a structured frame, `;`
separates statements.

A structured statement is one of: a `gate`, an `action`, a `relation`, or an
`atom`. The ASCII-canonical operator set (normative) is:

```
->  =>  bc  so  par  merge  conflict  !=  ~=  <=  >=
```

`->` (sequence/yields), `=>` (implies), `bc` (because), `so` (therefore),
`par` (parallel-with), `merge` (join), `conflict`, and the comparisons
`!= ~= <= >=`. Unicode glyph forms (`→ ⇒ ∵ ∴` and friends) are **optional,
non-normative sugar only** and are deliberately absent from the `op`
production (§7.b).

**Keep-exact.** `path` and `symbol` are first-class productions in the EBNF
(not folded into `ident`), so file paths (`./parse.py`, `hosts/vakedos/deploy.sh`)
and code symbols (`foo.bar.baz`, `Module::func`, `Type#method`, `parse/2`)
round-trip byte-for-byte through `[R:tool]`. `quoted` carries opaque payloads
(error strings, fragments needing spaces) verbatim. This is the keep-exact half
of the design rule, enforced structurally.

The full grammar — `message`, `frame`, `stmt`, `relation`, `action`, `gate`,
`atom`, `path`, `symbol`, the character-level productions, and the gated body
classes — is normative in [`protocol/ail/ail-v0.ebnf`](../ail/ail-v0.ebnf).
The sketch above is illustrative; on any divergence the `.ebnf` wins.

## 4. Gate-as-grammar (output discipline)

The artifact gate is a **production**, not a prose convention. The
`[R:artifact]` body reduces to `english_text`, which reduces to `english_char`
— a character class that **excludes** the CJK Unicode blocks: CJK Unified
Ideographs and Extension A, CJK Compatibility Ideographs, Hiragana, Katakana,
Hangul Syllables, and CJK Symbols & Punctuation. A CJK glyph in an artifact
body is therefore a **grammar rejection**, not a lint warning. `[R:commit]`
applies the same English-only class to a Conventional-Commit subject.

Two `gate(name:state)` productions also let a frame *record* a discipline
outcome inline: `gate_name ∈ {artifact, english, no_cjk, ci, bench, parse}`
and `gate_state ∈ {pass, fail, warn, skip}`. Both sets are closed.

**Why gate output but not reasoning.** Forcing tight structure on reasoning
collapses model accuracy — rigid JSON drove Claude-3-Haiku GSM8K from 86.51%
to 23.44%, the mechanism being field-order forcing the answer before the
reasoning; NL-then-format recovers it. So `[R:think]` / `[R:plan]` are
free-text and only `[R:tool]` / `[R:artifact]` / `[R:commit]` are tightly
structured. Gating the *output* register catches CJK leakage at exactly the
boundary where it matters (the artifact a human or downstream tool consumes)
without taxing the reasoning that produces it.

## 5. Token savings are a hypothesis, not a claim

AIL-0's distinctive mechanism — hand-authored, register-tagged compression —
has **no direct token-savings evidence**, and this RFC states that plainly.
The register tags are pure token **tax**: `[R:think]`, `gate(...)`, and the
operator morphemes all cost tokens that prose does not.

The savings reported in the compression literature come from mechanisms AIL-0
does *not* primarily use: (a) algorithmic low-information removal (LLMLingua,
up to ~20x token reduction at ~1.5pt accuracy loss) and (b) replacing verbose
natural language with a genuinely more compact structured form (CodeAgents
reports 55–87% input-token cuts — single-source and partly definitional).
AIL-0 must therefore earn any net savings from **information density**, and
that net effect — savings *after* the tag tax — must be **measured on TOKENS**,
per tokenizer, on the bench.

Two methodological guards follow: **per-character savings do not imply
per-token savings**, and **fewer turns/actions is not token evidence**. The
bench (§5.2) measures tokens and characters as *separate* quantities and never
substitutes one for the other. Issue #202's hypothesized 49–62% reduction is a
target to confirm or refute on tokens, not a starting assumption.

### 5.1 Acceptance criteria

AIL-0 v0 is accepted when:

1. The EBNF at [`protocol/ail/ail-v0.ebnf`](../ail/ail-v0.ebnf) parses **all**
   sample frames in [`protocol/ail/examples/`](../ail/examples/) (`plan.ail`,
   `risk.ail`, `artifact.ail`).
2. The morpheme table [`docs/language/0025-ail-morphemes.md`](../../docs/language/0025-ail-morphemes.md)
   has **≤ 80 entries**, and every morpheme it lists appears in the EBNF and
   vice-versa (round-trip closure).
3. A `[R:artifact]` body **requires English output**: any CJK glyph is a parse
   rejection (the gate-as-grammar of §4), verified against the `english_char`
   class.
4. The bench (§5.2) reports its metric set across all four modes on a real
   tokenizer matrix.

### 5.2 Bench (token-honest)

The bench design is specified in
[`docs/superpowers/specs/2026-06-14-ail-bench-design.md`](../../docs/superpowers/specs/2026-06-14-ail-bench-design.md)
(design only — it runs on `dev-cx53` / GitHub Actions, never on the developer
machine). It compares four modes:

```
normal  ·  cuc-wenyan-ultra  ·  ailish-pidgin  ·  ailish-strict
```

The gate reports, per mode and per tokenizer, the following metrics — token and
character quantities kept **separate** throughout:

1. **net token savings** — savings *after* the register-tag tax (the headline
   honesty metric);
2. **character reduction** — kept distinct from token savings, never used as a
   proxy for it;
3. **parse success** — fraction of emitted frames the EBNF accepts;
4. **artifact CJK leakage** — CJK glyphs reaching an `[R:artifact]` / `[R:commit]`
   body (target: zero);
5. **literal preservation** — paths/symbols/quoted literals round-tripping
   byte-for-byte through `[R:tool]`;
6. **register compliance** — frames using the correct register for their content;
7. **repair cost** — tokens/turns to fix a frame the parser rejected.

## 6. Relationship to ARP, CUC, and HCP

AIL-0 sits in a four-name stack; keeping the boundaries crisp is part of the
spec:

| Name | Role | Where |
|------|------|-------|
| **AIL-0** | the **formal grammar** for the text conventions ARP carries | this RFC + `protocol/ail/` |
| **ARP** | Agent Register Protocol — model-agnostic primitive layer | [issue #202](https://github.com/peterlodri-sec/vaked-base/issues/202) (open) |
| **CUC** | human-facing **compression style** (the `caveman` rename) | [PR #203](https://github.com/peterlodri-sec/vaked-base/pull/203) (open) |
| **HCP** | the project **wire protocol** | [RFCs 0001–0007](./0001-hcp.md) |

- **AIL-0 ↔ ARP.** AIL-0 **docks under** [issue #202](https://github.com/peterlodri-sec/vaked-base/issues/202):
  it is the grammar layer; ARP is the model-agnostic primitive/adapter layer
  that carries AIL-0 frames across providers. AIL-0 does *not* introduce a
  second control plane — it formalizes the notation ARP already implies.
- **AIL-0 ↔ CUC.** [PR #203](https://github.com/peterlodri-sec/vaked-base/pull/203)
  (`caveman → cuc` rename + five-model bench) is the *human-facing* compression
  style. CUC is how a human reads compressed text; AIL-0 is the machine grammar.
  The `cuc-wenyan-ultra` bench mode (§5.2) lets the two be compared on equal
  footing. This RFC does **not** create `.claude/skills/cuc/` — that is #203's
  deliverable.
- **AIL-0 ↔ HCP.** HCP ([RFCs 0001–0007](./0001-hcp.md)) is the wire protocol:
  framing, transport, authority. AIL-0 is orthogonal notation that may travel
  *inside* an HCP payload but does not define or modify any HCP frame. AIL-0
  adds no terms to the HCP roster.

## 7. Design decisions (with rationale)

### 7.a Placement under `protocol/ail/`, not `vaked/grammar/`

The grammar lives at [`protocol/ail/ail-v0.ebnf`](../ail/ail-v0.ebnf), under
`protocol/`, **not** under `vaked/grammar/`.

*Rationale.* `vaked/grammar/` is the home of the **Vaked language** — the
capability-graph declaration language compiled by vakedc/vakedz. AIL-0 is a
different artifact with a different audience: it is ARP's register protocol for
agent communication, not a Vaked construct, and it compiles to nothing. Placing
it under `protocol/` keeps it beside the other inter-agent protocol work
(HCP RFCs) and prevents conflating a notation-for-agents with the
infrastructure-declaration language. The two grammars share a line-oriented
discipline by convention but are independent.

### 7.b ASCII-canonical operators

The normative operator set is ASCII (`-> => bc so par merge conflict != ~= <= >=`);
Unicode glyph forms are optional, non-normative sugar excluded from the `op`
production.

*Rationale.* Rare-Unicode and CJK glyphs can **increase** token count under
byte-fallback tokenization: a glyph outside a tokenizer's learned vocabulary
decomposes into multiple byte-level tokens, so a "compact" arrow (`→`) can cost
*more* tokens than the two ASCII characters `->`. Since AIL-0's entire premise
is token economy (§5), admitting token-inflating glyphs into the normative
grammar would be self-defeating. A conformant emitter SHOULD emit the ASCII
forms; Unicode is tolerated only as readability sugar a tokenizer-aware emitter
avoids.

## 8. Security considerations

AIL-0 defines no transport, authority, or executable behavior, so it carries no
network or capability surface of its own. Its security-relevant properties are
**output-discipline** properties, enforced structurally:

- **CJK rejection at parse time.** The `english_char` class (§4) makes a CJK
  glyph in an `[R:artifact]` / `[R:commit]` body a *parse failure*, not a
  warning that can be ignored downstream. The discipline cannot be silently
  bypassed by a producer that "forgot" to lint.
- **Keep-exact integrity.** `path`, `symbol`, and `quoted` are first-class
  productions (§3), so command/path/error-string literals cannot be silently
  mangled by the compression layer — the class of bug where a compressor
  paraphrases a literal it should have preserved is structurally excluded for
  `[R:tool]` bodies.
- **Closed gate vocabulary.** `gate_name` and `gate_state` are closed sets
  (§4), so a recorded discipline outcome is typed, not stringly-typed, and
  cannot smuggle an unrecognized "pass-like" state.

AIL-0 makes no tamper-evidence or authority claims; any frame's *trustworthiness*
is the concern of whatever HCP/`eventd` layer transports or records it
([RFCs 0001–0007](./0001-hcp.md)), not of the notation.

## 9. Open questions

Lifted from the reconciled design spec — these are the questions the bench
(§5.2) must settle:

- **Net token savings after the tax.** Does hand-authored register-tagged
  compression net-save **tokens** once the register-tag tax is paid, per
  tokenizer? There is currently no evidence either way (§5).
- **Artifact gate on thinking models.** Does the gate-as-grammar hold on
  thinking models without an accuracy hit? CJK leakage was measured on QwQ, not
  DeepSeek-R1; generality is unknown. (QwQ ≠ DeepSeek-R1 — do not conflate.)
- **Constrained-decode coverage cliff.** Does a small EBNF avoid the
  grammar-constrained-decoding coverage collapse (empirically 3–41% on hard
  grammars) in practice? AIL-0 is deliberately small precisely to test this.
- **README/vocabulary docking.** Whether the AIL-0 register terms should be
  carried into `docs/protocol/README.md` once AIL-0 stabilizes (deferred; AIL-0
  is a separate register language, not an HCP roster change).
