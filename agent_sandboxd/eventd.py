"""agent_sandboxd.eventd — audit integration.

Every spawn, kill, and filesystem access violation is appended as an audit
event to the eventd hash chain **before** the action is taken
(write-ahead log discipline). This is the "eventd (immutable)" seam for the
process + filesystem membrane:

  - ``spawn_event`` — written immediately before exec (or refusal) of a new
    child process inside the sandbox boundary.
  - ``kill_event`` — written immediately before sending a signal to terminate
    a supervised process.
  - ``access_event`` — written when a filesystem access decision is made
    (allow or deny); DENY events constitute access violations.

Payloads are deterministic (no wall-clock in the chained body) — a wall-time
sidecar field ``_ts_ns`` is added but NOT included in the hash payload (same
discipline as agent-guardd: wall time never in the chain). Replayed runs hash
identically; the verify leg can prove the boundary held.

The eventd oracle owns canonical hashing (``eventd.EventLog``); sandboxd never
computes its own hashes — the same "no canonical hashing in the daemon" rule
the supervisord design enforces.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import time

from eventd import EventLog


# --------------------------------------------------------------------------- #
# Payload builders                                                              #
# --------------------------------------------------------------------------- #

def spawn_event(
    agent_id: str,
    command: list,
    filesystem_policy: str,
    process_policy: str,
    capability_token: "str | None",
    action: str,
    reason: str,
    *,
    seq: "int | None" = None,
) -> dict:
    """The ``Event.Spawn`` payload for one spawn attempt.

    ``action`` is ``"allow"`` or ``"deny"``; ``reason`` explains the decision.
    Written before the exec (or before the refusal is returned to the caller).
    """
    payload: dict = {
        "kind": "sandbox_spawn",
        "v": 1,
        "agent_id": agent_id,
        "command": command,
        "filesystem_policy": filesystem_policy,
        "process_policy": process_policy,
        "action": action,      # "allow" | "deny"
        "reason": reason,
    }
    if capability_token is not None:
        payload["capability_token"] = capability_token
    if seq is not None:
        payload["seq"] = seq
    return payload


def kill_event(
    agent_id: str,
    pid: int,
    signal: int,
    reason: str,
    *,
    seq: "int | None" = None,
) -> dict:
    """The ``Event.Kill`` payload for a supervised process termination."""
    payload: dict = {
        "kind": "sandbox_kill",
        "v": 1,
        "agent_id": agent_id,
        "pid": pid,
        "signal": signal,
        "reason": reason,
    }
    if seq is not None:
        payload["seq"] = seq
    return payload


def access_event(
    agent_id: str,
    path: str,
    mode: str,
    action: str,
    reason: str,
    *,
    seq: "int | None" = None,
) -> dict:
    """The ``Event.Access`` payload for one filesystem access decision.

    ``mode`` is ``"read"`` or ``"write"``; ``action`` is ``"allow"`` or
    ``"deny"``. A ``"deny"`` action with ``mode="write"`` is an access
    violation — the filesystem membrane enforcement point.
    """
    payload: dict = {
        "kind": "sandbox_fs_access",
        "v": 1,
        "agent_id": agent_id,
        "path": path,
        "mode": mode,
        "action": action,      # "allow" | "deny"
        "reason": reason,
    }
    if seq is not None:
        payload["seq"] = seq
    return payload


# --------------------------------------------------------------------------- #
# Chain writer                                                                  #
# --------------------------------------------------------------------------- #

def testify(log_path: str, payload: dict) -> dict:
    """Append one audit payload to the eventd log at ``log_path``.

    Single-writer; fsync; boot-verify on open. Returns the chained entry dict.
    The payload is the exact body committed to the hash chain (no wall-time
    in the hash — the eventd oracle owns the bytes).
    """
    with EventLog(log_path, writer=True) as log:
        return log.append(payload)
