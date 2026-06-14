#!/usr/bin/env python3
"""benchmark-scalability-sweep.py — the N-sweep scalability harness.

Where the sibling ``benchmark-100k-scalability.py`` measures ONE point (the
committed 100k fixture, which is itself a stub), this script generates a family
of *synthetic flat-architecture* ``.vaked`` files at several sizes N and runs
the full vakedc pipeline (parse -> check -> lower) K times at each N, recording
per-stage wall-clock so the results can be plotted as a log-log scalability
curve (see ``docs/evaluation/scalability-analysis-v0.1.md``).

  * Deterministic + self-contained: the generator below is the only source of
    truth for the synthetic input. No network, no committed fixture, no RNG.
  * Flat architecture (0012 lowering's common case): 1 runtime, 1 stream, N
    "worker" fibers + 2 "aggregator" fibers, all sharing one stream input. The
    runtime's `contains` fan-out is the thing whose cost we are probing — the
    `_children_of` full-edge scan in vakedc/lower.py runs over this fan-out.
  * No mesh / workflow / parallel-with-many-members: those exercise *other*
    code paths (the O(W*E) workflow scan at lower.py:1885); a flat fiber fan-out
    isolates the runtime-decomposition cost the credibility review flagged.

NOT a determinism check and NOT the 100k stub re-run — it is the controlled
*curve*. Determinism is already covered by benchmark-100k-scalability.py.

⚠️  RUN ON A BUILD HOST, NOT THE DEV MACHINE. The repo rule "NEVER BUILD ON
DEVELOPER MACHINE" plus the sheer weight of N=100000 (a multi-MB source file,
~100k nodes, repeated K times) means this belongs on dev-cx53 or GitHub Actions.
See the doc's §1 for the exact command. The generator (`--emit-only`) is cheap
and safe to run anywhere for inspection.

Usage:
  # full sweep (build host):
  python3 scripts/benchmark-scalability-sweep.py --sweep --iters 10 \
      --out artifacts/scalability-curve.csv

  # custom N set:
  python3 scripts/benchmark-scalability-sweep.py --sweep --sizes 100,1000,10000 \
      --iters 5 --out artifacts/curve.csv

  # just write the synthetic .vaked for inspection (cheap, dev-safe):
  python3 scripts/benchmark-scalability-sweep.py --emit-only --n 1000 \
      --out /tmp/synth-1000.vaked
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# ANSI color codes (skipped automatically when stdout is not a tty).
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SIZES = (100, 1000, 10000, 100000)

# The engine decl the synthetic fibers reference. It is written as a SIDECAR
# file (engine.vaked) that the generated runtime imports via `use "./engine.vaked"`.
# An `engine` decl only enters a runtime's scope through a `use` import — a
# top-level engine decl in the same file is NOT in the runtime's closed-world
# scope (vakedc/check.py:_collect_import_decls vs _collect_runtime_decls). The
# sidecar keeps the input self-contained (no dependency on the repo's examples/
# engines/zig.vaked) while resolving cleanly. Mirrors examples/engines/zig.vaked.
_ENGINE_SIDECAR_NAME = "engine.vaked"
_ENGINE_DECL = (
    'engine zigDaemon(name: String, src: Path) -> Engine {\n'
    "  package = zig.build {\n"
    "    inherit src\n"
    '    optimize = "ReleaseSafe"\n'
    "  }\n"
    "\n"
    '  check("smoke", "${package}/bin/${name} --help")\n'
    "}\n"
)


def _color(s, code):
    return s if not sys.stdout.isatty() else code + s + RESET


def generate_synthetic_vaked(n: int) -> str:
    """Return a deterministic, self-contained flat-architecture .vaked source
    with ``n`` worker fibers plus 2 aggregator fibers under one runtime.

    Shape (the flat common case 0012 lowering targets):
      runtime "scale-sweep" {
        systems = ["x86_64-linux"]
        stream workIn { source = agentpipe.transcripts; type = Agent.Transcript; retention = 7d }
        fiber worker00001 { engine = zigDaemon; input = stream.workIn; output = artifacts.w00001 }
        ... n of them ...
        fiber aggregatorA { engine = zigDaemon; input = stream.workIn; output = artifacts.aggA }
        fiber aggregatorB { engine = zigDaemon; input = stream.workIn; output = artifacts.aggB }
      }

    Every fiber shares the single stream `workIn` as input and emits a distinct
    artifact, so the runtime's `contains` fan-out is exactly (n + 2) fibers + 1
    stream — a flat tree, no nesting, no mesh, no workflow. The runtime imports
    the engine via `use "./engine.vaked"` (the sidecar this harness writes next
    to the source). The generated source parses, checks, and lowers with no
    diagnostics. Pure function of ``n``: byte-identical for a given n (no clock,
    no RNG)."""
    lines = []
    lines.append('use "./%s"' % _ENGINE_SIDECAR_NAME)
    lines.append("")
    lines.append("# synthetic flat-architecture scalability input — generated by")
    lines.append("# scripts/benchmark-scalability-sweep.py (deterministic, n=%d)." % n)
    lines.append('# 1 runtime + 1 stream + %d worker fibers + 2 aggregator fibers.' % n)
    lines.append("")
    lines.append('runtime "scale-sweep" {')
    lines.append('  systems = ["x86_64-linux"]')
    lines.append("")
    lines.append("  stream workIn {")
    lines.append("    source = agentpipe.transcripts")
    lines.append("    type = Agent.Transcript")
    lines.append("    retention = 7d")
    lines.append("  }")
    lines.append("")
    # N worker fibers — fixed-width index so names are stable & sortable.
    width = max(5, len(str(n)))
    for i in range(1, n + 1):
        tag = str(i).zfill(width)
        lines.append("  fiber worker%s {" % tag)
        lines.append("    engine = zigDaemon")
        lines.append("    input = stream.workIn")
        lines.append("    output = artifacts.w%s" % tag)
        lines.append("  }")
    # 2 aggregator fibers (the "results sink" pair).
    for tag in ("A", "B"):
        lines.append("  fiber aggregator%s {" % tag)
        lines.append("    engine = zigDaemon")
        lines.append("    input = stream.workIn")
        lines.append("    output = artifacts.agg%s" % tag)
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _run_stage(cmd, env, timeout):
    """Run one compiler stage; return (elapsed_ms, returncode). On timeout the
    elapsed is the wall time spent and rc is 124 (matches the sibling script)."""
    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return elapsed_ms, result.returncode
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return elapsed_ms, 124


def run_point(n: int, iters: int, timeout: int, keep_dir: Path | None):
    """Generate the synthetic input for size ``n`` and run parse/check/lower
    ``iters`` times. Returns a dict of per-iteration rows + a summary.

    Each iteration measures the three CLI subcommands separately (parse, check,
    lower), exactly as the sibling 100k script does, so the numbers are directly
    comparable. The synthetic file is written once and reused across iterations
    (its generation is not part of the measured pipeline)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    src = generate_synthetic_vaked(n)
    # Write the source to a temp (or kept) location; lower writes its tree to a
    # throwaway dir so the artifact IO doesn't accumulate on disk between iters.
    work = keep_dir or Path(tempfile.mkdtemp(prefix="vaked-sweep-%d-" % n))
    work.mkdir(parents=True, exist_ok=True)
    # The engine sidecar the runtime `use`-imports (resolves `engine = zigDaemon`).
    (work / _ENGINE_SIDECAR_NAME).write_text(_ENGINE_DECL, encoding="utf-8")
    vaked_path = work / ("synth-%d.vaked" % n)
    vaked_path.write_text(src, encoding="utf-8")
    out_dir = work / "lower-out"

    rows = []
    for it in range(iters):
        parse_ms, parse_rc = _run_stage(
            ["python3", "-m", "vakedc", "parse", str(vaked_path)], env, timeout)
        check_ms, check_rc = _run_stage(
            ["python3", "-m", "vakedc", "check", str(vaked_path)], env, timeout)
        lower_ms, lower_rc = _run_stage(
            ["python3", "-m", "vakedc", "lower", str(vaked_path),
             "--out", str(out_dir)], env, timeout)
        total_ms = parse_ms + check_ms + lower_ms
        ok = (parse_rc == 0 and check_rc == 0 and lower_rc == 0)
        rows.append({
            "n": n, "iter": it + 1,
            "parse_ms": parse_ms, "check_ms": check_ms,
            "lower_ms": lower_ms, "total_ms": total_ms,
            "parse_rc": parse_rc, "check_rc": check_rc, "lower_rc": lower_rc,
            "ok": ok,
        })

    ok_rows = [r for r in rows if r["ok"]]

    def _agg(key):
        vals = [r[key] for r in ok_rows]
        if not vals:
            return {"min": None, "median": None, "mean": None, "max": None}
        return {
            "min": min(vals),
            "median": statistics.median(vals),
            "mean": statistics.fmean(vals),
            "max": max(vals),
        }

    summary = {
        "n": n,
        "iters": iters,
        "ok_iters": len(ok_rows),
        "fibers": n + 2,
        "parse_ms": _agg("parse_ms"),
        "check_ms": _agg("check_ms"),
        "lower_ms": _agg("lower_ms"),
        "total_ms": _agg("total_ms"),
    }
    return rows, summary


