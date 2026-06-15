"""Append-only, hash-chained decision ledger for an oracle RE session.

Reuses tools/ralph/ralphcore.py chain primitives (do NOT reimplement the chain).
"""
from __future__ import annotations

import json
import os
import sys

# import ralphcore from the sibling tools/ralph
_RALPH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ralph")
sys.path.insert(0, _RALPH)
import ralphcore  # noqa: E402

GENESIS_HASH = ralphcore.GENESIS_HASH


class Ledger:
    """JSONL of ralphcore chain entries. One entry per decision / finding."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._entries = self._load()

    def _load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        for line in open(self.path):
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def append(self, payload: dict) -> dict:
        prev = self._entries[-1]["hash"] if self._entries else GENESIS_HASH
        seq = len(self._entries)
        entry = ralphcore.make_entry(prev, seq, payload)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._entries.append(entry)
        return entry

    def entries(self) -> list[dict]:
        return list(self._entries)

    def verify(self) -> bool:
        return ralphcore.verify_chain(self._entries)

    def valid_prefix(self) -> list[dict]:
        return ralphcore.longest_valid_prefix(self._entries)
