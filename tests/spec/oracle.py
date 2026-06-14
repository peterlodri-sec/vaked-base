#!/usr/bin/env python3
"""oracle.py — differential gate: run the SAME .vaked inputs through the Python
`vakedc` and the Zig `vakedc`, byte-compare each stage's artifact.

This is the correctness spine of the Python→Zig migration (design spec §5). A
stage is "green" only when every corpus file produces a byte-identical artifact
(stdout) AND an identical exit code from both implementations.

Opt-in: set ``VAKEDC_ZIG`` to the Zig binary path (e.g.
``zig/zig-out/bin/vakedc``). When unset, the oracle skips (and passes) so the
normal Python suite is unaffected.

Stages become active by being listed in ``ENABLED_STAGES``; that list grows one
entry per migration phase (lex → parse → check → lower). Until a stage is
enabled, its spec below is dormant.

Run standalone for one stage:

    VAKEDC_ZIG=zig/zig-out/bin/vakedc python3 tests/spec/oracle.py lex
"""

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

# Stages whose Zig implementation exists and should be gated. Grows per phase.
ENABLED_STAGES: list[str] = ["lex"]

# How to invoke each stage on each implementation. Each entry maps a stage to
# the argv *suffix* (after the program) that emits the comparable artifact on
# stdout. The Python program is ``python3 -m vakedc``; the Zig program is the
# VAKEDC_ZIG binary. `lower` is special-cased (it writes a tree, not stdout) and
# is added in Phase 4.
STAGE_ARGS = {
    "lex": lambda f: ["lex", f],
    "parse": lambda f: ["parse", f, "--print"],
    "check": lambda f: ["check", f, "--json"],
}


def corpus() -> list[str]:
    """All example .vaked files (repo-relative), sorted for determinism."""
    pat = os.path.join(REPO_ROOT, "vaked", "examples", "**", "*.vaked")
    return sorted(os.path.relpath(p, REPO_ROOT) for p in glob.glob(pat, recursive=True))


def _run(argv: list[str]) -> tuple[bytes, int]:
    """Run argv from the repo root; return (stdout_bytes, returncode)."""
    proc = subprocess.run(
        argv, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return proc.stdout, proc.returncode


def py_artifact(stage: str, rel_file: str) -> tuple[bytes, int]:
    return _run([sys.executable, "-m", "vakedc", *STAGE_ARGS[stage](rel_file)])


def zig_artifact(stage: str, rel_file: str, zig_bin: str) -> tuple[bytes, int]:
    return _run([zig_bin, *STAGE_ARGS[stage](rel_file)])


def _first_diff(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n  # one is a prefix of the other


def diff_stage(stage: str, zig_bin: str) -> tuple[bool, list[str]]:
    """Byte-compare the stage artifact across both impls over the whole corpus."""
    lines: list[str] = []
    files = corpus()
    mismatches = 0
    for rel in files:
        py_out, py_rc = py_artifact(stage, rel)
        zg_out, zg_rc = zig_artifact(stage, rel, zig_bin)
        if py_out == zg_out and py_rc == zg_rc:
            continue
        mismatches += 1
        if py_rc != zg_rc:
            lines.append(f"  {rel}: exit {py_rc} (py) != {zg_rc} (zig)")
        if py_out != zg_out:
            off = _first_diff(py_out, zg_out)
            lines.append(
                f"  {rel}: bytes differ at offset {off} "
                f"(py {len(py_out)}B, zig {len(zg_out)}B)"
            )
            lines.append(f"     py : {py_out[max(0, off - 8):off + 24]!r}")
            lines.append(f"     zig: {zg_out[max(0, off - 8):off + 24]!r}")
    ok = mismatches == 0
    lines.insert(0, f"  {stage}: {'PASS' if ok else 'FAIL'} "
                    f"({len(files) - mismatches}/{len(files)} files byte-identical)")
    return ok, lines


def run() -> tuple[bool, list[str]]:
    """run_all.py entry point. Skips (passes) unless VAKEDC_ZIG is set."""
    zig_bin = os.environ.get("VAKEDC_ZIG")
    if not zig_bin:
        return True, ["  oracle: skipped (set VAKEDC_ZIG to enable)"]
    if not os.path.exists(zig_bin):
        return False, [f"  oracle: VAKEDC_ZIG set but not found: {zig_bin}"]
    if not ENABLED_STAGES:
        return True, ["  oracle: no stages enabled yet (none implemented in Zig)"]
    ok_all = True
    out: list[str] = []
    for stage in ENABLED_STAGES:
        ok, lines = diff_stage(stage, zig_bin)
        ok_all = ok_all and ok
        out.extend(lines)
    return ok_all, out


if __name__ == "__main__":
    zig_bin = os.environ.get("VAKEDC_ZIG")
    if not zig_bin:
        print("oracle: VAKEDC_ZIG not set; nothing to compare.")
        raise SystemExit(0)
    if len(sys.argv) != 2:
        print("usage: VAKEDC_ZIG=<bin> python3 tests/spec/oracle.py <stage>")
        raise SystemExit(2)
    stage = sys.argv[1]
    if stage not in STAGE_ARGS:
        print(f"oracle: unknown stage {stage!r}; known: {sorted(STAGE_ARGS)}")
        raise SystemExit(2)
    ok, lines = diff_stage(stage, zig_bin)
    print("\n".join(lines))
    raise SystemExit(0 if ok else 1)
