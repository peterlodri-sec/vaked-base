# doc-keeper

Deterministic **doc / spec / RFC drift** checks for vaked-base — the third fleet
agent (sibling to `tools/ralph` and `vaked-agents/ci/pr-review`). The pr-review
agent twice claimed a doc/file was "missing" when it existed; the honest answer to
*"does this reference resolve?"* is a checker, not another model. doc-keeper gates
that drift in CI.

## Checks
- **RFC cross-refs** — every `RFC 00NN` mention in `protocol/**` resolves to a
  `protocol/rfcs/00NN-*.md`. A reference **within** the existing range that doesn't
  resolve is an **error** (gap/typo); one **beyond** the highest existing RFC is a
  **warning** (planned/forward reference). External RFCs (`RFC 9110`, no leading
  zero) are ignored.
- **Repo-path refs** — backticked tokens in prose that *look* like repo paths
  (a `NNNN-name.md` design doc, or `topdir/…/file.ext` under a real top-level dir)
  must resolve. **Error** if dangling. Templates (`<x>`, globs) and illustrative
  paths whose first segment isn't a real top-level dir are ignored. Design/plan/
  decision docs (`docs/superpowers/`, `docs/decisions/`) are skipped — they
  intentionally describe future files.
- **Stub-README freshness** (warn) — a README that says "Currently empty" / "Stub"
  whose target dir now holds real code (`.rs/.zig/.erl/.ex/.py`).

Markdown **link** resolution is already covered by `tests/spec/test_doc_links.py`
and is not duplicated here.

## Run
```
python3 tools/dockeeper/dockeeper.py          # errors fail (exit 1), warnings don't
python3 tools/dockeeper/dockeeper.py --strict # warnings fail too
python3 tools/dockeeper/test_dockeeper.py      # unit tests (stdlib, no deps)
```
Stdlib-only (Python 3.10+). CI: [`.github/workflows/docs-keeper.yml`](../../.github/workflows/docs-keeper.yml)
runs it on doc/protocol pushes, PRs, and a weekly cron.

## Possible follow-ups
- LLM pass (OpenRouter, ralph-style) to *draft a fix PR* for detected drift.
- Section-level RFC cross-ref validation (`§9.2` resolves to a real heading).
- Extend stub-freshness to `protocol/` impl dirs once code lands.
