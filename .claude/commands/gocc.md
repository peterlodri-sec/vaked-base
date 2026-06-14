---
description: gocc — one ARP-traversable pipeline (caveman-ultra) brainstorm → enriched parallel plan → subagent-driven build → PR → review → simplify → suggestions
argument-hint: <topic-or-task>
---

# /gocc — ARP execute

Run the full development lifecycle for **$ARGUMENTS** as a single **ARP-traversable
pipeline**: the stages below form a traversable execution graph with a **checkpoint
between each stage**. The pipeline is pausable / resumable / rewindable — if the
user interrupts, report the current checkpoint and the last clean stage so it can
resume or rewind there. Speak in **caveman ULTRA** throughout (code, commits, PRs,
and security notices stay normal prose).

## Mode

Invoke the `caveman` skill at intensity **ultra** first, then keep it for the whole
run. Do not narrate tool calls; report one **checkpoint line** per stage.

## Stages (wavefronts)

Each stage ends at a checkpoint. Do not advance past a checkpoint with failing
tests, an unmet gate, or an open review issue. Emit `✓ checkpoint <n>: <stage> — <one-line state>` after each.

1. **Brainstorm** — invoke `superpowers:brainstorming` on `$ARGUMENTS`. Honor its
   HARD-GATE: design must be presented and approved, spec written + committed,
   before any code. Terminal artifact = a committed spec doc.
   *Checkpoint 1: spec committed, path reported.*

2. **Plan (parallel-enriched)** — invoke `superpowers:writing-plans` on the spec.
   **Enrichment:** tag every task `parallel-safe` or `sequential` and record its
   `depends-on` tasks, so the build stage can fan out. Group parallel-safe tasks
   into wavefronts (mirror the 0015 schedule model).
   *Checkpoint 2: plan committed, wavefronts identified.*

3. **Isolate** — ensure an isolated workspace via `superpowers:using-git-worktrees`
   (never build on `main`). Verify a clean baseline (`tests/spec/run_all.py` green).
   *Checkpoint 3: worktree ready, baseline green.*

4. **Build** — invoke `superpowers:subagent-driven-development` to execute the plan.
   Dispatch one implementer per task; fan **parallel-safe** tasks within a wavefront
   via `superpowers:dispatching-parallel-agents` up to the worker ceiling (see
   **Scale & fan-out**); run sequential tasks in order. Two-stage review (spec
   compliance → code quality) per task. Keep tests green at every commit.
   *Checkpoint 4: all tasks complete, suite green.*

5. **PR** — open a pull request for the branch (use `gh`). Title + body describe the
   spec, the wavefronts, and the verification results.
   *Checkpoint 5: PR number reported.*

6. **Review** — run the `code-review` skill (or `/review`) against the opened PR.
   Apply must-fix findings on the branch; re-run until clean.
   *Checkpoint 6: review clean.*

7. **Simplify** — run the `simplify` skill over the PR diff (reuse / dead code /
   altitude). Quality only — no behavior change. Keep tests green.
   *Checkpoint 7: simplified, suite green.*

8. **Suggestions** — emit a short caveman-ultra list of next ARP steps: deferred
   items from the spec's v0 boundary, follow-up specs, and any risks surfaced.
   *Checkpoint 8: pipeline complete.*

## Scale & fan-out (N logical SWE → bounded workers)

The plan's parallel-safe tasks are **logical SWE work items**. Map N logical items
onto the physical worker pool through a work-stealing queue; **wavefronts gate
ordering** (the 0015 schedule). The schedule is the scale-invariant abstraction:
the *same plan* runs on 16 workers or N — only the pool size changes.

The north star — **N≈millions of SWE workers, near-hardware-speed, real-time** —
is **not** delivered by orchestration subagents. It is delivered by the **generated
artifact's** inline-compiled projection (0015 Layer 2: static schedule, one address
space, no supervisor, no wire) and stress-validated by **zeta-bench** (hard
real-time suite). gocc encodes the schedule so the same plan scales onto that
runtime when it exists; it does not itself spawn millions of agents.

## Reality / caps (honest — do not overclaim)

Claude Code subagent dispatch is hard-capped: ~`min(16, cores−2)` concurrent,
~1000 lifetime. gocc's build stage fans out **to that ceiling**, then queues the
rest. "XXM SWE / near-hardware / real-time" is the **runtime vision** (inline-
compiled projection + a future swarm-runtime spec + zeta-bench), reached by what
gocc *builds*, not by gocc's own agent fan-out. Report the real worker count used;
never claim million-scale dispatch that the harness cannot perform.

## Rewind / stop

- **rewind <n>** → return to checkpoint `n` and re-run from there (prior stages'
  committed artifacts are the restore points).
- **stop** → halt at the current checkpoint, leave the branch + PR as-is, report
  state. No destructive cleanup.

## Guardrails

- Never skip the brainstorm approval gate or the per-task two-stage review.
- Never commit to `main`; never force-push.
- A red test suite is a hard stop — fix or report `BLOCKED`, do not advance.
- PR-dependent stages (6, 7) operate only on the PR opened in stage 5.
