"""eventd CLI — verify / append / replay / floor / coldstart.

Reference tooling over a JSONL eventd log (issue #18, RFC 0004):

    python3 -m eventd verify    <log>
    python3 -m eventd append    <log> '<payload json>'
    python3 -m eventd replay    <log>
    python3 -m eventd state     <log> [--at N]
    python3 -m eventd floor     <log> <producer-agent>
    python3 -m eventd coldstart <log> <consumer-agent>

``state`` is the Track D jump/replay verb (control-plane design 2026-06-12):
verify the whole chain, then fold entries 0..N (default: tip) and print the
folded view as of N — per-kind counts and the live state-dependency summary
(GC floors per producer). Read-only; "going back" in anger is a RewindEvent
APPEND, never truncation.

Exit codes are STABLE ORACLE CONTRACT (harness scripts and the Zig-port
parity tests depend on them):

    0   ok / chain verified / dependencies verified ⇒ RUNNING
    2   usage error
    3   PAUSED(stale_dependency)  — coldstart refused the RUNNING transition
    4   tampered / malformed log  — the audit spine is broken
    5   writer refused            — single-writer lock held elsewhere
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict

from .log import EventLog, TamperError, WriterLockError
from .statedep import DependencyIndex

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_STALE = 3
EXIT_TAMPERED = 4
EXIT_LOCKED = 5


def _open_ro(path: str) -> EventLog:
    try:
        return EventLog(path)
    except TamperError as e:
        print(f"eventd: TAMPERED — {e}", file=sys.stderr)
        sys.exit(EXIT_TAMPERED)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return EXIT_USAGE
    cmd, path, *rest = argv

    if cmd == "verify":
        log = _open_ro(path)
        print(f"eventd: {path} — chain OK ({len(log)} entries, "
              f"tail {log.tail_hash[:16]}…)")
        return EXIT_OK

    if cmd == "append":
        payload = json.loads(rest[0] if rest else sys.stdin.read())
        try:
            with EventLog(path, writer=True) as log:
                entry = log.append(payload)
        except TamperError as e:
            print(f"eventd: refused — {e}", file=sys.stderr)
            return EXIT_TAMPERED
        except WriterLockError as e:
            print(f"eventd: refused — {e}", file=sys.stderr)
            return EXIT_LOCKED
        print(f"eventd: appended seq {entry['seq']} "
              f"({entry['hash'][:16]}…) to {path}")
        return EXIT_OK

    if cmd == "replay":
        log = _open_ro(path)
        kinds = log.replay(
            lambda acc, e: acc + Counter([e["payload"].get("kind", "(other)")]),
            Counter())
        print(f"eventd: {path} — {len(log)} entries, tail {log.tail_hash[:16]}…")
        for kind, n in sorted(kinds.items()):
            print(f"  {kind}: {n}")
        return EXIT_OK

    if cmd == "state":
        log = _open_ro(path)
        n = len(log)
        if rest and rest[0] == "--at":
            n = min(int(rest[1]) + 1, len(log))   # inclusive entry index N
        entries = log.entries[:n]
        kinds = Counter(e["payload"].get("kind", "(other)") for e in entries)
        tail = entries[-1]["hash"][:16] if entries else "(genesis)"
        print(f"eventd: {path} — state as of entry {n - 1 if n else '-'} "
              f"({n}/{len(log)} entries, tail {tail}…)")
        for kind, c in sorted(kinds.items()):
            print(f"  {kind}: {c}")
        idx = DependencyIndex.from_entries(entries)
        producers = sorted({p for (_c, p) in idx.registrations}
                           | {p for (_c, p) in idx.checkpoints})
        for p in producers:
            floor = idx.gc_floor(p)
            print(f"  floor[{p}]: "
                  f"{floor if floor is not None else 'none'}")
        if idx.rewinds:
            for p, rw in sorted(idx.rewinds.items()):
                print(f"  rewind[{p}]: to step {rw['rewind_to_step']} "
                      f"(epoch {rw['topology_epoch']})")
        if idx.evicted:
            print(f"  evicted: {', '.join(sorted(idx.evicted))}")
        return EXIT_OK

    if cmd == "floor":
        log = _open_ro(path)
        floor = DependencyIndex.from_entries(log.entries).gc_floor(rest[0])
        if floor is None:
            print(f"eventd: {rest[0]} — no live consumer constrains "
                  f"compaction (floor: none)")
        else:
            print(f"eventd: {rest[0]} — producer_gc_floor = {floor} "
                  f"(compaction legal strictly below)")
        return EXIT_OK

    if cmd == "coldstart":
        log = _open_ro(path)
        stale = DependencyIndex.from_entries(log.entries) \
            .verify_cold_start(rest[0], log.entries)
        if stale is None:
            print(f"eventd: {rest[0]} — dependencies verified ⇒ RUNNING")
            return EXIT_OK
        print(f"eventd: {rest[0]} — PAUSED(stale_dependency): "
              f"{json.dumps(asdict(stale), sort_keys=True)}")
        return EXIT_STALE

    print(f"eventd: unknown command {cmd!r}", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
