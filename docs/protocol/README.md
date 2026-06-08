# HCP / Litany — protocol overview

**HCP** (Harness Control Protocol) is the IPC/wire protocol for agent↔harness↔tool communication in the Vaked runtime. **Litany** is its reference implementation: a wire format (**Litany Wire**), a frame model (**Votive Frames**), a schema/IDL language (`.hcplang`), a binary encoding (`hcpbin`), and a set of daemons + tools.

This is a **stub**. The normative spec lives in the RFC series under [`/protocol/rfcs`](../../protocol/rfcs/); see [`0001-hcp.md`](../../protocol/rfcs/0001-hcp.md).

## Vocabulary

| Term | Meaning |
|------|---------|
| HCP | The protocol itself (HARNESS/IPC layer) |
| Litany Wire | The on-the-wire byte protocol |
| Votive Frames | The framing/message model carried over Litany Wire |
| `.hcplang` | Schema / interface definition language for HCP messages |
| `hcpbin` | Canonical binary encoding |

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
