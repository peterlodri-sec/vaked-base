# AIL-0 — SDD fan-out plan (drive #211 to end-to-end)

Instantiates the **subagent-driven-development** workflow
(`.claude/skills/subagent-driven-development`, formalized in `vaked/examples/sdd.vaked`)
to take #211 (AIL-0 register language + naive ARP e2e) from its current **spec layer**
to a **tested, shippable** state. **This is the plan + per-wave subagent instructions —
it is not executed here** (no builds; see CLAUDE.md NEVER-BUILD).

Refs: #211 (AIL-0 spec), #202 (ARP text conventions), #203, RFC `0009-*`,
`docs/language/0025-*`, `protocol/ail/`. Driver skill for the parser waves:
`ailish-v1-drive`.

## Context

#211 ships an **honest** spec: deep-research (`wru7qq2ax`, 8 strands, adversarially
verified) found register-tagged hand-authored compression has **no direct token-savings
evidence and the tags are a net token tax**; the proven wins are algorithmic
(LLMLingua ~20x) and genuinely-compact structured forms. Two evidence-forced
corrections are baked in: **ASCII-canonical operators** (Unicode is optional sugar) and
**gate artifacts, not reasoning** (rigid JSON collapses reasoning accuracy). So AIL-0 e2e
must *measure* the idea (a bench), not assume it.

## Wave DAG

```
W0 frame ─▶ W1 research ─▶ W2 spec ─▶ W3 implement ─▶ W4 test ─▶ W5 integrate
                                         (fan-out)      (fan-out)
```

### W0 · Frame  *(orchestrator)*
Acceptance: this DAG, with each component's gate. Deferred implementables from #211:
EBNF (`protocol/ail/ail-0.ebnf`), morpheme table (`docs/language/0025-*`), RFC
(`protocol/rfcs/0009-*`), and the bench (design present; run deferred).

### W1 · Research  *(researchers, parallel — mostly DONE)*
- Reuse run `wru7qq2ax` (single-agent) + `wnlq8ckib` (multi-agent/adapter) dossiers.
- **Adjacent gap to fill** (1 `deep-research` each, only if not already covered): (a)
  `nom` parser-combinator patterns for a register-tagged ASCII IL; (b) the LLMLingua /
  CodeAgents baselines the bench must compare against.
- Gate: every bench hypothesis has a named baseline + metric; unproven claims flagged.

### W2 · Spec  *(spec-author + coherence-critic)*
- Finalize `protocol/ail/ail-0.ebnf` (ASCII-canonical operators `-> => bc so ...`;
  Unicode sugar marked optional), `docs/language/0025-*` morpheme table, and
  `protocol/rfcs/0009-*` (`Status: Draft`, `Track: protocol`). Cite #202/ARP + RFC 0004
  as ground truth; keep `[R:think]/[R:plan]` reasoning **free-text** (gate artifacts only).
- coherence-critic (rfc-incoherence-hunter) vs #202, 0004, the 0013 MLIR set.
- **Gate:** `python3 tools/dockeeper/dockeeper.py` 0 errors · `python3 tests/spec/test_doc_links.py` PASS · critic 0 confirmed-critical/major.

### W3 · Implement  *(coders, parallel — own worktrees, builds on dev-cx53/GHA only)*
| component | path | gate |
|-----------|------|------|
| AIL-0 parser + validator (nom) + the `[R:*]`-vs-artifact guardrail | `protocol/ail/` (Rust crate) | `cargo build`/`test`/`clippy` clean |
| ARP ↔ AIL-0 adapter (#202 text conventions ↔ AIL-0 grammar) | adapter crate/module | round-trip parses |
| token-compaction bench harness (multi-model via OpenRouter; ailishfmt) | `tools/ail-bench/` | `--dry-run` builds prompts + cost estimate, $0 |
Use the `ailish-v1-drive` skill for the nom parser + ailishfmt waves.

### W4 · Test/verify  *(test-authors, parallel + integration)*
- Parser: golden + **negative** vectors authored spec-only (independent of the parser impl).
- ARP round-trip: ARP→AIL-0→ARP byte-stable on a corpus.
- Bench: the multi-model run (GHA / dev-cx53) producing the honest token-delta table —
  **report the result whatever it shows** (per the #211 honesty stance).
- **Gate:** `ci-gate` green at tier; the bench run completes and the table is committed.

### W5 · Integrate  *(broker)*
Stacked, dependency-ordered, ready-for-review PRs: `spec (EBNF/RFC/morpheme)` → `parser`
→ `adapter` → `bench`. Each green on `ci-gate` + `agent-structure-guard`. **No self-merge.**

## Per-wave subagent dispatch (copy-paste briefs)

- **researcher (W1 gap):** `deep-research` — "nom parser-combinator idioms for an ASCII,
  EBNF-governed register-tagged IL; and the LLMLingua + CodeAgents token-compression
  baselines AIL-0's bench must beat. Cited, adversarially verified; flag unproven."
- **spec-author (W2):** "From the AIL-0 dossiers + EBNF, finalize RFC 0009 (Status:
  Draft) + the 0025 morpheme table; ASCII-canonical operators; keep `[R:*]` free-text;
  cite #202/RFC 0004. Run dockeeper + doc_links to green."
- **coder (W3, one per row):** isolated worktree; "implement <component> per
  `protocol/rfcs/0009-*` + `protocol/ail/ail-0.ebnf`; build/test on dev-cx53/GHA; 0
  warnings; no self-merge." Use `ailish-v1-drive` for parser/ailishfmt.
- **test-author (W4):** spec-only (no parser source); "author golden + negative AIL-0
  vectors and the ARP round-trip corpus from RFC 0009 alone."
- **broker (W5):** open the four stacked PRs ready-for-review; drive `ci-gate` green.

## Verification (of this plan, before any execution)
- `python3 tools/dockeeper/dockeeper.py` and `python3 tests/spec/test_doc_links.py`
  pass on this doc (links resolve).
- Each W-gate is a concrete, runnable check (above) — no "looks done" gates.
