# HCP / Litany — protocol overview

**HCP** (Harness Control Protocol) is the IPC/wire protocol for agent↔harness↔tool communication in the Vaked runtime. **Litany** is its reference implementation: a wire format (**Litany Wire**), a frame model (**Votive Frames**), a schema/IDL language (`.hcplang`), a binary encoding (`hcpbin`), and a set of daemons + tools.

This is a **stub**. The normative spec lives in the RFC series under [`/protocol/rfcs`](../../protocol/rfcs/); see [`0001-hcp.md`](../../protocol/rfcs/0001-hcp.md).

> **Adjacent register-language RFC:** [`0009-ail-register-language.md`](../../protocol/rfcs/0009-ail-register-language.md) defines **AIL-0** (Agentic Intermediate Language) — a register notation for agent reasoning / tool-intent / artifact frames. It is *adjacent to* HCP (it is the grammar for the text conventions that **ARP**, [issue #202](https://github.com/peterlodri-sec/vaked-base/issues/202), carries), not an HCP wire concern: it adds no Votive Frame, wire format, or daemon. (The 0008 slot is in-flight on a separate branch — crypto-seal domain — so it is intentionally absent from `protocol/rfcs/` here.)

## Vocabulary

| Term | Meaning |
|------|---------|
| HCP | The protocol itself (HARNESS/IPC layer) |
| Litany Wire | The on-the-wire byte protocol |
| Votive Frames | The framing/message model carried over Litany Wire |
| `.hcplang` | Schema / interface definition language for HCP messages |
| `hcpbin` | Canonical binary encoding |

### Control frames ([RFC 0005](../../protocol/rfcs/0005-control-frames.md))

| Term | Meaning |
|------|---------|
| Control-plane frame | Votive `request` frame addressed to the supervision plane: pause / resume / slow / step / rewind ("control plane" names the destination, not the frame class) |
| Scope | `runtime` (the whole OTP tree) or `agent` (one supervisor child); case 0 `unspecified` is refused |
| Target | Declared name (child id / runtime name), fenced by the current topology epoch |
| `ControlAck` | The response: applied, or refused with a typed `ControlRefusal` reason |
| `control_action` | The eventd payload kind recording every APPLIED control frame (write-ahead, before effect; carries corr + actor) |
| Step | One-shot tick while paused; stays paused afterwards |

### Inter-host fabric ([RFC 0006](../../protocol/rfcs/0006-transport-identity-distribution.md))

| Term | Meaning |
|------|---------|
| SVID / SPIFFE ID | Per-agent transport identity; the SPIFFE ID is the canonical AgentId (resolves the RFC 0005 name→AgentId question via oraclefd) |
| Trust domain | The SPIFFE root scoping one fleet's identities |
| Subject | A NATS pub/sub address (`agent.<uuid>.rewind`; the dot-free uuid handle, not the dotted SPIFFE URI); wildcard interest = near-constant fan-out matching, no per-peer bookkeeping |
| Fabric boundary | NATS carries notifications + proofs only; the hash-chained log stays the single source of truth |

### State dependency ([RFC 0004](../../protocol/rfcs/0004-multi-agent-state-dependency.md))

| Term | Meaning |
|------|---------|
| `DependencyRegistration` | Write-ahead control frame: a consumer's causal anchor on a producer step, logged before consumption |
| `ConsumerCheckpoint` | Durable acknowledgement of how far a producer dependency is folded into the consumer's committed state |
| `RewindEvent` | Event frame voiding anchors above a producer's rewind point |
| Topology epoch | Version of the state-dependency graph carried by every dependency artifact |
| GC floor | Lowest producer step pinned by any downstream checkpoint — compaction is legal only strictly below it |
| Edge kind | `state_dependency` (must be a DAG) vs `observation` / `control_signal` / `metrics` (cycles tolerated) |
| `stale_dependency` | Paused lifecycle state entered when cold-start anchor verification fails |

### Workflow orchestration lowering ([RFC 0008](../../protocol/rfcs/0008-workflow-orchestration-lowering.md))

| Term | Meaning |
|------|---------|
| Workflow run | One end-to-end traversal of a lowered Vaked `workflow`, instantiated by `agent-supervisord` under a single topology epoch (the DAG is static; a run executes it once) |
| Step activation | Admitting a step to `RUNNING` after its inbound `DependencyRegistration`s are logged and cold-start anchor verification passes; otherwise it parks `PAUSED(stale_dependency)` |
| Lowering contract | The normative construct→frame correspondence (`workflow`/`mesh`/`budget`/`runclass` → RFC 0004/0005 frames) |
| `DeadlineExpiry` | *Proposed* event frame marking a step's `budget.wallClock` exhausted — the missing wire dual of a declared wall-clock budget (today realized as a supervisor `PauseControl`) |

### Post-quantum & image-as-code ([RFC 0007](../../protocol/rfcs/0007-post-quantum-litany-sealed-image.md))

| Term | Meaning |
|------|---------|
| Hybrid handshake | X25519 + ML-KEM-768 key exchange baked into the wire; confidential if either half holds (defeats harvest-now-decrypt-later) |
| PQC SVID | A SPIFFE SVID signed hybrid Ed25519+ML-DSA (migration) or ML-DSA-65 (PQC-only); root signed SLH-DSA |
| Sealed image | Content-addressed materialized artifact (NixOS closure / OCI / unikernel), deny-by-default by construction |
| Image-as-code | The only mutation path to a running system is a re-derived, re-signed code change — no out-of-band mutation |
| Votive seal | A PQC (ML-DSA) signature over a sealed image's measurement + provenance, recorded to `eventd` — the image's analogue of an SVID |
| Attestation quote | Load-time evidence (ML-DSA over `{measurement, nonce, epoch}`) that a measured image matches its signed provenance; replaces "eBPF testifies" for sealed unikernels |

### Agent register protocol ([RFC 0009](../../protocol/rfcs/0009-arp.md))

ARP adds behavioral signals + per-model adapters layered on [AI-lish V1](../ailish/2026-06-14-ailish-v1-rfc.md) (the agent execution-graph IR + `ailish/` crate). It is in-context text only — no wire — carries no authority, and composes one level below HCP.

| Term | Meaning |
|------|---------|
| ARP | Behavioral primitives + model adapters for AI-lish (this RFC) |
| Stride / Tension / Valence / Branch | `[STRIDE: a → b]` (progress arc), `[T:N]` (goal-distance 0..100), `[+]/[-]/[!]` (result polarity), `[BRANCH: a \| b; condition: X]` (fork) |
| AI-lish V1 | The execution-graph grammar/IR ARP rides on (the `ailish/` crate + `docs/ailish/` RFC) |

## Daemons (proposed — roles to be fixed in RFCs)

| Daemon | Proposed role |
|--------|---------------|
| `chapterd` | Session/segment ("chapter") lifecycle over a connection |
| `preceptord` | Policy/authority plane — what a peer may request |
| `reliquaryd` | Durable artifact / relic store referenced by frames |
| `candled` | Liveness / presence / heartbeat (vigil) |
| `petitiond` | Request intake / ingress |
| `oraclefd` | Resolution / query oracle (names, capabilities, answers) |

## Tools

```text
litanyctl     control plane CLI
litanydump    inspect / decode captured frames
litanyfmt     format .hcplang sources
litanyreplay  replay captured Litany Wire logs
```

## Relationship to the runtime

HCP is how `mcp-brokerd` brokers tool calls, how `agent-supervisord` orchestrates, and how operator **surfaces** subscribe to `eventd`. The protocol is transport for the membranes; the [runtime daemons](../runtime/README.md) are the endpoints.
