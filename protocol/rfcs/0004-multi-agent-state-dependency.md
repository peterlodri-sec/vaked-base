# RFC 0004 — Multi-Agent State Dependency (registration, GC, rewind)

- **Status:** Draft
- **Created:** 2026-06-12
- **Track:** Protocol
- **Alias:** referred to as **"RFC 0005"** in the 2026-06-12 owner design
  sessions (numbered 0004 here: next in the series). External notes citing
  "RFC 0005" mean this document.

## Abstract

This RFC defines the **state-dependency layer** of HCP: how a consumer agent
durably registers a causal dependency on a producer agent's step output, and
the three **non-optional invariants** that make a multi-agent cluster's history
safe to compact, its topology safe to run, and its restarts safe to trust:

1. **Log GC is dependency-aware** — no agent may truncate producer history
   still referenced by any downstream consumer checkpoint (§4).
2. **State-consumption topology is a DAG per topology epoch** — enforced
   before runtime by the compiler, over typed edges (§5).
3. **Cold start verifies dependency freshness before RUNNING** — an agent
   pauses on stale anchors instead of sprinting into corrupt history (§6).

Every dependency artifact carries the **topology epoch** that authorized it
(§7), so "was this dependency legal under the topology that created it?" stays
answerable forever. These are invariants of the protocol, not implementation
notes: a conforming runtime MUST enforce all three.

The compiler counterpart is
[`docs/language/0013-mlir-topology-compilation.md`](../../docs/language/0013-mlir-topology-compilation.md)
(the `hcp` dialect lowers `vaked.consume` to the frames defined here); the
durable substrate is `eventd`
([design](../../docs/superpowers/specs/2026-06-12-eventd-design.md), the
hash-chained per-runtime log) and the content-addressed arena. Lifecycle
transitions are owned by `agent-supervisord`
([runtime roster](../../docs/runtime/README.md)).

## Terminology

| Term | Definition |
|------|------------|
| Producer / consumer | The agent whose step output is read / the agent reading it. One agent may be both, for different edges. |
| Step / `StepId` | One entry in an agent's hash-chained event log (`eventd` seq). |
| `StepHash` | The eventd entry hash of a step — the cryptographic anchor a dependency pins. |
| Dependency anchor | The `(producer, producer_step, producer_step_hash)` triple a consumer's state is built on. |
| `DependencyRegistration` | The write-ahead control frame declaring an anchor **before** consumption (§3). |
| `ConsumerCheckpoint` | A consumer's durable acknowledgement of how far its dependency on a producer has been folded into its own committed state (§4). |
| GC floor (`producer_gc_floor`) | The lowest producer step still pinned by any downstream checkpoint; compaction is legal only strictly below it (§4). |
| Topology epoch | A monotonically increasing version of the state-dependency graph; bumped on any change to it (§7). |
| `RewindEvent` | The event frame announcing that a producer's canonical history was rewound past anchors consumers may hold (§3.3). |
| `stale_dependency` | The paused lifecycle state entered when a cold-start anchor check fails (§6). |
| Edge kind | The typed class of a graph edge: `state_dependency`, `observation`, `control_signal`, `metrics` (§5). |

Terms shared with the overview live in
[`docs/protocol/README.md`](../../docs/protocol/README.md); both tables are
kept aligned.

## 1. Dependency model

Agent B consuming agent A's step-N output creates a **causal anchor**: B's
downstream state is only meaningful while A's step N remains part of A's
canonical history. Three artifacts manage that anchor's lifecycle:

```text
DependencyRegistration   (write-ahead: BEFORE consumption — §3)
        │ pins (producer, step, hash, epoch)
        ▼
ConsumerCheckpoint       (after fold: "I committed past it" — §4)
        │ releases history below min_required_step
        ▼
producer_gc_floor        (compaction boundary — §4)

RewindEvent              (exception path: the anchor itself moved — §3.3)
```

All three are events on the hash-chained `eventd` log, so the dependency
record is itself tamper-evident and replayable.

## 2. Frames (`.hcplang`)

Normative shapes, in the RFC-0002 schema language. Header fields
(kind/corr/stream/seq/end) are implicit; tags begin at `@1`.

