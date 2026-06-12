# eventd — append-only hash-chained event log (design)

## Status

Design (2026-06-12). Track B of the 1.0 epic (#17), issue #18. The **immutable
leg**: the tamper-evident, replayable spine shared by the runtime AND the
release-driver. Convention: daemon = design → plan → impl; this is the design.
The **format is already proven** — the ralph driver implements it today
(`tools/ralph/ralphcore.py: make_entry/verify_chain`, `tools/ralph/ralph.py:
append_event/load_events/replay_events`), so eventd is that format promoted to a
runtime daemon.

## Purpose

A single, append-only, hash-chained event log per runtime. Every state change is
an entry; **state is the fold over the log** (never patched in place). This gives
Vaked its immutability theory at runtime: tamper-evidence, deterministic replay,
and the substrate for control (rewind/jump, Track D #20) — you rewind by
replaying the log up to entry N over the content-addressed arena (#16).

This mirrors how an agent turn is shaped (the canonical sketch):

```
system  = mission preamble (the goal; never in the log)
messages = the hash-chained log, append-only   ← eventd
        + the one new turn (the only thing changing)
```

History lives entirely in the log; the model/runtime reads the localized branch
it acts against, not a growing mutable blob.

## Entry format (frozen — matches ralphcore today)

One JSON object per line (JSONL), append-only:

```
{ "seq": <u64, 0-based>,
  "prev": <hex sha256 of the previous entry, GENESIS = 64×"0" at seq 0>,
  "payload": <arbitrary JSON event body>,
  "hash": sha256(prev_hex || canonical_json(payload)) }
```

- `canonical_json` = sorted keys, compact separators, `ensure_ascii=False` (the
  bytes hashed). Identical to `ralphcore._canon`.
- **Verify** (`ralphcore.verify_chain`): seq is 0,1,2,…; each `prev` links the
  prior `hash`; each `hash` recomputes. Any tamper (payload edit, reorder,
  insert, drop) breaks the chain.
- **Replay** = fold the verified entries → state (`ralph.replay_events` is the
  reference fold; the runtime fold reconstructs the typed graph instead).

## Daemon shape (runtime)

- One log per runtime instance: `var/lib/<runtime>/eventd/log.jsonl` (path is a
  lowering output, 0012).
- Writers append via a single-writer discipline (the OTP `agent-supervisord`
  owns the writer; fibers emit events to it) — append-only, fsync-on-append for
  durability; the hash chain makes concurrent-reader snapshots safe.
- Readers (dashboard, replay, rewind) map the log read-only and fold.
- **Tamper check on boot**: verify the chain before accepting a log; a broken
  chain is a hard error (the audit spine must be intact). Matches the
  `docs/runtime/README.md:16` "tamper-evident audit spine" intent.

## Relationship to the arena (#16)

eventd is the **time axis** (what happened, in order); the substrate arena is the
**content** (immutable content-addressed graph nodes). An event payload
references arena `NodeId`s, not inline data. Rewind to entry N = fold events
0..N, resolving `NodeId`s against the arena; refcount structural sharing (#16)
means a rewound branch shares unchanged nodes with siblings — rewinding one does
not fracture another. This is exactly what Track D (control) consumes.

## Phases

1. **(done) format + tooling reference** — ralph driver: chain + verify + replay,
   29/29 tests. eventd adopts this format verbatim.
2. **(reference done)** eventd daemon: single-writer append + fsync + boot-time
   chain verify — the **Python reference/oracle** lives at `/eventd`
   (`EventLog`: flock single-writer, fsync-on-append, TamperError on boot;
   CLI `python3 -m eventd {verify,append,replay,floor,coldstart}`;
   `tests/spec/test_eventd.py` cross-verifies the format against ralphcore).
   It also carries the **RFC 0004 state-dependency layer** (`eventd.statedep`:
   DependencyRegistration / ConsumerCheckpoint / RewindEvent / eviction
   payloads, the O(1) `DependencyIndex`, `gc_floor`, cold-start verifier —
   RFC 0004 §8 orders 1–4, 6, 7). Remaining for this phase: the Zig daemon
   port (#15 pattern, Python as oracle) and the per-runtime log path as a
   0012 lowering output.
3. runtime fold: reconstruct the typed semantic graph from the log (state =
   fold), over the arena.
4. (Track D) rewind/jump: fold 0..N; arena snapshots for O(1) checkpoints.

## Verification

- The ralph reference already proves format + verify + replay (`python3
  tools/ralph/test_ralph.py` → chain verify/tamper/reorder + replay fold).
- Daemon: a chain-verify test on a written log; a tamper test (flip a byte →
  boot rejects); a replay determinism test (same log → byte-identical folded
  state).

## Open

- fsync cadence vs throughput (batch-append?).
- log rotation / compaction without breaking the chain (checkpoint entries that
  fold a prefix into an arena snapshot, then chain forward).
- single-writer vs multi-writer (per-fiber sub-logs merged by seq?) — start
  single-writer.
