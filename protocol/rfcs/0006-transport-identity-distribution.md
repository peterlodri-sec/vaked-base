# RFC 0006 — Transport Identity & Distribution (the inter-host fabric)

- **Status:** Draft
- **Created:** 2026-06-13
- **Track:** Protocol

## Abstract

RFCs 0001–0003 define *what* an HCP message is and how its bytes are framed on
a single connection (Litany Wire). This RFC defines the **inter-host fabric** —
how frames and event notifications travel *between* hosts in a multi-node
agentfield: **who a peer is** (SPIFFE/SPIRE transport identity) and **how
broadcasts fan out** (NATS subject distribution). It composes RFCs 0004 (state
dependency) and 0005 (control), adding two layers beneath them and **changing
neither's source of truth**: the per-runtime hash-chained `eventd` log remains
the single authority; this fabric carries identity-proven point-to-point frames
and best-effort notifications + verifiable proofs, never a competing event
store. Triaged in [0016](../../docs/language/0016-substrate-candidates.md)
(slot, issue #52).

## Terminology

| Term | Definition |
|------|------------|
| Trust domain | A SPIFFE trust root scoping one fleet's identities (e.g. `spiffe://agentfield.example`). |
| SVID | A SPIFFE Verifiable Identity Document — the short-lived X.509 cert SPIRE issues to a workload. |
| SPIFFE ID | The identity URI inside an SVID, e.g. `spiffe://agentfield.example/runtime/agent-field/agent/coder`. |
| Workload API | The local SPIRE-agent socket a workload calls to fetch/rotate its SVID — no secrets on disk. |
| Subject | A NATS publish/subscribe address, e.g. `agent.<id>.rewind`; supports `*`/`>` wildcards. |
| Fabric | The combination of SPIFFE identity + NATS distribution defined here. |
| Notification | A best-effort fabric message announcing that something happened (its proof/truth lives elsewhere). |

Shared vocabulary lives in [`docs/protocol/README.md`](../../docs/protocol/README.md);
the dependency machinery is [RFC 0004](./0004-multi-agent-state-dependency.md),
control is [RFC 0005](./0005-control-frames.md), the wire is
[RFC 0003](./0003-litany-wire.md).

## 1. Transport identity (SPIFFE/SPIRE)

### 1.1 Every agent is a workload with an SVID

Each agent (and each daemon) obtains an SVID from a local SPIRE agent via the
Workload API — no long-lived key on disk, automatic rotation. The SPIFFE ID
encodes the agent's place in the topology:
`spiffe://<trust-domain>/runtime/<runtime>/agent/<name>`.

### 1.2 Identity is checked before the frame is parsed

A cross-host HCP connection is mutually authenticated with SVIDs. A
`DependencyRegistration` (RFC 0004 §2) arriving from consumer B to producer A's
host is **validated at the TLS layer before a byte of the frame is parsed**:
the peer's SPIFFE ID must match the `consumer` the frame claims. This is
defense in depth, **not** a replacement for `preceptord` authority (RFC 0005
security model) — preceptord still decides *what* the proven principal may do.
The `control_action.actor` field (RFC 0005 §3), taken on faith today, becomes
the verified SPIFFE ID.

### 1.3 SPIFFE ID is the canonical AgentId

This answers RFC 0005's open question — *"name→AgentId resolution is the
supervisor's roster (oraclefd surface)"*: the SPIFFE ID **is** the canonical
AgentId, and `oraclefd` resolves declared names ⇄ SPIFFE IDs. The RFC 0004
`uuid` agent identifiers are the local handle; the SPIFFE ID is the network
identity they bind to in a multi-host fleet.

### 1.4 Identity vs topology epoch

SVID rotation (lifetime, on the order of an hour) and topology epochs (RFC 0004
§7, bumped on graph change) are **orthogonal**: identity is per agent instance,
the epoch is per dependency graph. A frame carries both — its SVID proves the
sender, its `topology_epoch` fences which graph authorized the edge. Rotation
mid-epoch is normal and must not invalidate in-flight epoch-valid frames.

## 2. Distribution (NATS)

### 2.1 Subject taxonomy

The subject token for an agent is its **`uuid` handle** (RFC 0004), **not** the
SPIFFE URI: NATS treats `.` as the subject-hierarchy separator and `*` as a
*single-token* wildcard, so a dotted `spiffe://…/agent/coder` ID would expand
into many tokens and defeat `agent.*.rewind`. The dot-free uuid is exactly one
token; the SPIFFE ID authenticates the connection (§1.2), the uuid keys the
subject.

| Subject | Carries | Pattern |
|---------|---------|---------|
| `agent.<uuid>.rewind` | a `RewindEvent` notification (RFC 0004 §3.3) | publish per rewind |
| `agent.<uuid>.step` | step-progress notifications (optional, for surfaces) | publish per step |

A supervisor subscribes `agent.*.rewind` — **wildcard interest gives
near-constant matching with no per-peer cluster bookkeeping**: a cross-host
consumer learns a producer rewound without polling the producer's log.

**The fabric carries events and proofs only — never privileged request/response.**
Control frames (RFC 0005) and `DependencyRegistration` (RFC 0004) are
identity-proven, acknowledged point-to-point frames: they ride mTLS Litany
connections (§1), *not* NATS. This is the §3 boundary made concrete in the
transport split — nothing that mutates state travels the best-effort fabric.

### 2.2 Retained accumulators over JetStream

RFC 0004 §4.1's retained proofs (snapshot / Merkle accumulator / segment
footer) are transported across hosts via JetStream KV / object store — so a
remote consumer can fetch the proof a producer's GC floor references without a
direct connection to the producer's `reliquaryd`.