```hcplang
schema hcp.statedep {
  version = "0.1.0"

  /// Why a supervisor refused the RUNNING transition (§6).
  record StaleDependency {
    producer:        uuid    @1   # producer AgentId
    expected_step:   u64     @2
    expected_hash:   hash    @3
    observed_tip:    u64?    @4   # producer's canonical tip, if reachable
    topology_epoch:  u64     @5
  }

  /// Write-ahead declaration of a causal anchor. MUST be durably logged
  /// (eventd) before the consumer reads the producer's step output (§3).
  frame DependencyRegistration control {
    consumer:           uuid  @1
    producer:           uuid  @2
    consumer_step:      u64   @3   # consumer step that will consume it
    producer_step:      u64   @4
    producer_step_hash: hash  @5
    topology_epoch:     u64   @6   # the epoch that authorized this edge (§7)
  }

  /// Durable acknowledgement: the consumer's committed state has folded the
  /// producer dependency up to consumer_checkpoint_step (§4).
  frame ConsumerCheckpoint control {
    consumer_agent:           uuid       @1
    producer_agent:           uuid       @2
    min_required_step:        u64        @3   # lowest producer step still needed
    consumer_checkpoint_step: u64        @4
    topology_epoch:           u64        @5
    last_heartbeat_at:        timestamp  @6   # liveness lease (candled — §4.2)
  }

  /// A producer's canonical history was rewound to rewind_to_step; anchors
  /// above it are void. Consumers MUST re-verify (§3.3).
  frame RewindEvent event {
    producer:        uuid  @1
    rewind_to_step:  u64   @2
    rewind_to_hash:  hash  @3
    topology_epoch:  u64   @4
  }
}
```

## 3. Write-ahead discipline

### 3.1 Registration precedes consumption

A consumer MUST durably log `DependencyRegistration` **before** fetching or
folding the producer's step output. The compiler makes this structural rather
than manual: the `hcp` dialect's lowering of `vaked.consume`
(0013 Pass 2) injects `create_registration_token → write_ahead_log →
fetch_canonical_data` — hand-written registration is a conformance smell.

### 3.2 Verification on registration

The registration's `producer_step_hash` MUST be checked against the producer's
canonical chain (or a retained accumulator, §4.1-2) at registration time. A
mismatch is a protocol error, not a warning.

### 3.3 Rewind

When a producer's history is rewound (Track-D control), it MUST emit
`RewindEvent` before serving any post-rewind step. Consumers holding anchors
above `rewind_to_step` MUST treat them as void and re-enter dependency
verification (§6) — running state built on a voided anchor is the precise
failure this RFC exists to prevent.

## 4. Invariant I — dependency-aware log GC

> No agent may truncate producer history that is still referenced by any
> downstream consumer checkpoint.

### 4.1 The GC floor

```text
producer_gc_floor =
  min( all downstream consumers'
       acknowledged min_required_step[producer_agent_id] )
```

A producer may compact or truncate log entries **strictly below**
`producer_gc_floor`, and only when all three hold:

1. **Checkpointed past.** Every registered downstream consumer has
   checkpointed beyond the referenced `producer_step`.
2. **Proof retained.** The `producer_step_hash` of every surviving anchor
   remains verifiable: included in a retained snapshot, a Merkle accumulator,
   or the canonical segment footer (retained artifacts are relics —
   `reliquaryd`). Compaction MUST preserve the cryptographic proof chain for
   surviving anchors — no "cryptographic hostage evicted from disk."
3. **Epoch auditable.** The topology epoch that created the dependency edge
   is still available for audit (§7).

### 4.2 Dead consumers

A consumer that stops checkpointing pins the floor forever — a denial-of-
compaction hazard. `last_heartbeat_at` (fed by `candled` liveness) is the
lease: a consumer silent past the configured lease window MAY be evicted from
the floor computation **only** by an explicit, logged operator/supervisor
action — never silently. Eviction voids that consumer's anchors; if it
returns, cold-start verification (§6) pauses it as `stale_dependency` rather
than letting it run on history that no longer exists.

## 5. Invariant II — the state-dependency subgraph is a DAG

> Dependency edges used for **state consumption** MUST form a DAG per
> topology epoch.

Not all edges are equal; the graph carries **edge kinds**:

| Edge kind | Cycles |
|-----------|--------|
| `state_dependency` | **forbidden** — the subgraph MUST be acyclic |
| `observation` | allowed (metrics, surfaces, chat) |
| `control_signal` | allowed with guardrails (supervision is inherently cyclic: supervise ↓ / signal ↑) |
| `metrics` | allowed |

The hard rule:

```text
subgraph(edge.kind == state_dependency) MUST be acyclic   (per topology epoch)
```

