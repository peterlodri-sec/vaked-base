"""agent_memoryd.store — folded-state memory store.

State model (from the 0014/memoryd design): each mined entry is an eventd
event; recall state is the **fold** over the log, partitioned by ``scope``
(``"session"`` / ``"agent"`` / ``"runtime"``). The store is the materialised
cache of that fold.

Storage layout:
  * **In-memory dict** keyed by ``content_hash`` (sha256 of canonical content).
  * **Optional persistence** to a JSON file — the file is written atomically
    (tmp → replace) on every mutation, matching eventd's crash-safe pattern.

Entry format (the payload riding the eventd chain)::

    {
      "kind":             "memory_entry",
      "v":                1,
      "key":              str,          # human-readable label
      "content_hash":     hex-sha256,   # content-address (the store key)
      "content":          str,          # the mined entry body
      "capability_domain": "mem",
      "agent_id":         str,
      "scope":            "session"|"agent"|"runtime",
      "epoch":            int,          # logical epoch (monotone)
      "created_at":       ISO-8601 UTC  # wall-time sidecar (NOT hashed)
    }

``content_hash`` is sha256(content.encode("utf-8")).hexdigest().
The ``created_at`` field rides the payload but carries wall-clock time;
it is NOT used in hashing (matches eventd's discipline that wall-time is a
non-hashed sidecar). The chain provides the ordering.

Retention (from the design): handled by tombstone events (``memory_tombstone``
payloads in the eventd log) — the fold drops an entry when it sees a tombstone.
That keeps the materialised cache cheap and rewind exact.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Iterator


ENTRY_KIND = "memory_entry"
TOMBSTONE_KIND = "memory_tombstone"
ENTRY_VERSION = 1


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class MemoryEntry:
    """One folded-state recall entry.

    ``content_hash`` is the content-address and the primary store key.
    ``epoch`` is a monotonically increasing counter that advances each time
    the store is mutated (equivalent to a lamport clock for ordering within
    the fold).
    """
    key: str
    content_hash: str
    content: str
    capability_domain: str
    agent_id: str
    scope: str
    epoch: int
    created_at: str

    def to_payload(self) -> dict:
        """Serialise to the eventd payload format (kind + v header)."""
        return {
            "kind": ENTRY_KIND,
            "v": ENTRY_VERSION,
            "key": self.key,
            "content_hash": self.content_hash,
            "content": self.content,
            "capability_domain": self.capability_domain,
            "agent_id": self.agent_id,
            "scope": self.scope,
            "epoch": self.epoch,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            key=d["key"],
            content_hash=d["content_hash"],
            content=d["content"],
            capability_domain=d.get("capability_domain", "mem"),
            agent_id=d["agent_id"],
            scope=d.get("scope", "agent"),
            epoch=d.get("epoch", 0),
            created_at=d.get("created_at", ""),
        )

    @classmethod
    def from_payload(cls, p: dict) -> "MemoryEntry":
        """Re-inflate from an eventd chain payload (strips kind/v header)."""
        return cls.from_dict(p)


def _tombstone_payload(content_hash: str, agent_id: str, reason: str) -> dict:
    """The eventd payload for a retention tombstone / explicit forget."""
    return {
        "kind": TOMBSTONE_KIND,
        "v": ENTRY_VERSION,
        "content_hash": content_hash,
        "agent_id": agent_id,
        "reason": reason,
        "tombstoned_at": _utcnow(),
    }


class MemoryStore:
    """In-memory dict of :class:`MemoryEntry` keyed by ``content_hash``.

    Optionally persisted to a JSON file (``persist_path``).  The file is
    written atomically on every mutation (tmp → os.replace) so a crash
    never leaves a half-written file.

    Thread-safety: the store is NOT thread-safe (single-writer daemon model
    mirrors eventd's design — the control plane owns the writer).
    """

    def __init__(self, persist_path: "str | None" = None):
        self._entries: dict[str, MemoryEntry] = {}
        self._epoch: int = 0
        self._persist_path = persist_path
        if persist_path and os.path.exists(persist_path):
            self._load_persist()

    # ---------------------------------------------------------------------- #
    # Epoch management
    # ---------------------------------------------------------------------- #

    def _next_epoch(self) -> int:
        self._epoch += 1
        return self._epoch

    # ---------------------------------------------------------------------- #
    # Store (write path)
    # ---------------------------------------------------------------------- #

    def store(self, key: str, content: str, agent_id: str,
              scope: str = "agent") -> MemoryEntry:
        """Store a new entry (or update an existing one by content_hash).

        Returns the :class:`MemoryEntry` with the assigned ``content_hash``
        and ``epoch``.  The caller is responsible for write-ahead logging to
        eventd BEFORE calling this method (the daemon.py layer does that).
        """
        if scope not in ("session", "agent", "runtime"):
            raise ValueError("unknown scope %r; "
                             "expected session/agent/runtime" % scope)
        content_hash = _sha256(content)
        entry = MemoryEntry(
            key=key,
            content_hash=content_hash,
            content=content,
            capability_domain="mem",
            agent_id=agent_id,
            scope=scope,
            epoch=self._next_epoch(),
            created_at=_utcnow(),
        )
        self._entries[content_hash] = entry
        self._persist()
        return entry

    # ---------------------------------------------------------------------- #
    # Recall (read path / fold)
    # ---------------------------------------------------------------------- #

    def recall(self, *,
               agent_id: "str | None" = None,
               scope: "str | None" = None,
               key_prefix: "str | None" = None,
               token_agent_id: str,
               token_level: str) -> list[MemoryEntry]:
        """Return entries visible to the token, filtered by optional criteria.

        The capability visibility check is applied via the
        :mod:`agent_memoryd.capability` module's scope_visible rule; the
        caller must have already validated the token level (>=recall) before
        calling this.  This method does the ownership/scope filter.
        """
        from .capability import CapabilityToken, CapLevel
        token = CapabilityToken(
            agent_id=token_agent_id,
            level=CapLevel.from_str(token_level),
            scope=scope,
        )
        results: list[MemoryEntry] = []
        for entry in self._entries.values():
            if not token.scope_visible(entry.scope, entry.agent_id):
                continue
            if agent_id is not None and entry.agent_id != agent_id:
                continue
            if scope is not None and entry.scope != scope:
                continue
            if key_prefix is not None and not entry.key.startswith(key_prefix):
                continue
            results.append(entry)
        # order by epoch (fold order)
        results.sort(key=lambda e: e.epoch)
        return results

    def get(self, content_hash: str) -> "MemoryEntry | None":
        """Fetch a single entry by content-address."""
        return self._entries.get(content_hash)

    # ---------------------------------------------------------------------- #
    # Forget (delete / tombstone path)
    # ---------------------------------------------------------------------- #

    def forget(self, content_hash: str, agent_id: str) -> "MemoryEntry | None":
        """Remove an entry by content-address.  Returns the removed entry (or
        None if it was not found).  Write-ahead must be done by the caller
        (daemon.py) before invoking this method.
        """
        entry = self._entries.pop(content_hash, None)
        if entry is not None:
            self._persist()
        return entry

    # ---------------------------------------------------------------------- #
    # Fold from eventd log (replay = fold)
    # ---------------------------------------------------------------------- #

    def fold_from_entries(self, entries: list[dict]) -> None:
        """Rebuild the store state by folding over a list of eventd chain
        entries (each with a ``payload`` key).  Applies memory_entry events
        and memory_tombstone events in sequence order.  Used on startup to
        rebuild the materialised cache from the durable eventd log.
        """
        self._entries.clear()
        self._epoch = 0
        for chain_entry in entries:
            payload = chain_entry.get("payload", {})
            kind = payload.get("kind")
            if kind == ENTRY_KIND:
                try:
                    e = MemoryEntry.from_payload(payload)
                    self._entries[e.content_hash] = e
                    if e.epoch > self._epoch:
                        self._epoch = e.epoch
                except (KeyError, TypeError):
                    pass   # skip malformed; fold is best-effort
            elif kind == TOMBSTONE_KIND:
                ch = payload.get("content_hash", "")
                self._entries.pop(ch, None)

    # ---------------------------------------------------------------------- #
    # Snapshot helpers
    # ---------------------------------------------------------------------- #

    def snapshot(self) -> list[dict]:
        """Export all entries as a list of dicts (for catalog.jsonl emit)."""
        return [e.to_dict() for e in
                sorted(self._entries.values(), key=lambda e: e.epoch)]

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[MemoryEntry]:
        return iter(self._entries.values())

    # ---------------------------------------------------------------------- #
    # Persistence
    # ---------------------------------------------------------------------- #

    def _persist(self) -> None:
        if not self._persist_path:
            return
        os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
        tmp = self._persist_path + ".tmp"
        data = {
            "epoch": self._epoch,
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._persist_path)

    def _load_persist(self) -> None:
        with open(self._persist_path, encoding="utf-8") as f:
            data = json.load(f)
        self._epoch = data.get("epoch", 0)
        for d in data.get("entries", []):
            try:
                e = MemoryEntry.from_dict(d)
                self._entries[e.content_hash] = e
            except (KeyError, TypeError):
                pass   # skip malformed entries on load


def make_entry_payload(key: str, content: str, agent_id: str,
                       scope: str, epoch: int,
                       content_hash: "str | None" = None) -> dict:
    """Build an eventd-ready ``memory_entry`` payload without a store instance.

    Useful in tests and for the write-ahead path where the content_hash must
    be computed before the entry is committed to the store.
    """
    ch = content_hash or _sha256(content)
    return {
        "kind": ENTRY_KIND,
        "v": ENTRY_VERSION,
        "key": key,
        "content_hash": ch,
        "content": content,
        "capability_domain": "mem",
        "agent_id": agent_id,
        "scope": scope,
        "epoch": epoch,
        "created_at": _utcnow(),
    }
