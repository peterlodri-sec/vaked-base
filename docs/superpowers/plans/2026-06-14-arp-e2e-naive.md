# ARP (Agent Register Protocol) — naive e2e Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> tracking. This is the UMBRELLA plan; AIL-0 (Wave 1) has its own detail bundle at
> `docs/superpowers/batch/2026-06-14-ail-0/`.

**Goal:** Build and drive end-to-end the cheapest possible model-agnostic **ARP** — a register
layer that lives entirely in the context window (no SDK, no DB, no network), per issue #202 —
and measure that it actually works across ≥2 model families.

**Architecture:** ARP is pure text convention. An ARP-wrapped completion = (1) a system-prompt
preamble teaching the register tags, (2) frames the model emits in those registers, (3) a thin
stdlib validator that parses frames against the **AIL-0** EBNF and enforces the artifact gate.
AIL-0 is the formal grammar for ARP's conventions; the "driver" is a system prompt + a parser +
a token-diff. Model-agnostic = per-family adapter notes, no per-model code paths.

**Tech stack:** Markdown/EBNF (author-only, this machine); Python stdlib validator + bench
(authored here, RUN only on `dev-cx53`/GHA — see NEVER BUILD rule); OpenRouter for multi-model.

**Provenance:** issue #202 (ARP definition) · PR #187 (CUC origin — claimed 49–62% token savings,
artifact gate across 3 families) · PR #203 (caveman→cuc rename + 5-model bench) · this branch
(AIL-0 grammar). Research run `wru7qq2ax` adversarially re-verifies the token-savings claims.

---

## Deviations from the `/agentops:plan` default (honest log)

The skill's heavyweight regime is intentionally NOT used here:
- `bd` / `ao` CLIs and `.agents/` are **absent** in this repo → no bead issues, no `ao` ratchet,
  no findings registry. Tracking is native tasks + this markdown doc (the skill's documented
  fallback).
- Plan lives at `docs/superpowers/plans/` (repo convention), not `.agents/plans/`.
- Protocol design is captured as an **RFC via `hcp-rfc-author`** (Wave 1), per CLAUDE.md, not as a
  hexagon/BDD packet.
- The goal explicitly says "naive / no-frills"; #202 itself defines ARP as "the cheapest possible
  layer." So the ceremony (PR-001..007 planning rules, slice-validation surface, custom_rubric
  judges) is dropped as not-applicable. Lightweight acceptance criteria + waves + a file matrix
  are kept because they are cheap and genuinely useful.

---

## What ARP IS and IS NOT (from issue #202)

IN: register tags (`[R:plan]` `[R:tool]` `[R:artifact]` ...), causal/state operators, the artifact
gate (final outputs English-only, exact literals preserved), all as text in the context window.

OUT (explicitly not ARP): any SDK, database, network transport, fine-tuning, or per-model code.
If a task here reaches for one of those, it is out of scope — stop and report.

---

## File / wave dependency matrix

| Wave | Task | Files (access) | Runs where |
|------|------|----------------|-----------|
| 1 | AIL-0 grammar+spec | see `docs/superpowers/batch/2026-06-14-ail-0/02-plan.md` (write: EBNF, `docs/language/0025-*`, `protocol/rfcs/0009-*`, `docs/context/*bootstrap*`, bench-design spec) | local (author-only) |
| 2 | ARP driver | write: `tools/arp/preamble.md`, `tools/arp/validate.py`, `tools/arp/adapters.md` | author local · RUN dev-cx53/GHA |
| 3 | e2e drive + bench | write: `tools/cuc-bench/*` (per AIL-0 bench design), `tools/arp/e2e_demo.md`, results under `tools/cuc-bench/reports/` | RUN dev-cx53/GHA |

No two same-wave tasks write the same file. Wave 2 reads Wave 1's EBNF. Wave 3 reads Wave 2's
validator + Wave 1's bench design.

---

## Wave 1 — AIL-0 grammar + spec layer (author-only, this branch)

This wave IS the AIL-0 batch. Full task detail lives in
`docs/superpowers/batch/2026-06-14-ail-0/02-plan.md` (authored after research run `wru7qq2ax`
lands). Summary of deliverables:

