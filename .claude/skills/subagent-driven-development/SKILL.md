---
name: subagent-driven-development
description: Use to drive an RFC, feature, or PR end-to-end (research → spec → scaffold → implement → test → integrate) by fanning out single-purpose subagents in dependency-ordered waves. The orchestrator decomposes, dispatches, gates, and merges; it never writes code itself. Trigger on "/subagent-driven-development", "SDD", "fan-out implement", "drive this RFC/PR e2e", "subagent fan-out".
---

# Subagent-Driven Development (SDD)

Drive a unit of work from **intent → evidence → spec → code → green** by fanning out
**single-purpose subagents in dependency-ordered waves**. This mirrors the repo's own
machinery — the `swe_af` mesh (`plan → code → review → publish`), the `deep-research`
adversarial-verify loop, the `rfc-incoherence-hunter` critic, and the
design → plan → implement convention — and composes them into one repeatable loop.

**Invocation:** `/subagent-driven-development <pr-url | issue | rfc-path>`

**Prime directive:** the **orchestrator** (you) decomposes, dispatches, gates, and
merges. It does **not** author code or specs directly — every artifact is produced by a
delegated subagent, so work is parallel, isolated, and independently verifiable. Each
wave has an explicit **acceptance gate** that must pass before the next wave fans out.

## Mesh (roles)

| role | parallel | does | repo analog |
|------|:-------:|------|-------------|
| **orchestrator** | 1 | decompose → wave-DAG; own gates, ledger, merges; never edits code | this session / `ralph` |
| **researcher** | N | one `deep-research` per core/adjacent topic; cited, adversarially verified | `deep-research` skill |
| **spec-author** | 1 | scaffold RFC / EBNF / tables from the dossier | `hcp-rfc-author` / `vaked-language-author` |
| **coherence-critic** | 1 | adversarial check of the spec vs existing RFCs/grammar | `rfc-incoherence-hunter` |
| **coder** | N | one per component, **isolated git worktree**, plan→code | `swe_af` coder / `swe-af-orchestrator` |
| **test-author** | N | tests written **independent** of the impl (separate agent, spec-only) | hcpbin/sandboxd adversarial tests |
| **reviewer** | 1 | per-wave diff review | `pr-review` |
| **broker** | 1 | stacked PRs, ready-for-review, **never auto-merge** | `swe_af` broker |

## Phases (each ends at a gate)

### P0 · Frame & decompose  *(orchestrator)*
Read the target (PR/issue/RFC) and its refs. Produce a **wave-DAG**: dependency-ordered
components, each with explicit acceptance criteria and the CI/doc gates that apply.
Classify research topics into **core** (the thing itself) and **adjacent** (prior art,
failure modes, alternatives). Write the umbrella to
`docs/superpowers/plans/<date>-<feat>-sdd.md`.
**Gate:** the DAG is acyclic, every node has an owner role + an acceptance check, and the
scope matches the target's stated intent.

### P1 · Research fan-out  *(researchers, parallel)*
Launch one `deep-research` subagent per core topic and per adjacent topic. Synthesize
into ONE dossier under `docs/superpowers/research/` with **evidence-forced corrections**
— let the evidence overrule the original design (e.g. #211 caught "register tags are a
net token tax" and "gate artifacts, not reasoning" this way).
**Gate:** every load-bearing claim has ≥2 independent sources, or is explicitly flagged
**unproven** (and then the spec ships a *test*, not a *claim*).

### P2 · Spec scaffold  *(spec-author + coherence-critic)*
Scaffold the RFC (next zero-padded number, front-matter `Status: Draft` + `Track`),
grammar/EBNF, and tables — each citing its shipped reference as ground truth. Then the
coherence-critic runs adversarially against the existing RFC set.
**Gate:** `python3 tools/dockeeper/dockeeper.py` 0 errors · `python3 tests/spec/test_doc_links.py` PASS · critic reports 0 confirmed-critical/major.

### P3 · Implementation fan-out  *(coders, parallel waves)*
Decompose into components in dependency order. Each coder runs in its **own git
worktree** (no collisions; orchestrator holds the only merge authority), plan→code.
**Builds run on `dev-cx53` or GHA only — NEVER on the developer machine** (see CLAUDE.md
3-gate rule). 
**Gate per component:** builds clean, **0 warnings**, `cargo clippy`/`zig build` as
applicable.

### P4 · Test/verify fan-out  *(test-authors, parallel + integration)*
Per-component tests authored **independently of the impl** (a separate, spec-only
subagent — the adversarial-test discipline from hcpbin/sandboxd). Then integration / e2e
(round-trips, cross-impl byte-agreement where two languages meet, benches).
**Gate:** `ci-gate` green at the classified tier; for protocol work, a cross-impl
agreement corpus passes.

### P5 · Integrate & broker  *(broker)*
Assemble **one stacked PR per wave** (reviewable diffs, dependency-ordered). Drive
`ci-gate` + `agent-structure-guard` green. The broker opens PRs **ready-for-review**.
**Stop at human approval — never self-merge.**

## Fan-out discipline (what makes it SDD)
- **Isolation** — every coder/test subagent gets its own worktree (`Agent` with
  `isolation: "worktree"`); only the orchestrator merges.
- **Idempotent waves** — a wave is re-runnable from its inputs (dossier + plan), so a
  failed/garbled subagent just re-fans; no partial state leaks.
- **Independent verification** — test-authors never see the coder's code; critics are
  adversarial; reviewers are a distinct role from coders.
- **Ledger** — append one hash-chained entry per wave (eventd-style) so the run is
  auditable and resumable across sessions/container restarts.
- **Cost guard** — respect the OpenRouter budget; prefer cheap models for fan-out
  (coder/researcher), reserve a reasoner for synthesis/critique only.
- **Dogfood** — the whole DAG is expressible as a Vaked `workflow`
  (`vaked/examples/sdd.vaked`); the skill can emit/refresh that capability graph.

## Anti-patterns (do NOT)
- Orchestrator writing code/specs itself instead of delegating.
- Fanning out the next wave before the current gate is green.
- A subagent reviewing/testing its own output.
- Building on the developer machine, or self-merging a PR.

## Output of a run
1. `docs/superpowers/plans/<date>-<feat>-sdd.md` — the wave-DAG + acceptance gates.
2. `docs/superpowers/research/<date>-<feat>-*.md` — the dossier(s).
3. The spec(s)/RFC + per-component PRs, stacked and ready-for-review.
4. A wave ledger (status checklist) the orchestrator refreshes each wave.