## 3. The boundary (normative)

> The fabric distributes **notifications and proofs only**. The per-runtime
> hash-chained `eventd` log is the single source of truth (RFC 0004
> single-writer).

Concretely: a node receiving an `agent.<id>.rewind` notification MUST NOT act
on the notification alone. It re-verifies against its own folded state
(`eventd state`, the cold-start verifier, RFC 0004 §6) and the fetched proof
(§2.2); the notification is only a *prompt to re-verify*, never evidence. A lost
or duplicated NATS message can therefore never corrupt state — at worst it
delays or redundantly triggers a re-verification that is idempotent. This is
what makes NATS safe to use here despite at-most/at-least-once delivery: it is
never load-bearing for correctness. Privileged effects (control, dependency
registration) never traverse the fabric at all — they are identity-proven,
acknowledged Litany frames (§2.1), so "act on a fabric message alone" cannot
arise for them.

## Security considerations

- **mTLS before parse** (§1.2) shrinks the attack surface: an unidentified peer
  never reaches the frame parser. Combined with preceptord authority, identity
  and authorization are separate gates (a stolen-then-rotated SVID closes
  fast; preceptord limits the blast radius in between).
- **Trust-domain boundary** is the fleet boundary; cross-domain federation
  (ZKP-proven rewinds across orgs, 0016) is explicitly out of scope here.
- **NATS subject authorization** maps onto the `mcp`/capability model: an
  agent may publish only `agent.<own-id>.*` and subscribe per its granted
  interest — a per-subject permission set issued with the SVID.
- **Notifications are not evidence** (§3): the fabric cannot be used to forge a
  rewind or a dependency state, because every consumer re-verifies against the
  tamper-evident log + proof. This is the single most important security
  property of the design.

## Open questions

1. **RFC 0003 integration**: is NATS a *Litany Wire transport* (frames tunnel
   over NATS) or a *parallel* notification plane beside point-to-point Litany
   connections? Lean: parallel — Litany for request/response identity-proven
   frames, NATS for event fan-out — but a unified "Litany-over-NATS" transport
   is worth evaluating.
2. **SPIRE deployment**: one SPIRE server per fleet with per-host agents
   (standard) vs nested trust domains per runtime.
3. **Subject taxonomy vs Votive Frame classes**: finalize the mapping
   (request/response ⇄ request-reply; event ⇄ subject; control ⇄ ?).
4. **CCN/NDN** (0016) is the further generalization — content-named anchors
   (`/agent/<id>/step/<hash>`) where a rewind invalidates the name in routing
   itself; revisit if the subject model outgrows point-to-point fan-out.
