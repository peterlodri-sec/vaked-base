# nullclaw evolution map (goWithTheFlow output, 2026-06-13)

Output of the `goWithTheFlow` workflow (11 agents, run `wf_f5878832-8a6`): study
nullclaw/nullclaw → per-agent evolve → verify gate (X) → gated Zig-migration.
Full raw result in the run transcript; this is the synthesis.

## Headline finding: the gate (X) was miscalibrated

The verify gate required `autonomy_score >= 8` (fully autonomous, no human in any
turn) before allowing the Zig-migration stage. **All 5 agents failed it** (scores
5,5,5,7,7) — and that is the *correct* result, for two reasons:

1. Our agents are **advisory / substrate by design**: ralph is advisory (human
   ratifies — PURPOSE.md "ratify-not-redirect"); eventd is an immutable log (it
   records/verifies, it has no turn); the OTP supervision artifact is a static
   lowering projection (0012 "no runtime semantics").
2. **nullclaw's own rubric rewards bounded autonomy** — "Autonomy as a bounded
   safety envelope": deny-by-default, `max_actions_per_hour`, `level: full` is an
   explicit opt-in. Fully-autonomous-≥8 contradicts nullclaw too.

**Correction for next runs:** the gate should test *bounded-autonomy correctness*
(self-heals, rate/scope-limited, replayable, no-human-in-the-*generation*-turn),
NOT `≥8 fully autonomous`. The all-fail is a gate bug, not an agent verdict.

## nullclaw rubric (grounded traits worth adopting)

Fast/small/autonomous, all verified against the real repo:
- **Small static binary** (678 KB, ReleaseSmall + strip triad), **~1 MB RSS**,
  **<2 ms cold start**; size/RSS as hard product constraints (AGENTS.md §2.2).
- **Comptime feature-flag trimming** (`-Dchannels`/`-Dengines` compile out unused
  subsystems).
- **Self-supervising daemon** (exponential backoff, state flush, graceful stop).
- **Heartbeat self-tasking** + **skillforge Scout→Evaluate→Integrate** (auto-
  discover/score/integrate on a timer) — strongest autonomy signals.
- **Automatic history compaction** (keep_recent=20, token-limit trigger) for
  unbounded unattended runs.
- **Vtable + factory** swappability; **caller-owns-the-impl** ownership rule.
- **5,300+ tests, 0 leaks** (std.testing.allocator), `builtin.is_test` side-effect
  guards; pre-push hook blocks on any failure/leak.
- **Exact Zig 0.16 API discipline** (`std.fs.File.stdout()`, `std.http.Client.fetch`,
  `std.process.Child` `.Pipe`) — matches the churn we hit in the vakedc canary +
  arena.

These are the patterns the eventual Zig agent plane (zig-port #15) should follow.

## Per-agent verdicts + the REAL wins (gate aside)

Grounding was excellent across the board (accurate line cites); the only ungrounded
items: agent-supervisord's regression test (it assumed `operatorMap` is a fiber — it
is a `surface`, so a `gen/zig/operatorMap.json` it asserts never exists), and
flow-driver's "status = replay (both exist)" (replay/payloads need enriching first).

| agent | grounded wins (adopt) | honest N/A |
|---|---|---|
| ralph | flat-cost compaction · 3×→1 gh fetch · backoff · gh-org repo auto-discover · ratify/override feedback loop (records the PURPOSE.md metric) | binary-size/Zig traits |
| flow-driver | **flat-cost fix (headline)** · status.json→event-log projection · implement rewind+jump (M4) · resume-on-crash · urllib-trim read-only paths | strip/RSS/comptime |
| eventd | append O(n)→O(1) (cache tail+seq) · fsync-on-append + truncate-torn-tail recovery · boot-time verify_chain hard-fail · checkpoint compaction folding a prefix into an arena snapshot | heartbeat/skillforge/cron (a log has no turn) |
| agent-supervisord | child_spec enrichment (restart=permanent, shutdown_ms, config_path→same gen/zig bytes) · `rest_for_one` from supervised-dag · restart_intensity envelope (3/60s) | self-task/self-extend/schedule |
| nullclaw-sentinel(=ralph) | same as ralph + step one-shot bug fix + cron-persistence (survive restart) | Zig-binary traits |

## Prioritized backlog (filed as issues)

1. **flat-cost bug** — stage-2 injects the whole growing log; compact to keep_recent.
   Breaks the PURPOSE.md research bet. Found independently by 3 agents. (HIGH)
2. **eventd hardening** — O(1) append + fsync + boot verify_chain. (correctness)
3. **status.json → event-log projection** + the `step` one-shot writeback bug.
4. **OTP supervision emitter enrichment** (child_spec/rest_for_one/restart_intensity)
   — folds into the M3 emitter (PR #22 / #19).
5. **gate recalibration** — next goWithTheFlow run: bounded-autonomy correctness, not ≥8.

## Verdict

goWithTheFlow's value was NOT a Zig migration (correctly gated off) — it was a
line-cited audit that surfaced a research-bet-breaking cost bug + an eventd
correctness set + the recognition that our advisory/substrate design is *aligned*
with nullclaw's bounded-by-default ethos. The Zig convergence (zig-port #15) adopts
the rubric's build/test/API discipline; the agents stay bounded by design.
