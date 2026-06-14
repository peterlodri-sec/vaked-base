# session-scribe — scrubbed session reasoning transcripts

`session-scribe` exports the current Claude Code chat session as a **cleaned, PII-scrubbed,
enriched** reasoning transcript — a `USER:SYSTEM` conversation safe to share, archive, or attach
to a PR/issue without leaking identity or secrets.

- **Command:** `/session-scribe [output-path]`
- **Skill:** `.claude/skills/session-scribe/SKILL.md`

## Why

The on-disk session `.jsonl` is a poor sharing artifact: it is often unflushed mid-session, the
`thinking` blocks are redacted (text length 0), and it is dense with home paths, UUIDs, hook
echoes, and tool-call spam. `session-scribe` instead reconstructs the session from live
conversation context and emits a human-readable reasoning arc with identity scrubbed.

## What it produces

A Markdown document of `USER:` / `SYSTEM:` turns. Each `SYSTEM` turn is enriched as
**intent → reasoning → outcome** rather than a verbatim dump; noise turns (one-word acks, hook
echoes, repeated tool calls) are collapsed into the decision they served.

## Scrub ruleset

| Class | Replacement |
|-------|-------------|
| Username | `[USER]` |
| Email | `[EMAIL]` |
| Home / absolute paths | `~/...` or `[HOME]/...` |
| Session IDs / UUIDs | `[ID]` |
| GitHub org / owner | `[ORG]` |
| Infra hosts | `[REMOTE_HOST]` |
| Social / personal domains | `[SOCIAL]` |
| Tokens / keys / secrets | `[REDACTED]` |

Technical substance (designs, spec numbers, op names, reasoning, decisions) is **kept**. Identity
is scrubbed; content is not.

## Audit gate

Before the transcript is considered done, the written file is grepped for every scrubbed
identifier. All counts must be `0`; a non-zero hit blocks completion until fixed.

## Limitations

- **Reconstruction, not capture.** The transcript is rebuilt from context. Stretches that cannot
  be recalled are flagged, never fabricated.
- **Thinking tokens are not separable.** The API folds reasoning into `output_tokens` and stores
  `thinking` text redacted, so the transcript captures *decisions*, not raw chain-of-thought.
- **Enrichment is interpretive.** SYSTEM turns summarize intent and outcome; they are not a
  byte-exact replay.

## Usage

```
/session-scribe                       # default output: /tmp/session-transcript-scrubbed.md
/session-scribe /tmp/my-session.md    # custom path
```
