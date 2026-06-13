"""eventd — append-only hash-chained event log (reference implementation).

Track B of the 1.0 epic (#17, issue #18): the immutable leg. This package is
the **Python reference / oracle** for the eventual Zig daemon (the #15
pattern: Python defines the bytes, Zig reproduces them). It implements:

* the frozen entry format (``core`` — verbatim the ralphcore chain:
  ``{seq, prev, payload, hash}``, sha256(prev || canonical_json(payload)));
* the daemon shape of the eventd design (``log`` — single-writer append with
  fsync, boot-time chain verification as a hard error, replay = fold);
* the RFC 0004 state-dependency layer (``statedep`` — DependencyRegistration /
  ConsumerCheckpoint / RewindEvent payloads, the O(1) dependency index, the
  dependency-aware GC floor, and the cold-start verifier).

CLI: ``python3 -m eventd {verify,append,replay,floor,coldstart} ...``.
Python 3.12 stdlib only.
"""
from .core import GENESIS_HASH, canonical_json, chain_hash, make_entry, verify_chain
from .log import EventLog, TamperError, WriterLockError, repair_truncate_tail
from .statedep import (
    DependencyIndex,
    StaleDependency,
    consumer_checkpoint,
    consumer_evicted,
    dependency_registration,
    rewind_event,
)

__all__ = [
    "GENESIS_HASH", "canonical_json", "chain_hash", "make_entry", "verify_chain",
    "EventLog", "TamperError", "WriterLockError", "repair_truncate_tail",
    "DependencyIndex", "StaleDependency",
    "dependency_registration", "consumer_checkpoint", "rewind_event",
    "consumer_evicted",
]