- [ ] **1a** `docs/context/cuc-v2-ail-bootstrap.md` — bridge note (CUC=style, AIL=grammar, ARP=protocol).
- [ ] **1b** AIL-0 EBNF grammar file (placement decided in AIL-0 spec: `protocol/ail/ail-v0.ebnf`).
- [ ] **1c** `docs/language/0025-ail-morphemes.md` — ≤80-entry morpheme table.
- [ ] **1d** `protocol/rfcs/0009-ail-register-language.md` — RFC stub via `hcp-rfc-author`.
- [ ] **1e** Bench DESIGN spec (metrics, modes, model matrix) — design only, no Python.
- [ ] **1f** GitHub issue for the versioned-language change, docked under #202.

**Acceptance (Wave 1):** every file exists; EBNF parses all sample frames in the spec by
inspection; RFC follows `hcp-rfc-author` structure; numbering is `0025`/`0009` (collision-free);
no `.claude/skills/cuc/` touched.

---

## Wave 2 — naive ARP driver (author local, run dev-cx53/GHA)

The "driver" is deliberately three flat files — no framework.

- [ ] **2a — ARP system-prompt preamble.** Create `tools/arp/preamble.md`: a model-agnostic
  preamble that teaches the registers + artifact gate in <40 lines, ready to prepend to any
  system prompt. Content = the AIL-0 register list + the keep-exact/compress rule + the
  artifact-gate rule.

- [ ] **2b — stdlib validator.** Create `tools/arp/validate.py` (Python stdlib ONLY): reads ARP
  frames on stdin, (i) parses each `[R:*]` frame against the AIL-0 EBNF, (ii) enforces the gate:
  `[R:artifact]`/`[R:commit]` bodies contain no CJK; `[R:tool]` args preserve exact paths/symbols,
  reports `parse_success`, `gate_pass`, and a `repair_needed` flag. Author the file + a few inline
  sample frames as docstring fixtures. **Do NOT run pytest locally** — running is Wave 3 / dev-cx53.

- [ ] **2c — per-family adapter notes.** Create `tools/arp/adapters.md`: one short section per
  family (GPT, Llama, DeepSeek, Qwen, Morph single-turn, Gemma local) capturing the known failure
  mode and the preamble tweak (e.g. Qwen thinking-CJK → reinforce gate; Morph single-turn → fold
  registers into one message). Seed from PR #203 bench findings + research `wru7qq2ax`.

**Acceptance (Wave 2):** validator parses every sample frame and flags a deliberately
gate-violating frame (CJK in `[R:artifact]`); preamble < 40 lines; adapters.md covers ≥5 families.
Validator execution gated to dev-cx53/GHA.

---

## Wave 3 — drive e2e + bench (run dev-cx53/GHA)

- [ ] **3a — bench harness.** Implement `tools/cuc-bench/*` per the Wave-1 bench DESIGN spec
  (corpus, modes `normal|cuc-wenyan-ultra|ailish-pidgin|ailish-strict`, metrics). Stdlib + an
  OpenRouter client.
- [ ] **3b — e2e drive.** `tools/arp/e2e_demo.md` + script: take one real task, wrap it with the
  ARP preamble, drive it through registers on ≥2 model families via OpenRouter, run output through
  the Wave-2 validator, record token counts vs the unwrapped baseline.
- [ ] **3c — measure + report.** Produce `tools/cuc-bench/reports/`: per-model token savings,
  parse-success, artifact-CJK-leakage, repair-cost.

**Acceptance (Wave 3):** e2e runs green on ≥2 families; report shows **TOKEN** (not char) savings
with the unwrapped baseline stated; artifact gate holds (0 CJK leaks in `[R:artifact]`). Treat
#202's 49–62% as a hypothesis to confirm or refute — report the measured number whatever it is.

---

## Execution order & gating

1. Wave 1 (this branch, author-only) — proceeds now (after research lands), via the AIL-0 batch.
2. Wave 2 authoring local; **3-gate verify-confirm** before any dev-cx53/GHA run.
3. Wave 3 entirely on dev-cx53/GHA. Outward action (GitHub issue 1f, any model spend) requires
   explicit user confirmation at the time.

## Next steps

- Let research `wru7qq2ax` land → enrich Wave-1 bench design + Wave-2 adapters.
- Author the AIL-0 batch bundle (Wave 1 detail).
- Then kick off the fan-out batch for Wave 1; Waves 2–3 follow on dev-cx53/GHA.
