# Ratifying ralph decisions

**You don't need to know the whole codebase to do this.** This is a ~daily,
~1-hour triage pass over machine-suggested decisions. You read each new
suggestion, decide whether it's sound, and record a one-line verdict. That's it.

## What is this?

[`ralph`](../../tools/ralph/README.md) is an autonomous loop. A few times a day,
for one of Vaked's hard design areas ("tracks"), a cheap model reads the
project's current state and **proposes the single most important open decision**,
appending it to that track's log:

- `<track>.ralph-log.md` — the **advisory decision log** (machine-written,
  append-only, never edited).

The model has **no authority**. Nothing happens until a human **ratifies**. Your
job is to be that human.

## The daily pass

1. **Find what's new.** Run `python3 tools/ralph/ralph.py ratify` for a per-track
   summary (decisions surfaced, verdicts recorded, ratify-rate, and the
   un-acted backlog). Then open the `*.ralph-log.md` files with un-acted entries.
2. **Read each new `## … Decision #N` entry.** Each has: the decision/question,
   options, a recommendation, risks, next actions, and a confidence level. Ask:
   *is this real, correctly framed, and is the recommendation sound?*
3. **Record one verdict per decision** by appending a line to the track's
   **ratify log** — `<track>.ratify-log.md` (create it if absent). Never edit the
   decision entry itself; ratification is a separate append, so the record stays
   immutable.

### Verdict line format

```
- <track>#<N> — **ratify** | **override** | **defer** — <one-line reason> — @you 2026-06-12
```

Concrete examples:

```
- graph-concept#3 — **ratify** — sound; opening the follow-up issue — @pl 2026-06-12
- mlir-topology#1 — **override** — conflates lowering with the dialect; wrong layer — @pl 2026-06-12
- hcp-litany#2 — **defer** — depends on RFC-0003 landing first — @pl 2026-06-12
```

### The three verdicts

| verdict | meaning | what you do next |
|---------|---------|------------------|
| **ratify** | The decision is sound. | Adopt it — usually **open a GitHub issue** to do the work. The pass is triage, not implementation. |
| **override** | It's wrong or mis-framed. | Your **reason is the correction** — it's fed back into the loop's next prompt so it learns what you reject. |
| **defer** | Not now (blocked / premature). | Nothing yet; it can re-surface later. |

## Why it's shaped this way

- **Append-only.** Decision logs and the event ledger are never rewritten, so the
  whole history is replayable and tamper-evident (`ralph events --replay`).
- **Override reasons train the loop.** Recent `override` reasons are injected into
  the next stage-1 prompt for that track, so the stream should drift toward what
  you'd ratify. The metric to watch is **ratify-rate** (ratified ÷ (ratified +
  overridden)) — `ralph ratify` prints it. If it climbs as the log grows, the
  loop is working.
- **Cadence is the guard.** The loop is paced to ~8 decisions/day so a ~1h pass
  keeps up. If the backlog (`todo`) grows faster than you ratify, slow the loop
  (fewer tracks / a longer cron interval) rather than letting the log become
  un-ratified noise.

## "What's next" after a pass

- Ratified decisions → file GitHub issues for the actual work.
- Overrides → nothing to do; the reason does the work.
- Glance at `ralph ratify`'s ratify-rate trend over the week.

That's the whole loop: **the model proposes, you dispose, the log remembers.**
