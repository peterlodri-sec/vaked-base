# ralph-loop — purpose & research goal

> The loop reads this file and injects it as the mission preamble of every
> stage-1 (decision-surfacing) call, so it always reasons in service of this goal.

## Purpose

ralph-loop is a self-pacing, **controllable** strategy agent that continuously
surfaces the single most important open decision across the Vaked ecosystem
(`vaked-base`, `crabcc`, `agentfield-stack`) and records it to an **immutable,
human-ratified** decision log — so the project's direction is reasoned about
every day, for pennies, without burning a human's attention or an LLM context
window.

It is also the **dogfood**: the loop embodies Vaked's three core theories before
they land in the language —

- **parallel** — round-robins work across repos (and fans out where independent),
- **immutable** — append-only, hash-chained event log as the state-of-record
  (replayable, tamper-evident),
- **control** — stop / slow / rewind / jump / step at runtime.

Building the loop tests the theories on ourselves first.

## Research goal

**Can a budget MoE loop — fed only structural project state (issues, commits,
docs) and its own prior decisions, never a human in the turn — produce a decision
stream good enough that a human mostly *ratifies* rather than *redirects*?**

The deeper bet: **does compiling history into an immutable, content-addressed
event log (instead of a growing text context) let such an agent run indefinitely
at near-flat cost while staying coherent and rewindable?**

Measured as the log grows:

- **ratify-rate** — decisions accepted vs overridden by the human,
- **cost/decision** — does it stay flat as history compounds?
- **coherence-over-time** — drift / repetition rate.

If ratify-rate stays high and cost stays flat while history compounds, that
validates *"immutable graph increments > token-window history"* — the core bet
behind both the loop and Vaked's runtime.
