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

from .core import (GENESIS_HASH, chain_hash, entry_line, make_entry,
                   verify_chain)

KIND_REPAIR = "log_repair"


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


def _longest_valid_prefix(path: str) -> list[dict]:
    """The longest contiguous, untampered chain prefix readable from ``path``
    (line by line from genesis), stopping at the first line that fails to
    parse or fails to chain. Everything after is the unverifiable suffix."""
    prefix = []
    prev = GENESIS_HASH
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:
        return []
    with f:
        for line in f:
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                break
            if (e.get("seq") != len(prefix) or e.get("prev") != prev
                    or e.get("hash") != chain_hash(prev, e.get("payload", {}))):
                break
            prefix.append(e)
            prev = e["hash"]
    return prefix


def repair_truncate_tail(path: str) -> dict:
    """#35 — the explicit operator crash-recovery command. A torn final write
    (or any unverifiable suffix) leaves a chain that boot-verify REFUSES;
    this drops everything after the longest valid prefix and appends a
    ``log_repair`` event recording the drop, so the chain is intact again and
    the truncation is itself in the audit trail. **A break anywhere truncates
    everything after it** — a hash chain cannot resume past a broken link, so
    a mid-log tamper (not just a torn tail) drops the whole unverifiable
    suffix; the ``dropped`` count + ``log_repair`` entry make the loss
    explicit. The rewrite is crash-atomic (temp file → fsync → ``os.replace``
    → dir fsync), so a crash mid-repair never destroys the verified prefix.

    Takes the single-writer lock (it mutates the file). Returns
    ``{"repaired": bool, "dropped": int, "tail_seq": int|None}``. ``repaired``
    is False (a no-op) when the chain is already intact. NOT daemon-automatic:
    a truncated tail stays a hard error until an operator runs this."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fh = open(path, "a", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        fh.close()
        raise WriterLockError(
            f"{path}: another writer holds the log "
            f"(single-writer discipline)") from e
    try:
        prefix = _longest_valid_prefix(path)
        raw = [ln for ln in open(path, encoding="utf-8") if ln.strip()]
        dropped = len(raw) - len(prefix)
        if dropped <= 0:
            return {"repaired": False, "dropped": 0, "tail_seq": None}
        prev = prefix[-1]["hash"] if prefix else GENESIS_HASH
        repair = make_entry(prev, len(prefix),
                            {"kind": KIND_REPAIR, "v": 1, "dropped": dropped})
        # crash-atomic: temp → fsync → replace → dir fsync (never truncate the
        # live file in place — a second crash would lose the verified prefix).
        tmp = path + ".repair.tmp"
        with open(tmp, "w", encoding="utf-8") as w:
            for e in prefix:
                w.write(entry_line(e))
            w.write(entry_line(repair))
            w.flush()
            os.fsync(w.fileno())
        os.replace(tmp, path)
        dfd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return {"repaired": True, "dropped": dropped, "tail_seq": repair["seq"]}
    finally:
        fh.close()   # releases the flock


class EventLog:
    """An open eventd log.

    ``EventLog(path)`` opens read-only; ``EventLog(path, writer=True)`` takes
    the single-writer lock and may ``append``. Opening ALWAYS verifies the
    chain (boot-time tamper check) unless ``verify=False`` is forced — which
    only ``litanydump``-style forensics should ever do.
    """

    def __init__(self, path: str, *, writer: bool = False, verify: bool = True):
        self.path = path
        self._fh = None
        # Writer path: take the exclusive lock FIRST, then load/verify under
        # it — loading before locking races a departing writer's final append
        # and would chain the next entry off a stale tail (Codex P1, PR #31).
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
        try:
            self._entries = load_entries(path)
            if verify and not verify_chain(self._entries):
                raise TamperError(
                    f"{path}: hash chain verification failed "
                    f"({len(self._entries)} entries) — refusing to serve a "
                    f"tampered audit spine")
        except TamperError:
            self.close()   # never hold the writer lock on a refused log
            raise

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
