"""agent_guardd.evidence — the testimony leg: every egress decision becomes one
``Event.Ebpf`` payload appended to the eventd hash chain.

This is the "eBPF testifies" → "eventd (immutable)" seam. The membrane's
``observe = stream.ebpfEvents`` channel (in the .vaked source) is realized here:
agent-guardd is the writer, eventd is the tamper-evident spine. Payloads are
DETERMINISTIC (no wall-clock) so a replayed run hashes identically and the
:mod:`agent_guardd.verify` membrane-held check is reproducible — wall-time, when
wanted, rides a separate non-hashed sidecar, never the chained payload.
"""
from __future__ import annotations

from eventd import EventLog


def egress_event(membrane: str, principal: str, host: str, port: int,
                 action: str, reason: str, mechanism: str,
                 seq: "int | None" = None) -> dict:
    """The ``Event.Ebpf`` payload for one egress decision (the on-chain body)."""
    payload = {
        "kind": "ebpf_egress",        # the Event.Ebpf discriminant
        "v": 1,
        "membrane": membrane,
        "principal": principal,
        "syscall": "connect",
        "proto": "tcp",
        "daddr": host,
        "dport": port,
        "action": action,            # "allow" | "deny"
        "reason": reason,
        "mechanism": mechanism,      # "ebpf-cgroup" | "reference"
    }
    if seq is not None:
        payload["attempt"] = seq      # the attempt ordinal (not the chain seq)
    return payload


def testify(log_path: str, payload: dict) -> dict:
    """Append one testimony payload to the eventd log at ``log_path`` (single
    writer; fsync; boot-verify). Returns the chained entry."""
    with EventLog(log_path, writer=True) as log:
        return log.append(payload)
