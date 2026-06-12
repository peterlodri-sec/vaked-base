"""eventd.log — the daemon shape: single-writer append, fsync, boot verify.

Per the eventd design (docs/superpowers/specs/2026-06-12-eventd-design.md
§"Daemon shape"):

* one log per runtime instance (the path is a 0012 lowering output — pending);
* writers append under a single-writer discipline (advisory ``flock`` here;
  in the runtime, `agent-supervisord` owns the writer) — append-only,
  fsync-on-append for durability;
* readers map the log read-only and fold;
* **tamper check on boot is a hard error**: a broken chain raises
  ``TamperError`` before any entry is served — the audit spine must be intact.
"""
from __future__ import annotations

import fcntl
import json
import os
from functools import reduce

from .core import GENESIS_HASH, entry_line, make_entry, verify_chain


class TamperError(Exception):
    """The on-disk chain failed verification — the log must not be used."""


class WriterLockError(Exception):
    """A second writer tried to open the log (single-writer discipline)."""


def load_entries(path: str) -> list[dict]:
    """Read a JSONL log into entries (empty if the file is missing).

    A syntactically malformed line (crash torn-write, byte-level tamper) is
    the same broken audit spine as a hash mismatch and raises ``TamperError``
    through the same refusal path — never a raw ``JSONDecodeError``."""
    try:
        with open(path, encoding="utf-8") as f:
            entries = []
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise TamperError(
                        f"{path}:{n}: malformed log line — broken audit "
                        f"spine") from e
            return entries
    except FileNotFoundError:
        return []


class EventLog:
    """An open eventd log.

    ``EventLog(path)`` opens read-only; ``EventLog(path, writer=True)`` takes
    the single-writer lock and may ``append``. Opening ALWAYS verifies the
    chain (boot-time tamper check) unless ``verify=False`` is forced — which
    only ``litanydump``-style forensics should ever do.
    """

    def __init__(self, path: str, *, writer: bool = False, verify: bool = True):
        self.path = path
        self._entries = load_entries(path)
        if verify and not verify_chain(self._entries):
            raise TamperError(
                f"{path}: hash chain verification failed "
                f"({len(self._entries)} entries) — refusing to serve a "
                f"tampered audit spine")
        self._fh = None
        if writer:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8")
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                self._fh.close()
                self._fh = None
                raise WriterLockError(
                    f"{path}: another writer holds the log "
                    f"(single-writer discipline)") from e

    # -- read side -----------------------------------------------------------

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def tail_hash(self) -> str:
        return self._entries[-1]["hash"] if self._entries else GENESIS_HASH

    def replay(self, fold, init):
        """state = fold over the (verified) log — the design's state model."""
        return reduce(fold, self._entries, init)

    # -- write side ----------------------------------------------------------

    def append(self, payload: dict) -> dict:
        """Append one payload as the next chained entry; fsync before return."""
        if self._fh is None:
            raise WriterLockError(f"{self.path}: log opened read-only")
        entry = make_entry(self.tail_hash, len(self._entries), payload)
        self._fh.write(entry_line(entry))
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._entries.append(entry)
        return entry

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()   # releases the flock
            self._fh = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
