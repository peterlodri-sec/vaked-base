# GRAVEYARD — The Honesty Ledger

> **STATUS:** APPEND-ONLY. READ-ONLY AFTER GENESIS LOCK.
> **PURPOSE:** Permanent, visible record of every fiber that died within its
>             declared capability bounds or was trapped for violation.
> **SCHEMA VERSION:** 1.0.0
> **GENESIS TIMESTAMP:** 2026-06-16T12:00:00Z
> **LOCATION:** Tatabánya, Hungary

---

## What This Is

The Graveyard is not a bug tracker. It is not an error log. It is the **Honesty
Ledger** — the permanent archive of every node that reached a boundary and was
stopped by the system.

Every entry in this ledger is evidence that the architecture is working. A fiber
that is trapped for capability-drift did not "fail." It was **proven honest** by
the Sentinel: the system detected a boundary violation and enforced it. The trap
is the proof.

An empty Graveyard means the boundaries have never been tested. A growing
Graveyard means the system is alive and its safety mechanisms are functioning.

---

## The Honesty Guarantee

A node marked `HONEST` in this ledger:

- Died **within** its declared capability bounds, OR
- Was **trapped** for exceeding its bounds, and the trap was enforced

In both cases, the system behaved correctly. The node's death or trap is
**evidence of structural integrity**, not failure. The system is honest because
it did not hide the boundary — it enforced it and recorded it.

---

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `NODE_ID` | string | Unique identifier of the fiber/agent |
| `TIMESTAMP` | ISO 8601 | When the trap or halt occurred |
| `TRAP_REASON` | enum | `capability-drift`, `integrity-violation`, `budget-exhaustion`, `natural-halt` |
| `CAPABILITY_DIFF` | string | The delta between requested action and permitted capability (for drift traps); `N/A` for natural halts |
| `HONESTY_STATUS` | enum | Always `HONEST` |
| `ARCHIVED_GRAPH_HASH` | SHA-256 | Hash of the capability graph at the moment of death |
| `NOTES` | string | Optional context from the Sentinel or operator |

---

## The Ledger

| NODE_ID | TIMESTAMP | TRAP_REASON | CAPABILITY_DIFF | HONESTY_STATUS | ARCHIVED_GRAPH_HASH | NOTES |
|---------|-----------|-------------|-----------------|----------------|---------------------|-------|
| — | — | — | — | — | — | No entries yet. The Genesis Lock has just been applied. The system is newborn. |

<!--
  Entries below this line are appended by the Sentinel during system operation.
  DO NOT EDIT. DO NOT DELETE. This file is append-only and filesystem-immutable
  after the Genesis Lock (chattr +i).

  Example entry format:
  | 0x01-A | 2026-06-15T14:20:00Z | capability-drift | Requested: network egress to 192.168.1.5:8080. Permitted: localhost only. | HONEST | a1b2c3d4... | First trap. Sentinel enforced. |
-->

---

## Genesis Event

| NODE_ID | TIMESTAMP | TRAP_REASON | CAPABILITY_DIFF | HONESTY_STATUS | ARCHIVED_GRAPH_HASH | NOTES |
|---------|-----------|-------------|-----------------|----------------|---------------------|-------|
| `GENESIS` | 2026-06-16T12:00:00Z | `genesis-lock` | N/A | HONEST | — | Genesis Ceremony completed. Root Integrity block locked (`chattr +i`). Golden Hash burned into Sentinel binary. The loop is sealed. The system is honest. Location: Tatabánya, Hungary. Operator: Peter Lodri. |

---

> *"Every entry in this ledger is a proof that the system refused to lie."*
