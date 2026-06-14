# CUC V2 / AIL-0 Bootstrap Bridge

> Context note for contributors entering the AIL-0 branch. Read before editing
> anything on `worktree-feat+ail-0-bridge` or referencing PRs #203 / issue #202.

---

## Name stack

Use these consistently. All five names are live in the repository.

| Name | Meaning | Where it lives |
|------|---------|----------------|
| **AIL** | Agentic Intermediate Language (repo-native name) | this work |
| **AIL-0** | experimental v0 register grammar | this work |
| **CUC** | human-facing compression skill (the `caveman` rename) | PR #203 (open) |
| **ARP** | Agent Register Protocol — model-agnostic primitive layer | issue #202 (open) |
| **HCP** | project wire protocol | `protocol/rfcs/0001-0007` |

---

## What each layer is (and is not)

CUC V1 is a compression *style* — the wenyan-ultra mode shipped inside the
`caveman` skill and renamed via PR #203. It is a human-readable convention, not
a grammar: there is no parser, no formal register syntax, and no enforcement
boundary. AIL (Agentic Intermediate Language) is a different thing: an
EBNF-governed *register substrate* that gives the notation a formal grammar,
machine-checkable register tags (`R:think`, `R:plan`, `R:tool`, `R:risk`,
`R:artifact`, `R:commit`, `R:review`, `R:bench`), and an explicit artifact
gate. ARP (issue #202) is the model-agnostic *protocol layer* that carries AIL
frames between agents, independent of any particular model or transport; it sits
below AIL the way a wire protocol sits below a message format. AIL-0 is the
working name for the experimental v0 grammar that will eventually dock under
ARP. These three layers have different scope and different delivery timelines;
conflating them produces incorrect dependency ordering.

---

## Core design rule: keep-exact vs compress

**Compress what natural language wastes; never compress what machines need exact.**

Keep EXACT (zero compression allowed):
- file paths
- symbol names
- command literals and flags
- API names
- error strings and log literals
- commit subjects
- tool arguments

Compress via AIL grammar registers:
- reasoning scaffold
- causality chains
- sequencing and ordering prose
- confidence qualifications
- task state and transition narration
- register transitions

The distinction is not stylistic — it is load-bearing. Compressing a file path
or commit subject breaks grep, shell expansion, and downstream tooling. Leaving
reasoning scaffold in verbose English wastes tokens with no machine-side benefit.

---

## Keeps PR #203 honest

PR #203 (`feat(cuc): rename caveman -> cuc + five-model bench complete`, branch
`claude/caveman-chinese-mode-experiment-yhndpi`) is a clean rename-and-bench PR.
Its scope ends there: rename the skill, deliver the five-model bench results, close
the PR. AIL-0 grammar work lives on its own branch (`worktree-feat+ail-0-bridge`)
and references PR #203 for the CUC V1 baseline, but does not merge into it and
does not depend on it landing. If PR #203 ships first, the AIL-0 branch picks up
the CUC rename and builds forward. If AIL-0 ships first, PR #203 remains
unaffected. Neither branch touches `.claude/skills/cuc/` while the other is open;
that directory is PR #203's deliverable and creating it here would race the open PR.

---

## Forward pointer: artifact gate stays English until the parser exists

The artifact gate rule (`[R:artifact]` and `[R:commit]` bodies must be
English-only, no CJK; `[R:tool]` must preserve exact paths and symbols) is
stated in the grammar design. It is enforced today as a *prose rule*, not by a
parser. Until an AIL-0 parser exists and is integrated into CI, compliance is
author-checked and reviewer-checked, not machine-checked. Do not claim automated
enforcement before that integration is in place.

---

## Honest baseline: no proven token savings yet

Register-tagged compression carries a token tax: every `[R:think]` or
`[R:artifact]` tag is additional tokens that untagged text does not pay. Whether
AIL-0 produces a net token reduction depends on whether the compression of
verbose reasoning scaffold outweighs the tag overhead across real agent
transcripts. The wenyan-ultra bench in PR #203 measured character-level
compression; token-level savings are not the same number and have not been
measured under AIL-0's register tagging scheme. AIL-0 is a hypothesis the bench
must test on *tokens*, not characters. Do not assert net token savings until a
token-level bench run has been executed and its results committed under
`docs/superpowers/research/`.
