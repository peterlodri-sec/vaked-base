# Track D — runtime control plane: replay / rewind / jump / step (design)

## Status

Design (2026-06-12). Track D of the 1.0 epic (#17), issue #20 — the control
leg, where the three theories converge: **control is IMPLEMENTED BY
immutability** (eventd log + arena snapshots) **over the parallel OTP tree**.
Depends on Track B (eventd — reference shipped) and Track C (otp.supervision —
shipped). Convention: design → plan → impl; this is the design, plus a first
reference slice (`eventd state`).

## The #20 grammar-first decision, answered

**Control is NOT a language primitive.** No new Vaked kind, no checkpoint
construct: a `.vaked` file declares *what the system is*, and control acts on
*a run of it*. Evaluation stays side-effect-free; the language's only contact
points are the artifacts that already lower (`gen/eventd.json`,
`gen/workflow/<name>.json`, the OTP tree). Runtime control is runtime/protocol
surface — `agent-supervisord` + HCP control frames (a future RFC catalogs
them; the semantics are fixed here and in RFC 0004).

## The five verbs (all folds — nothing ever mutates history)

| Verb | Semantics | Substrate |
|------|-----------|-----------|
| **stop / slow / step** | live scheduling of the driver/agents: pause flag, tick interval, one-shot step | the proven ralph `Control` model (`tools/ralph/ralphcore.py: Control/parse_control` — paused / interval / step), promoted to supervisor state; no log interaction |
| **replay** | `state = fold(entries[0..len))` — reconstruct state from the verified log | `EventLog.replay` (shipped) |
| **jump (inspect)** | `state = fold(entries[0..N])` — the state *as of* entry N, read-only; time-travel debugging | `eventd state --at N` (this slice) |
| **rewind (act)** | make entry N the canonical tip **forward**: append `RewindEvent(producer, rewind_to_step=N, hash)` — never truncate. Anchors above N are void; consumers re-verify and pause `stale_dependency` if affected (RFC 0004 §3.3/§6). Compaction below the GC floor remains the only way bytes ever disappear (§4) | `rewind_event` payload (shipped); supervisor emits it, then restarts the producer's worker (`one_for_one` — only true dependents react, via the dependency layer) |

Key invariant restated: **rewind is an append**. The log is the time axis;
"going back" is a new event that says so. Replaying the whole log therefore
reproduces every rewind too — the audit spine survives its own time travel.

- Sibling safety (epic acceptance 3): rewinding one branch must not corrupt
  concurrent siblings — delivered by arena structural sharing (#16 refcounts):
  a rewound branch shares unchanged nodes; nothing is freed while referenced
  (same shape as the GC floor).
- O(1)-ish jumps: fold-from-genesis is O(N); arena snapshots (eventd design
  phase 4) memoize fold prefixes. Reference ships O(N); the snapshot index is
  the daemon's optimization (#35 snapshot/compaction item).

## Supervisor integration (Track C handoff)

`agent-supervisord` owns the loop: it holds the eventd writer (RFC 0004
single-writer), receives control frames (pause/slow/step per agent or
runtime), and on rewind: (1) pause affected workers, (2) append `RewindEvent`,
(3) restart workers — whose **cold-start verification** (§6) then re-anchors
or pauses them. Control correctness is thus mostly *already specified*: the
verbs compose machinery that shipped with RFC 0004 and the eventd oracle.

## Reference slice shipped with this design

`python3 -m eventd state <log> [--at N]` — verify the chain, fold entries
`0..N` (default: all), print the folded view: entry count, tail hash at N,
per-kind payload counts, live state-dependency summary (registrations /
checkpoints / rewinds / evictions, GC floors per producer) **as of N**. This
is `jump (inspect)` + `replay` in oracle form, and the state the Zig daemon
must reproduce. Exit codes follow the frozen table (0 ok / 4 tampered).

## Plan

1. *(this slice)* `eventd state --at N` + spec-test group (fold-at semantics:
   the same log inspected at N=3 vs N=tip shows pre/post-rewind floors).
2. *(done)* Control-frame catalog → [RFC 0005](../../../protocol/rfcs/0005-control-frames.md)
   (pause/resume/slow/step/rewind + `ControlAck`, preceptord authority,
   accepted actions logged write-ahead as `control_action` events).
3. Supervisor loop (with the agent-supervisord daemon design): control file →
   frames; ralph `Control` semantics promoted.
4. Arena snapshot index for O(1) jumps (#35).
5. Live demo (epic acceptance 3): run the OTP tree (`task otp-smoke`), append
   steps, rewind one producer, observe the dependent pause + the sibling
   untouched.

## Open

- Per-agent vs per-runtime pause granularity in the frame catalog (lean both;
  per-agent is the supervisor child, per-runtime is the tree).
- Does `step` need eventd visibility (an entry per manual step) for replay
  fidelity? Lean yes — control actions are events too.
- `jump` as a *write* operation (fork a branch at N) — defer to the arena
  branch/graft design (#16); inspect-only until then.
