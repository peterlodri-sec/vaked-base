"""Append-only, hash-chained event ledger for a CTF simulation.

Reuses tools/ralph/ralphcore.py chain primitives (timestamp-free → replay-stable:
two runs with the same payloads produce the same chain hash). In-memory by default;
pass a path to also persist JSONL.
"""
from __future__ import annotations

import json
import os
import sys

_RALPH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ralph")
sys.path.insert(0, _RALPH)
import ralphcore  # noqa: E402

GENESIS_HASH = ralphcore.GENESIS_HASH


class Ledger:
    """A chain of `ralphcore` entries: {seq, prev, payload, hash}. Pure/deterministic."""

    def __init__(self, path: str | None = None):
        self.path = path
        self._entries: list[dict] = []
        if path and os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line:
                    self._entries.append(json.loads(line))

    def append(self, payload: dict) -> dict:
        prev = self._entries[-1]["hash"] if self._entries else GENESIS_HASH
        entry = ralphcore.make_entry(prev, len(self._entries), payload)
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._entries.append(entry)
        return entry

    def entries(self) -> list[dict]:
        return list(self._entries)

    def verify(self) -> bool:
        return ralphcore.verify_chain(self._entries)

    def head(self) -> str:
        return self._entries[-1]["hash"] if self._entries else GENESIS_HASH
