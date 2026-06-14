"""agent_memoryd.eventd — write-ahead log client (eventd integration).

Every store and forget operation write-ahead logs to eventd BEFORE the
operation is confirmed to the caller — the same discipline agent-guardd uses
(``evidence.testify`` → ``EventLog.append``).

Two modes:

1. **Local mode** (``log_path`` given): writes directly to the on-disk eventd
   JSONL file via ``eventd.EventLog``, exactly as agent-guardd does.  This is
   the primary mode for daemon-to-daemon colocation (memoryd + eventd on the
   same host, sharing the configured log path from ``gen/eventd.json``).

2. **HTTP mode** (``eventd_url`` given): POSTs the payload to the eventd HTTP
   API (future: when eventd ships an HTTP surface).  Falls back to local mode
   if the URL is unreachable and a fallback log path is configured.

The separation mirrors the design doc's "writer discipline: appends go through
eventd's single-writer (agent-supervisord owns it); memoryd is an eventd writer
for mem.append" — in this reference implementation the local EventLog is the
single-writer path.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Default log path (mirrors what gen/eventd.json + gen/memory/*.json agree on
# for the agentfield-swe example — see test_eventd.py lowering-wiring test).
_DEFAULT_LOG = "var/lib/memoryd/eventd/log.jsonl"


class EventdClient:
    """Write-ahead log client for memoryd.

    Wraps either the local ``eventd.EventLog`` API (recommended) or an HTTP
    endpoint.  The ``append`` method is the single entry point for all
    write-ahead appends.

    Usage::

        client = EventdClient(log_path="var/lib/memoryd/eventd/log.jsonl")
        entry = client.append(payload)   # blocks until fsynced
    """

    def __init__(self, log_path: "str | None" = None,
                 eventd_url: "str | None" = None):
        if not log_path and not eventd_url:
            log_path = _DEFAULT_LOG
        self._log_path = log_path
        self._eventd_url = eventd_url

    def append(self, payload: dict) -> dict:
        """Append ``payload`` to the eventd chain.  Returns the chain entry
        (``{seq, prev, payload, hash}``).  Raises on failure — the caller
        must NOT commit the store mutation if this raises.
        """
        if self._eventd_url:
            return self._http_append(payload)
        return self._local_append(payload)

    def _local_append(self, payload: dict) -> dict:
        """Append via the local EventLog (single-writer, fsync-on-append)."""
        from eventd import EventLog
        log_path = self._log_path or _DEFAULT_LOG
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with EventLog(log_path, writer=True) as log:
            return log.append(payload)

    def _http_append(self, payload: dict) -> dict:
        """POST ``payload`` to ``<eventd_url>/append``."""
        url = self._eventd_url.rstrip("/") + "/append"
        body = json.dumps({"payload": payload},
                          separators=(",", ":"), ensure_ascii=False).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError) as exc:
            # Fallback to local if configured
            if self._log_path:
                return self._local_append(payload)
            raise RuntimeError(
                "eventd HTTP append failed (%s) and no local fallback "
                "log path configured" % exc) from exc

    def verify(self) -> bool:
        """Verify the chain is intact (boot-time check).  Returns True if
        valid; raises ``eventd.TamperError`` on a broken chain."""
        if self._log_path:
            from eventd import EventLog
            log = EventLog(self._log_path)   # boot-verify is automatic
            return True
        return True   # HTTP mode: delegate to the remote daemon


def memory_store_payload(key: str, content: str, agent_id: str,
                         scope: str, epoch: int,
                         content_hash: str) -> dict:
    """Build a ``memory_entry`` eventd payload for write-ahead logging.

    This is the canonical payload shape that rides the hash chain.  It must
    be byte-deterministic (no wall-clock in hashed fields — ``created_at`` is
    present as a sidecar but is NOT part of the hash input; only the payload
    dict as a whole is hashed by eventd.core).
    """
    from .store import make_entry_payload
    return make_entry_payload(key, content, agent_id, scope, epoch,
                              content_hash=content_hash)


def memory_forget_payload(content_hash: str, agent_id: str,
                          reason: str = "explicit_forget") -> dict:
    """Build a ``memory_tombstone`` eventd payload for write-ahead logging."""
    from datetime import datetime, timezone
    return {
        "kind": "memory_tombstone",
        "v": 1,
        "content_hash": content_hash,
        "agent_id": agent_id,
        "reason": reason,
        "tombstoned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
