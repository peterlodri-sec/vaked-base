"""CLI entry point for meta-ralphd.

Usage::

    meta-ralphd watch             # Run the watchdog loop (default)
    meta-ralphd check             # One-shot health check, print report
    meta-ralphd check --watch     # One-shot health check then enter watch loop
    meta-ralphd ebpf-profile      # Generate the eBPF C program for L1 syscall guard
    meta-ralphd verify-ledger     # Verify the Oculus ledger chain integrity
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

from .monitor import (
    check_l1_health,
    verify_chain_integrity,
    RALPH_EVENTS_PATH,
)
from .watchdog import run_watchdog
from .ebpf import EbpfMonitor


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="meta-ralphd[%(process)d]: %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def cmd_check(args) -> int:
    """One-shot health check."""
    verbose = getattr(args, "verbose", False)
    _setup_logging(verbose)

    report = check_l1_health()
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.healthy else 1


def cmd_watch(args) -> int:
    """Run the watchdog loop (blocking)."""
    verbose = getattr(args, "verbose", False)
    _setup_logging(verbose)

    interval = getattr(args, "interval", 5.0)
    journal_stale = getattr(args, "journal_stale", 10.0)
    memory_max = getattr(args, "memory_max", 200)

    run_watchdog(
        check_interval_sec=interval,
        journal_max_stale=journal_stale,
        memory_max_mb=memory_max,
    )
    return 0


def cmd_ebpf_profile(args) -> int:
    """Generate the eBPF C program for L1 syscall guard."""
    monitor = EbpfMonitor(0)
    print(monitor.generate_bpf_c_program())
    return 0


def cmd_verify_ledger(args) -> int:
    """Verify the L1 events chain integrity."""
    _setup_logging()
    try:
        n = verify_chain_integrity()
        print(f"L1 chain: {n} entries, integrity OK")
        return 0
    except Exception as e:
        print(f"L1 chain: INTEGRITY FAILURE — {e}")
        return 1


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="meta-ralphd",
        description="Meta-Ralph (L2) — recursive observer for the Vaked runtime",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # check
    p = sub.add_parser("check", help="One-shot health check of L1")
    p.set_defaults(fn=cmd_check)

    # watch
    p = sub.add_parser("watch", help="Run the watchdog loop (blocking)")
    p.add_argument("--interval", type=float, default=5.0,
                   help="Health check interval in seconds (default: 5)")
    p.add_argument("--journal-stale", type=float, default=10.0,
                   help="Max journal staleness in seconds (default: 10)")
    p.add_argument("--memory-max", type=int, default=200,
                   help="Max L1 memory in MiB (default: 200)")
    p.set_defaults(fn=cmd_watch)

    # ebpf-profile
    p = sub.add_parser("ebpf-profile", help="Generate the eBPF C program")
    p.set_defaults(fn=cmd_ebpf_profile)

    # verify-ledger
    p = sub.add_parser("verify-ledger", help="Verify L1 event chain integrity")
    p.set_defaults(fn=cmd_verify_ledger)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
