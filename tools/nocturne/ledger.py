"""nocturne ledger — single-writer, append-only, SHA256 hash-chained event log.

Mirrors ralph's chain (tools/ralph/ralphcore.py): genesis = "0"*64, each entry
hashes sha256(prev_hex || canonical_json(payload)); the chain is replayable and
tamper-evident. This is the experiment memory + cross-night novelty source.

Event payloads carry an "event" key, e.g.:
  provision | trial | kept | discarded | baseline | confirm | found | none | teardown | error
Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

GENESIS_HASH = "0" * 64


def _canon(payload: dict[str, Any]) -> str:
    """Canonical JSON (sorted keys, compact) — the exact bytes that get hashed."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def chain_hash(prev_hex: str, payload: dict[str, Any]) -> str:
    """sha256(prev_hash || canonical(payload)) — the link function (ralph-compatible)."""
    return hashlib.sha256((prev_hex + _canon(payload)).encode("utf-8")).hexdigest()


def make_entry(prev_hex: str, seq: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"seq": seq, "prev": prev_hex, "payload": payload, "hash": chain_hash(prev_hex, payload)}


def load(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append one event, linked to the current tail. Single-writer (caller serializes)."""
    entries = load(path)
    prev = entries[-1]["hash"] if entries else GENESIS_HASH
    seq = entries[-1]["seq"] + 1 if entries else 0
    entry = make_entry(prev, seq, payload)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def verify_chain(entries: list[dict[str, Any]]) -> bool:
    """seq is 0,1,2,…; each prev links the prior hash; each hash recomputes."""
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if e.get("seq") != i or e.get("prev") != prev:
            return False
        if e.get("hash") != chain_hash(prev, e.get("payload", {})):
            return False
        prev = e["hash"]
    return True


def signatures(entries: list[dict[str, Any]]) -> set[str]:
    """Signatures PROMOTED in prior nights (event == 'found') — the cross-night novelty set.

    Only `found` events count: a same-night `keep`/`discard` trial must not make its own
    signature look 'already known' to the gate. A prior promotion is what 'not novel' means.
    """
    out: set[str] = set()
    for e in entries:
        p = e.get("payload", {})
        if p.get("event") == "found" and p.get("signature"):
            out.add(p["signature"])
    return out


if __name__ == "__main__":
    import sys

    path = os.environ.get("NOCTURNE_LEDGER", "state/events.jsonl")
    if len(sys.argv) > 1 and sys.argv[1] == "replay":
        entries = load(path)
        ok = verify_chain(entries)
        print(f"ledger: {len(entries)} entries · chain {'VALID' if ok else 'BROKEN'} · {path}")
        for e in entries:
            p = e["payload"]
            print(f"  [{e['seq']:>4}] {p.get('event','?'):<10} {_canon({k: v for k, v in p.items() if k != 'event'})[:90]}")
        sys.exit(0 if ok else 1)
    print("usage: ledger.py replay", file=sys.stderr)
    sys.exit(2)
