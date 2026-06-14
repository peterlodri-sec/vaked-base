#!/usr/bin/env python3
"""test_exec_schedule.py — static parallel schedule (vakedc.schedule).

Tests:
1. Linear chain: capture → compress → publish produces levels 0,1,2 and
   checkpoints [0,1,2].
2. Cycle detection: a mutual dep between two fibers yields a non-None cycle.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from vakedc.schedule import FiberIO, compute_schedule


def _t_levels(lines):
    ok = True
    ios = [
        FiberIO("capture",  frozenset({"device.camera"}),       frozenset({"stream.raw"})),
        FiberIO("compress", frozenset({"stream.raw"}),           frozenset({"artifacts.compressed"})),
        FiberIO("publish",  frozenset({"artifacts.compressed"}), frozenset({"surface.feed"})),
    ]
    s = compute_schedule(ios)
    if s.cycle is not None:
        ok = False; lines.append(f"  FAIL: unexpected cycle {s.cycle}")
    if (s.levels.get("capture"), s.levels.get("compress"), s.levels.get("publish")) != (0, 1, 2):
        ok = False; lines.append(f"  FAIL levels: {s.levels}")
    if s.checkpoints != [0, 1, 2]:
        ok = False; lines.append(f"  FAIL checkpoints: {s.checkpoints}")
    return ok


def _t_cycle(lines):
    ios = [
        FiberIO("a", frozenset({"x"}), frozenset({"y"})),
        FiberIO("b", frozenset({"y"}), frozenset({"x"})),
    ]
    s = compute_schedule(ios)
    if s.cycle is None:
        lines.append("  FAIL: expected a cycle, got none"); return False
    return True


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run():
    lines = []
    ok = True
    for fn in (_t_levels, _t_cycle):
        try:
            ok = fn(lines) and ok
        except Exception as e:
            import traceback
            ok = False
            lines.append(f"    ERROR in {fn.__name__}: {type(e).__name__}: {e}")
            lines.append(traceback.format_exc())
    return ok, lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_exec_schedule ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
