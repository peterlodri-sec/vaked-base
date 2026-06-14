"""agent-memoryd — the runtime memory plane daemon (Python reference implementation).

Roster position (docs/runtime/README.md): ``memoryd`` — Zig daemon; mines source
streams into typed entries, appends to eventd, folds the log into recall state,
serves capability-bound recall queries. This package is the **Python reference /
oracle** for that daemon (the #15 pattern: Python defines the bytes + the decision,
Zig reproduces them). The hyphenated daemon name maps to the importable module
``agent_memoryd``.

It closes the memory vertical slice (0014, issue #24, epic #17):

    Vaked declares      memory sessionPalace { source = ...; scope = "agent"; ... }
        ↓ vakedc lower  gen/memory/<name>.json         (store config)
                        gen/eventd.json                (log contract)
    eventd              appended to the hash chain (write-ahead)
    memoryd             mine → append → fold → recall (this package)
        store           content-addressed in-memory dict + optional JSON persistence
        capability      POLA mem.{none,recall,append,admin} enforcement
        eventd client   write-ahead every store/forget before confirming
    Surfaces reveal     recall = fold over the log (capability-gated)

Design: docs/superpowers/specs/2026-06-13-memoryd-design.md
Language doc: docs/language/0014-memory-primitive.md
Example: vaked/examples/primitives/memory.vaked
"""
from .store import MemoryStore, MemoryEntry
from .capability import CapabilityToken, CapLevel, check_capability
from .eventd import EventdClient

__version__ = "0.1.0"

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "CapabilityToken",
    "CapLevel",
    "check_capability",
    "EventdClient",
]
