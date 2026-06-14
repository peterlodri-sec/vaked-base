# Repo Context — AIL-0 batch

> Curated context for fresh subagents. You have NO session history. Everything you need
> to do an AIL-0 authoring task correctly is here. Read it before touching files.

## What AIL-0 is

AIL-0 (Agentic Intermediate Language, v0) is a small, EBNF-governed, **register-tagged**
notation for LLM-agent communication: planning, tool-intent, causality, risk, artifacts,
and state. Boot names seen in discussion: "AI-lish", "CUC V2". It is a *register language*,
not a full programming language.

Name stack (use these consistently):

| Name | Meaning | Where it lives |
|------|---------|----------------|
| **AIL** | Agentic Intermediate Language (repo-native name) | this work |
| **AIL-0** | experimental v0 register grammar | this work |
| **CUC** | human-facing compression skill (the `caveman` rename) | PR #203 (open) |
| **ARP** | Agent Register Protocol — model-agnostic primitive layer | issue #202 (open) |
| **HCP** | project wire protocol | `protocol/rfcs/0001-0007` |

Core design rule: **compress what natural language wastes; never compress what machines
need exact.**
- Keep EXACT (zero compression): file paths, symbols, commands, API names, error strings,
  literals, commit subjects, tool arguments.
- Compress (AIL grammar): reasoning scaffold, causality chains, sequencing, confidence,
  task state, register transitions.

Registers: `R:think R:plan R:tool R:risk R:artifact R:commit R:review R:bench`.

Key invention — the **artifact gate becomes grammar, not prose**: `[R:artifact]` and
`[R:commit]` bodies must be English-only, no CJK; `[R:tool]` must preserve exact paths and
symbols; `[R:think]` may compress. This directly targets the PR #203 finding that Chinese
reasoning leaked into artifact outputs on thinking models.

## Verified repo facts (checked 2026-06-14, do not re-derive)

- **PR #203** OPEN — `feat(cuc): rename caveman → cuc + five-model bench complete`,
  branch `claude/caveman-chinese-mode-experiment-yhndpi`. Keep it a clean rename+bench PR.
- **Issue #202** OPEN — `ARP (Agent Register Protocol): model-agnostic primitive layer`.
  AIL-0 docks under #202; do not invent a second control plane.
- **`docs/language/` numbering:** highest is `0024` (MLIR series 0019-0024). Next free = **`0025`**.
  The original spec proposed `0019-...` — that COLLIDES with `0019-mlir-vaked-dialect.md`. Use `0025`.
- **`protocol/rfcs/` numbering:** files are `0001`-`0007`. `0008` is claimed by remote branch
  `claude/rfc-0008-crypto-seal-domain-bw9u87`. Next safe = **`0009`**. Do NOT use the off-convention
  `LFC-0001` prefix from the original spec; RFCs are `00NN-*.md`.
- **Do NOT create `.claude/skills/cuc/`.** It does not exist locally yet — it is PR #203's
  deliverable. Creating it now races the open PR. Any CUC-skill TODO is deferred until #203 merges.

## Binding conventions (CLAUDE.md)

- **Grammar before code.** New grammar goes in EBNF + an example first. (`vaked-language-author` skill.)
- **Protocol decisions live in RFCs** under `protocol/rfcs/`, authored via the `hcp-rfc-author` skill.
- **Each subsystem gets its own design → plan → implementation cycle.** Scaffold the spec first.
- **File a GitHub issue for any versioned-language change.** AIL-0 is one → dock under #202.

## 🚫 NEVER BUILD ON DEVELOPER MACHINE (hard constraint)

The developer machine is an M1 MacBook. **No build/compile/link/test cascade may run on it.**
This includes `pytest`, `python setup.py`, `pip install -e`, `cargo build/test`, `zig build`,
`nix build`, `make`, `docker build`.

- **Allowed locally:** read files, edit/write files, git operations, `cargo fmt --check`,
  `cargo clippy`, static analysis that does not compile.
- **For anything that must RUN code/tests/model-calls:** target `dev-cx53` (Linux, Nix, Tailscale:
  `ssh dev-cx53`) or GitHub Actions. Gated by the 3-gate verify-confirm protocol in CLAUDE.md.

**Implication for this batch:** every task here is AUTHOR-ONLY (markdown, EBNF, RFC text).
There is nothing to compile or test locally. **Do not run any Python, do not run pytest, do not
invoke a parser binary.** If a task seems to need code execution to verify, STOP and report —
that work is deferred to a separate dev-cx53/GHA plan.

## Worktree

You are on branch `worktree-feat+ail-0-bridge`, a fresh worktree off `origin/main`. Commit
author-only changes here. This branch becomes the AIL-0 PR and references PR #203 / issue #202.

## Scope boundary for THIS batch

IN scope (local, author-only):
1. Bootstrap/bridge doc (`docs/context/...`).
2. AIL-0 EBNF grammar file.
3. Morpheme table doc (`docs/language/0025-...`).
4. RFC stub (`protocol/rfcs/0009-...`) in `hcp-rfc-author` style.
5. Bench DESIGN spec (metrics/modes/corpus/model-matrix) — design only, **no Python**.
6. Research docs (produced by the deep-research run) committed under `docs/superpowers/research/`.

DEFERRED (separate plan, runs on dev-cx53/GHA — NOT this batch):
- `tools/cuc-bench/*.py` implementation + the multi-model bench run.
- `.claude/skills/cuc/SKILL.md` TODO note (after PR #203 merges).
