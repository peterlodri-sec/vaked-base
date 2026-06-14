"""dogfood.wal — the kernel's write-ahead log, built on the real eventd daemon.

Rather than reimplement a third hash-chain (ralph has one inline, eventd is the
canonical one), the dogfood kernel records transitions into ``eventd.EventLog``.
This is truer dogfood: the verification kernel's audit spine *is* the production
append-only daemon. Boot-time tamper detection, single-writer discipline, and
the replay-fold all come from eventd unchanged.

We import eventd from the repo root (this file lives at tools/dogfood/wal.py).
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from eventd import EventLog, TamperError, repair_truncate_tail  # noqa: E402

__all__ = ["EventLog", "TamperError", "repair_truncate_tail", "append_transition",
           "replay_summary"]


def append_transition(log: EventLog, payload: dict) -> dict:
    """Append one transition payload; returns the chained entry (with seq/hash)."""
    return log.append(payload)


def _fold(state: dict, entry: dict) -> dict:
    """Reduce the verified log to a summary: count transitions, track the last
    accepted state hash, and remember the tail. Pure — same log ⇒ same summary.
    """
    payload = entry.get("payload", {})
    if payload.get("kind") == "dogfood_transition":
        state = dict(state)
        state["transitions"] = state.get("transitions", 0) + 1
        state["last_state_hash"] = payload.get("state_hash_after")
        state["last_patch_hash"] = payload.get("patch_hash")
    return state


def replay_summary(log: EventLog) -> dict:
    """Fold the (already chain-verified) log into a deterministic summary."""
    return log.replay(_fold, {"transitions": 0,
                              "last_state_hash": None,
                              "last_patch_hash": None})
