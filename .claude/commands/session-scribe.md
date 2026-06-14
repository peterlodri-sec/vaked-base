---
description: Emit a cleaned, PII-scrubbed, enriched USER:SYSTEM reasoning transcript of the current session.
---

Produce a **scrubbed reasoning transcript** of the current chat session for: **$ARGUMENTS**
(optional argument: output path; default `/tmp/session-transcript-scrubbed.md`).

Use the `session-scribe` skill. Steps:

1. **Reconstruct** the session from your own conversation context — every USER turn and your
   SYSTEM (assistant) reasoning + outcome. Collapse noise (one-word acks, hook echoes,
   tool-call spam) into the decision it served. Do **not** fabricate turns you cannot recall.
2. **Scrub** per the skill ruleset: usernames / emails / home paths → placeholders;
   session IDs / UUIDs → `[ID]`; GitHub org/owner → `[ORG]`; infra hosts + social domains →
   generic; tokens / secrets → `[REDACTED]`. Keep technical substance (designs, reasoning, decisions).
3. **Format** as `USER:` / `SYSTEM:` turns. Enrich each SYSTEM turn as intent → reasoning → outcome.
4. **Write** to the output path.
5. **Audit** (skill §Audit): grep the output for every identifier pattern; report hit counts.
   Every pattern MUST be `0`. If any is non-zero, fix and re-audit before reporting done.
6. **Surface** what was collapsed or could not be reconstructed. Never present a partial
   transcript as complete.