def write_csv(path: Path, summaries):
    """Write the per-N summary as CSV. One row per N; columns are the median of
    each per-stage timing (median is robust to scheduler jitter on a shared
    build host). Raw per-iteration rows live in the sibling JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["n", "fibers", "iters", "ok_iters",
              "parse_ms_median", "check_ms_median", "lower_ms_median",
              "total_ms_median",
              "parse_ms_min", "check_ms_min", "lower_ms_min", "total_ms_min"]
    lines = [",".join(header)]
    for s in summaries:
        def med(k):
            v = s[k]["median"]
            return "%.3f" % v if v is not None else ""

        def mn(k):
            v = s[k]["min"]
            return "%.3f" % v if v is not None else ""

        lines.append(",".join([
            str(s["n"]), str(s["fibers"]), str(s["iters"]), str(s["ok_iters"]),
            med("parse_ms"), med("check_ms"), med("lower_ms"), med("total_ms"),
            mn("parse_ms"), mn("check_ms"), mn("lower_ms"), mn("total_ms"),
        ]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path: Path, sizes, iters, summaries, all_rows):
    doc = {
        "tool": "benchmark-scalability-sweep.py",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": os.uname().nodename if hasattr(os, "uname") else None,
        "architecture": "synthetic flat: 1 runtime + 1 stream + N worker fibers + 2 aggregators",
        "sizes": list(sizes),
        "iters": iters,
        "summaries": summaries,
        "iterations": all_rows,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def cmd_sweep(args) -> int:
    sizes = (tuple(int(x) for x in args.sizes.split(","))
             if args.sizes else DEFAULT_SIZES)
    out_csv = Path(args.out).resolve()
    out_json = out_csv.with_suffix(".json")

    print(_color("\nVaked scalability sweep", BOLD))
    print("Architecture: synthetic flat (1 runtime + 1 stream + N fibers + 2 aggregators)")
    print("Sizes (N): %s" % ", ".join(str(s) for s in sizes))
    print("Iterations per N: %d" % args.iters)
    print("Per-stage timeout: %ds" % args.timeout)
    print("CSV -> %s" % out_csv)
    print("JSON -> %s\n" % out_json)

    summaries = []
    all_rows = []
    for n in sizes:
        print(_color("[N=%d] " % n, BOLD), end="", flush=True)
        rows, summary = run_point(n, args.iters, args.timeout, None)
        all_rows.extend(rows)
        summaries.append(summary)
        if summary["ok_iters"] == 0:
            print(_color("FAILED (no clean iterations)", YELLOW))
        else:
            tm = summary["total_ms"]["median"]
            print(_color("total median %.1f ms (%d/%d ok)"
                         % (tm, summary["ok_iters"], args.iters), GREEN))

    write_csv(out_csv, summaries)
    write_json(out_json, sizes, args.iters, summaries, all_rows)

    print(_color("\n=== Curve (median ms) ===", BOLD))
    print("%8s %12s %12s %12s %12s"
          % ("N", "parse", "check", "lower", "total"))
    for s in summaries:
        def cell(k):
            v = s[k]["median"]
            return "%.1f" % v if v is not None else "—"

        print("%8d %12s %12s %12s %12s"
              % (s["n"], cell("parse_ms"), cell("check_ms"),
                 cell("lower_ms"), cell("total_ms")))
    print(_color("\nWrote %s and %s" % (out_csv, out_json), BLUE))
    print("Read the log-log slope in docs/evaluation/scalability-analysis-v0.1.md §3.\n")
    return 0


def cmd_emit_only(args) -> int:
    """Write the synthetic .vaked for one N and exit — cheap, dev-machine-safe
    (no compiler run). For inspecting what the sweep feeds the pipeline."""
    src = generate_synthetic_vaked(args.n)
    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src, encoding="utf-8")
        # Write the engine sidecar alongside so the emitted file checks cleanly.
        (out.parent / _ENGINE_SIDECAR_NAME).write_text(_ENGINE_DECL, encoding="utf-8")
        print("Wrote synthetic .vaked (n=%d, %d bytes) -> %s"
              % (args.n, len(src.encode("utf-8")), out))
        print("Wrote engine sidecar -> %s" % (out.parent / _ENGINE_SIDECAR_NAME))
    else:
        sys.stdout.write(src)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="benchmark-scalability-sweep.py",
        description="N-sweep scalability harness for the vakedc pipeline "
                    "(parse -> check -> lower). RUN ON A BUILD HOST, not the "
                    "dev machine.",
    )
    ap.add_argument("--sweep", action="store_true",
                    help="run the full N-sweep (the curve)")
    ap.add_argument("--emit-only", action="store_true",
                    help="write the synthetic .vaked for --n and exit "
                         "(cheap, no compiler run)")
    ap.add_argument("--sizes", default=None,
                    help="comma-separated N values "
                         "(default: 100,1000,10000,100000)")
    ap.add_argument("--n", type=int, default=1000,
                    help="single N for --emit-only (default: 1000)")
    ap.add_argument("--iters", type=int, default=10,
                    help="iterations per N (default: 10)")
    ap.add_argument("--timeout", type=int, default=600,
                    help="per-stage subprocess timeout in seconds (default: 600)")
    ap.add_argument("--out", default="artifacts/scalability-curve.csv",
                    help="CSV output path (a sibling .json is written too); "
                         "or the .vaked path for --emit-only")
    args = ap.parse_args(argv)

    if args.emit_only:
        return cmd_emit_only(args)
    if args.sweep:
        return cmd_sweep(args)
    ap.error("specify --sweep (run the curve) or --emit-only (write input)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
