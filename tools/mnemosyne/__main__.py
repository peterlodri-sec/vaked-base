#!/usr/bin/env python3
"""Mnemosyne CLI — recursive ancestry compactor for the Oculus ledger.

Usage:
    mnemosyne squash <ledger_path>          # Squash old entries
    mnemosyne squash --dry-run <path>      # Preview without writing
    mnemosyne daemon <path>                # Run as 24h background service
    mnemosyne verify <path>                # Verify chain integrity
    mnemosyne analyze <path>               # Show squash potential
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

from . import (
    squash_ledger,
    verify_chain,
    HIGH_FIDELITY_DAYS,
    SQUASH_INTERVAL_SEC,
)


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="mnemosyne[%(process)d]: %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def cmd_squash(args) -> int:
    """Perform one squash cycle."""
    verbose = getattr(args, "verbose", False)
    _setup_logging(verbose)
    ledger_path = args.ledger_path
    dry_run = getattr(args, "dry_run", False)
    days = getattr(args, "days", HIGH_FIDELITY_DAYS)

    result = squash_ledger(ledger_path, high_fidelity_days=days, dry_run=dry_run)
    if result is None:
        return 0
    return 0


def cmd_daemon(args) -> int:
    """Run as 24h background service."""
    verbose = getattr(args, "verbose", False)
    _setup_logging(verbose)
    ledger_path = args.ledger_path
    days = getattr(args, "days", HIGH_FIDELITY_DAYS)

    from . import run_mnemosyne
    run_mnemosyne(ledger_path, high_fidelity_days=days)
    return 0


def cmd_verify(args) -> int:
    """Verify chain integrity."""
    _setup_logging(True)
    ledger_path = args.ledger_path

    entries = []
    with open(ledger_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))

    ok = verify_chain(entries)
    if ok:
        print(f"Chain integrity: PASS ({len(entries)} entries)")
        return 0
    else:
        print(f"Chain integrity: FAIL")
        return 1


def cmd_analyze(args) -> int:
    """Analyze squash potential without modifying."""
    _setup_logging(True)
    ledger_path = args.ledger_path
    days = getattr(args, "days", HIGH_FIDELITY_DAYS)
    now = time.time()
    cutoff = now - (days * 86400)

    entries = []
    with open(ledger_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))

    if not entries:
        print("Ledger is empty")
        return 0

    total = len(entries)
    old = [e for e in entries if e.get("payload", {}).get("timestamp", 0) < cutoff and e.get("seq", 0) > 0]
    old_critical = [e for e in old if _is_critical(e)]
    old_normal = [e for e in old if not _is_critical(e)]
    recent = [e for e in entries if e.get("payload", {}).get("timestamp", 0) >= cutoff or e.get("seq", 0) == 0]

    print(f"\n=== Mnemosyne Analysis ===")
    print(f"  Ledger:              {ledger_path}")
    print(f"  Total entries:       {total}")
    print(f"  High-fidelity days:  {days}")
    print(f"  Cutoff timestamp:    {time.ctime(cutoff)}")
    print(f"  Old entries:         {len(old)}")
    print(f"    Critical preserve: {len(old_critical)}")
    print(f"    Normal squash:     {len(old_normal)}")
    print(f"  Recent entries:      {len(recent)}")
    if old_normal:
        reduction = (1 - ((len(old_critical) + len(recent) + 1) / total)) * 100
        print(f"  Estimated reduction: {reduction:.1f}%")
        print(f"  New total:           {len(old_critical) + len(recent) + 1}")
    print()

    if old_critical:
        for e in old_critical:
            print(f"  PRESERVE: seq={e.get('seq')} kind={e.get('payload',{}).get('kind','?')}")


def _is_critical(entry: dict) -> bool:
    from . import is_critical_event
    return is_critical_event(entry)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="mnemosyne",
        description="Mnemosyne — recursive ancestry compactor for the Oculus ledger",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose")
    parser.add_argument("--days", type=int, default=HIGH_FIDELITY_DAYS,
                        help="High-fidelity window in days (default: 7)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("squash", help="Squash old entries")
    p.add_argument("ledger_path", help="Path to Oculus ledger JSONL")
    p.add_argument("--dry-run", action="store_true", help="Preview only")
    p.set_defaults(fn=cmd_squash)

    p = sub.add_parser("daemon", help="Run as 24h background service")
    p.add_argument("ledger_path", help="Path to Oculus ledger JSONL")
    p.set_defaults(fn=cmd_daemon)

    p = sub.add_parser("verify", help="Verify chain integrity")
    p.add_argument("ledger_path", help="Path to Oculus ledger JSONL")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("analyze", help="Analyze squash potential")
    p.add_argument("ledger_path", help="Path to Oculus ledger JSONL")
    p.set_defaults(fn=cmd_analyze)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
