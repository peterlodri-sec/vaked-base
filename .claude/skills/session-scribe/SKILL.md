---
name: session-scribe
description: >
  Use when asked to export, scrub, share, or archive a transcript of the current chat/session
  as a clean reasoning conversation. Produces a PII-scrubbed, enriched USER:SYSTEM transcript
  reconstructed from conversation context (not from disk — the live session transcript is often
  not flushed locally). Trigger on "transcript", "scrub session", "session export", "cleaned
  conversation", "reasoning transcript", "share this chat".
---

# session-scribe

Turn the current session into a **cleaned, PII-scrubbed, enriched** reasoning transcript safe to
share or archive. The source is your own conversation context — you reconstruct it, you do not
read the on-disk `.jsonl` (it is frequently absent, redacted, or unflushed).

## Output format

A Markdown document of `USER:` / `SYSTEM:` turns. `SYSTEM` = the assistant. Each SYSTEM turn is
enriched as **intent → reasoning → outcome**, not a verbatim dump. Collapse noise turns
(one-word acknowledgements, hook echoes, repeated tool calls) into the decision they served.

```
USER: <what the user asked, condensed>

SYSTEM: <intent>. Reasoning: <why this approach>. Outcome: <what happened / what was produced>.
```

End with a short "Cross-cutting reasoning patterns" section if the session is long enough to have them.

## Scrub ruleset (MANDATORY)

| Class | Example → Replacement |
|-------|----------------------|
| Username | `alice` → `[USER]` |
| Email | `a@corp.com` → `[EMAIL]` |
| Home / absolute paths | `/Users/alice/...` → `~/...` or `[HOME]/...` |
| Session IDs / UUIDs | `ec81…760` → `[ID]` |
| GitHub org / owner | `acme-sec/repo` → `[ORG]/repo` (keep repo if non-identifying) |
| Infra hosts | `prod-cx53`, `bastion` → `[REMOTE_HOST]` |
| Social / personal domains | `social.example.app` → `[SOCIAL]` |
| Tokens / keys / secrets | any → `[REDACTED]` |

**Keep** technical substance: designs, file names that are part of the work (e.g. spec numbers,
op names), reasoning, trade-offs, decisions. Scrub **identity**, not **content**.

## Audit (run before declaring done)

Grep the written file for every identifier you scrubbed. All counts MUST be 0:

```bash
for pat in <username> <email-local-part> <org> <host> <known-uuid-prefixes> <social-domain>; do
  printf '%s: ' "$pat"; grep -ic "$pat" <output-file>
done
```

If any pattern is non-zero, fix the transcript and re-audit. Do not report success on a dirty audit.

## Principles

- **Reconstruct, don't fabricate.** If a stretch of the session is unrecoverable from context,
  say so explicitly rather than inventing turns.
- **Enrich, don't transcribe.** The value is the reasoning arc, not a keystroke log.
- **Scrub is non-negotiable.** A single leaked identifier defeats the purpose; the audit gate is hard.
- **Neutral output path.** Default to a path with no username (e.g. `/tmp/...`), since the artifact
  is meant to be shared.
