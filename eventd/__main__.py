"""eventd CLI — verify / append / replay / floor / coldstart.

Reference tooling over a JSONL eventd log (issue #18, RFC 0004):

    python3 -m eventd verify    <log>
    python3 -m eventd append    <log> '<payload json>'
    python3 -m eventd replay    <log>
    python3 -m eventd floor     <log> <producer-agent>
    python3 -m eventd coldstart <log> <consumer-agent>

Exit codes: 0 ok / verified / RUNNING; 1 tampered, lock refusal, or
PAUSED(stale_dependency).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict

from .log import EventLog, TamperError, WriterLockError
from .statedep import DependencyIndex


def _open_ro(path: str) -> EventLog:
    try:
        return EventLog(path)
    except TamperError as e:
        print(f"eventd: TAMPERED — {e}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, path, *rest = argv

    if cmd == "verify":
        log = _open_ro(path)
        print(f"eventd: {path} — chain OK ({len(log)} entries, "
              f"tail {log.tail_hash[:16]}…)")
        return 0

    if cmd == "append":
        payload = json.loads(rest[0] if rest else sys.stdin.read())
        try:
            with EventLog(path, writer=True) as log:
                entry = log.append(payload)
        except (TamperError, WriterLockError) as e:
            print(f"eventd: refused — {e}", file=sys.stderr)
            return 1
        print(f"eventd: appended seq {entry['seq']} "
              f"({entry['hash'][:16]}…) to {path}")
        return 0

    if cmd == "replay":
        log = _open_ro(path)
        kinds = log.replay(
            lambda acc, e: acc + Counter([e["payload"].get("kind", "(other)")]),
            Counter())
        print(f"eventd: {path} — {len(log)} entries, tail {log.tail_hash[:16]}…")
        for kind, n in sorted(kinds.items()):
            print(f"  {kind}: {n}")
        return 0

    if cmd == "floor":
        log = _open_ro(path)
        floor = DependencyIndex.from_entries(log.entries).gc_floor(rest[0])
        if floor is None:
            print(f"eventd: {rest[0]} — no live consumer constrains "
                  f"compaction (floor: none)")
        else:
            print(f"eventd: {rest[0]} — producer_gc_floor = {floor} "
                  f"(compaction legal strictly below)")
        return 0

    if cmd == "coldstart":
        log = _open_ro(path)
        stale = DependencyIndex.from_entries(log.entries) \
            .verify_cold_start(rest[0], log.entries)
        if stale is None:
            print(f"eventd: {rest[0]} — dependencies verified ⇒ RUNNING")
            return 0
        print(f"eventd: {rest[0]} — PAUSED(stale_dependency): "
              f"{json.dumps(asdict(stale), sort_keys=True)}")
        return 1

    print(f"eventd: unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