Enforcement is **before runtime** — the compiler pass
`VerifyStateDependencyDAG` (0013 Pass 1) takes the agent graph + dependency
registration edges + epoch and rejects the build on a cycle. The Stage-0 form
already ships in `vakedc`: a `workflow`'s step edges are `state_dependency`
edges and are rejected cyclic (`E-WORKFLOW-CYCLE`,
[0015](../../docs/language/0015-workflow.md)); mesh delegation edges are an
authority axis (attenuation-checked, not state-consuming); surface `input`
edges are `observation`. This section generalizes that split to all runtime
dependency edges, so feedback loops stay possible without ever becoming
state-consumption deadlock.

## 6. Invariant III — cold start verifies before RUNNING

> An agent cannot transition to RUNNING until its direct dependency anchors
> are validated against the last committed dependency state.

Boot sequence (transitions owned by `agent-supervisord`):

```text
STOPPED -> BOOT_SCANNING -> DEPENDENCY_VERIFYING -> RUNNING
                                       └----------> PAUSED(stale_dependency)
```

The verification scan is **read-only and cheap** — for each direct producer
dependency:

1. read the last committed `ConsumerCheckpoint`;
2. read the producer's canonical tip / retained accumulator;
3. verify the anchored `producer_step_hash` is present and canonical;
4. missing / stale / divergent / unresolved ⇒ `PAUSED(stale_dependency)`
   with the `StaleDependency` record (§2) as the pause reason;
5. otherwise ⇒ RUNNING.

A paused agent resumes only through explicit recovery (re-anchor, rewind
fold, or operator action) — never by timeout. This closes the "cluster wakes
up and sprints into corrupt history" failure mode.

## 7. Topology epochs

Every dependency artifact (`DependencyRegistration`, `ConsumerCheckpoint`,
`RewindEvent`, `StaleDependency`) carries the **topology epoch** that
authorized the edge. The epoch is bumped on **any change to the
state-dependency subgraph** (agent added/removed, edge added/removed/rekinded)
and the authorizing graph for each epoch is retained (an arena-anchored
artifact referenced from the eventd log), so the audit question — *"was this
dependency legal under the topology that existed when it was created?"* —
remains answerable after arbitrary graph evolution. Cross-epoch anchors are
not implicitly valid: a consumer resuming under a newer epoch re-verifies (§6)
against the edge set of the **current** epoch.

## 8. Implementation order

| Order | Component | Why this position |
|-------|-----------|-------------------|
| 1 | `DependencyRegistration` WAL frame | core causal anchor |
| 2 | `RewindEvent` schema | recovery signal |
| 3 | `stale_dependency` supervisor pause state | prevent bad runtime transitions |
| 4 | O(1) dependency lookup index | makes rewind matching practical (AOT index, 0013 Pass 3) |
| 5 | DAG validation compiler pass | prevents cascading deadlock (Stage-0 shipped for `workflow`) |
| 6 | Dependency-aware GC floor | prevents history loss |
| 7 | Cold-start verifier | makes restart semantics safe |
| 8 | Zero-copy scan path (Cap'n-Proto-style layout) | optimize **after** correctness |

## Security considerations

- **Tamper evidence.** All three artifacts are eventd entries; a forged or
  reordered registration breaks the hash chain. Verification on boot is
  mandatory (eventd design: broken chain = hard error).
- **Authority.** Who may register a dependency on a producer, emit a rewind,
  or evict a dead consumer from the GC floor is a `preceptord` policy
  decision; none of these are open operations. Registration against a
  producer the consumer holds no capability for MUST be denied.
- **Denial of compaction.** A malicious or wedged consumer pinning
  `producer_gc_floor` is the resource-exhaustion vector; the §4.2 lease +
  explicit logged eviction is the mitigation. Eviction itself must be
  authorized (preceptord) and logged (eventd) — silent eviction would convert
  a liveness problem into an integrity problem.
- **Epoch forgery.** An artifact claiming a stale epoch to dodge current-graph
  validation MUST fail §6 re-verification; epochs are assigned by the
  supervision plane, never self-reported by agents.

## Open questions

- Lease duration for dead-consumer eviction (§4.2) — fixed, per-edge, or
  budget-derived (#28)?
- Proof retention representation (§4.1-2): Merkle accumulator vs canonical
  segment footers — decide with eventd's compaction design (its "rotation
  without breaking the chain" open question).
- Cross-node anchors: how `DependencyRegistration` rides Litany Wire between
  hosts, and where the SHM-arena graft boundary (#16) falls back to
  serialized payloads.
- The zero-copy scan path (order 8): vendor a Cap'n-Proto-style layout or
  reuse the arena's position-independent encoding (#16 open Q1)?
- Does `RewindEvent` need consumer acknowledgement (two-phase rewind), or is
  cold-start re-verification (§6) sufficient for all recovery paths?
