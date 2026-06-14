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
from vakedc.parser import parse_source
from vakedc.resolve import build_graph


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


_LIFECYCLE_SRC = """fiber mediaCompress {
  input = stream.screenrec
  output = artifacts.out
  lifecycle {
    on pause  { drain_timeout = "2s" }
    on resume { }
    on stop   { flush = true }
  }
}
"""


def _t_overlay_lifecycle(lines):
    ok = True
    g = build_graph(parse_source(_LIFECYCLE_SRC, "m.vaked"), "m.vaked")
    ids = {n.id for n in g.nodes}
    kinds = {n.kind for n in g.nodes}
    for need in ("m.vaked#mediaCompress/state:running",
                 "m.vaked#mediaCompress/state:paused",
                 "m.vaked#mediaCompress/state:stopped",
                 "m.vaked#mediaCompress/transition:pause"):
        if need not in ids:
            ok = False; lines.append(f"  FAIL: missing node {need}")
    if "lifecycle-state" not in kinds or "transition" not in kinds:
        ok = False; lines.append(f"  FAIL: kinds {kinds}")
    edges = {(e.source, e.label, e.target) for e in g.edges}
    want = ("m.vaked#mediaCompress", "controls", "m.vaked#mediaCompress/transition:pause")
    if want not in edges:
        ok = False; lines.append("  FAIL: missing controls edge")
    return ok


_CAP_SRC = """capability fs {
  grant repo_ro repo_rw
  order repo_ro < repo_rw
}

mesh agentfield {
  node codex {
    capabilities = [fs.repo_rw]
  }
}
"""


def _t_overlay_caps(lines):
    ok = True
    g = build_graph(parse_source(_CAP_SRC, "c.vaked"), "c.vaked")
    ids = {n.id for n in g.nodes}
    if "c.vaked#fs/grant:repo_rw" not in ids:
        ok = False; lines.append("  FAIL: missing grant node")
    edges = {(e.source, e.label, e.target) for e in g.edges}
    want = ("c.vaked#agentfield/codex", "holds", "c.vaked#fs/grant:repo_rw")
    if want not in edges:
        ok = False; lines.append(f"  FAIL: missing holds edge; edges={sorted(edges)}")
    return ok


_WAVE_SRC = """fiber capture  { input = device.camera        output = stream.raw }
fiber compress { input = stream.raw           output = artifacts.compressed }
fiber publish  { input = artifacts.compressed output = surface.feed }
parallel "pipe" {
  fibers = [capture, compress, publish]
  lifecycle {
    on pause  { }
    on stop   { }
    on rewind { }
  }
}
"""


def _t_overlay_schedule(lines):
    ok = True
    g = build_graph(parse_source(_WAVE_SRC, "w.vaked"), "w.vaked")
    node = {n.id: n for n in g.nodes}
    if node["w.vaked#compress"].props.get("level") != 1:
        ok = False; lines.append(f"  FAIL compress level: {node['w.vaked#compress'].props}")
    edges = {(e.source, e.label, e.target) for e in g.edges}
    if ("w.vaked#compress", "depends-on", "w.vaked#capture") not in edges:
        ok = False; lines.append("  FAIL: missing depends-on edge")
    if "w.vaked#pipe/checkpoint:0" not in node:
        ok = False; lines.append("  FAIL: missing checkpoint node")
    return ok


def _t_oracle(lines):
    from vakedc.oracle import expected_behavior
    ok = True
    g = build_graph(parse_source(_WAVE_SRC, "w.vaked"), "w.vaked")
    b = expected_behavior(g)
    if b["start_order"] != [["capture"], ["compress"], ["publish"]]:
        ok = False; lines.append(f"  FAIL start_order: {b['start_order']}")
    if "pause" not in b["control_alphabet"]:
        ok = False; lines.append(f"  FAIL: 'pause' missing from control_alphabet: {b['control_alphabet']}")
    if "stop" not in b["control_alphabet"]:
        ok = False; lines.append(f"  FAIL: 'stop' missing from control_alphabet: {b['control_alphabet']}")
    return ok


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run():
    lines = []
    ok = True
    for fn in (_t_levels, _t_cycle, _t_overlay_lifecycle, _t_overlay_caps, _t_overlay_schedule, _t_oracle):
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
