"""eventd.core — the FROZEN hash-chain entry format.

Verbatim the format the ralph driver proved (tools/ralph/ralphcore.py:
``GENESIS_HASH`` / ``_canon`` / ``chain_hash`` / ``make_entry`` /
``verify_chain``) and the eventd design froze
(docs/superpowers/specs/2026-06-12-eventd-design.md §"Entry format").
tests/spec/test_eventd.py cross-verifies this module against ralphcore on
shared vectors — any drift between the two is a spec-test failure.

One JSON object per line (JSONL), append-only:

    { "seq":  <u64, 0-based>,
      "prev": <hex sha256 of the previous entry; GENESIS = 64*"0" at seq 0>,
      "payload": <arbitrary JSON event body>,
      "hash": sha256(prev_hex || canonical_json(payload)) }

Canonical JSON dialect — the CROSS-LANGUAGE HASH CONTRACT. Python's encoder
defaults are not the unstated spec; a port (the Zig daemon, #15 pattern) MUST
reproduce these bytes exactly:

  * UTF-8 bytes. ``ensure_ascii=False``: non-ASCII characters are emitted as
    raw UTF-8, never ``\\uXXXX``-escaped; only the JSON-mandatory escapes are
    produced (``\\"``, ``\\\\``, and control characters as ``\\uXXXX``).
  * Object keys sorted by Unicode code point; separators ``(",", ":")`` —
    no insignificant whitespace anywhere.
  * Numbers: integers in full decimal form (arbitrary precision — no float
    folding); floats in Python ``repr`` form, i.e. the SHORTEST string that
    round-trips the IEEE-754 double (``-0.0`` → ``-0.0``, ``1.0`` → ``1.0``,
    ``1e-6`` → ``1e-06``). **NaN / Infinity are rejected** (``ValueError``) —
    deliberately stricter than ralphcore, whose default would emit non-JSON
    ``NaN`` literals.
  * Strings hash AS WRITTEN: **no Unicode normalization**. ``"é"`` (U+00E9)
    and ``"e\\u0301"`` (e + combining acute) are different payloads by design.
  * One entry per line, LF-terminated. A truncated / partial tail line is
    TAMPER (refused at load by ``eventd.log``); any repair is a future
    explicit operator command (``eventd repair --truncate-tail``-shaped),
    never automatic.
"""
from __future__ import annotations

import hashlib
import json

GENESIS_HASH = "0" * 64


def canonical_json(payload: dict) -> str:
    """Canonical JSON of a payload — the exact bytes hashed (dialect: module
    docstring). Byte-identical to ralphcore._canon on every finite payload;
    NaN/Infinity raise ``ValueError`` instead of producing invalid JSON."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False, allow_nan=False)


def chain_hash(prev_hex: str, payload: dict) -> str:
    """sha256(prev_hash || canonical(payload)) — the link function."""
    return hashlib.sha256(
        (prev_hex + canonical_json(payload)).encode("utf-8")).hexdigest()


def make_entry(prev_hex: str, seq: int, payload: dict) -> dict:
    """One hash-chained log entry. ``prev_hex`` is GENESIS_HASH for seq 0."""
    return {"seq": seq, "prev": prev_hex, "payload": payload,
            "hash": chain_hash(prev_hex, payload)}


def verify_chain(entries: list[dict]) -> bool:
    """True iff ``entries`` is a contiguous, untampered chain from genesis:
    seq is 0,1,2,…; each ``prev`` links the prior ``hash``; each ``hash``
    recomputes. Any tamper (payload edit, reorder, insert, drop) fails."""
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if e.get("seq") != i:
            return False
        if e.get("prev") != prev:
            return False
        if e.get("hash") != chain_hash(prev, e.get("payload", {})):
            return False
        prev = e["hash"]
    return True


def entry_line(entry: dict) -> str:
    """The canonical on-disk line for an entry (deterministic: same entries ⇒
    byte-identical log files). Hashing never depends on this — only on
    ``canonical_json(payload)`` — but eventd fixes the line encoding so two
    runs of the same event sequence produce identical files."""
    return json.dumps(entry, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=False, allow_nan=False) + "\n"
