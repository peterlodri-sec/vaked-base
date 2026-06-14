#!/usr/bin/env python3
"""ARP fine-tuning dataset harness — validate + generate.

This tool maintains `arp-examples.jsonl`, the seed dataset for fine-tuning a
model to emit ARP (Agent Register Protocol, RFC 0009) graphs: a validated
AI-lish V1 core (see docs/ailish/2026-06-14-ailish-v1-rfc.md) with the four
ARP behavioral primitives interleaved.

Two subcommands:

  validate   For each row: (a) strip the ARP primitives from `arp` and assert
             the result equals `ail_v1`; (b) run the `ailishcheck` binary on
             `ail_v1` and collect pass/fail. Prints a summary table; exits
             nonzero if any row fails either check.

  gen        Render a record from a `(problem, state, solution, frames)` spec,
             derive `arp` by inserting STRIDE/T/BRANCH lines and appending
             valence tokens, build `read`, VALIDATE it via ailishcheck, and
             append to the JSONL only if valid. This is the "keep generating"
             entry point: add specs to SPECS and re-run.

Stdlib only: json, subprocess, tempfile, re, argparse (+ os, sys, pathlib).

The four ARP behavioral primitives (RFC 0009 section 2), advisory and NOT part
of the AI-lish V1 grammar:
  Stride   [STRIDE: a -> b -> c]   declared progress arc, emitted before acting
  Tension  [T:N]  N in 0..100      goal-distance; high early, low as it converges
  Valence  [+]/[-]/[!]             polarity emitted AFTER a tool result
  Branch   [BRANCH: a | b; condition: X]   explicit fork / retry checkpoint
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_JSONL = HERE / "arp-examples.jsonl"

# ---------------------------------------------------------------------------
# ARP primitive recognisers (used by the strip round-trip)
# ---------------------------------------------------------------------------

# A line that is SOLELY one of these primitives is removed entirely.
STRIDE_RE = re.compile(r"^\s*\[STRIDE:[^\]]*\]\s*$")
TENSION_RE = re.compile(r"^\s*\[T:\d+\]\s*$")
BRANCH_RE = re.compile(r"^\s*\[BRANCH:[^\]]*\]\s*$")
# A trailing valence token on an otherwise-V1 line is stripped.
VALENCE_TRAIL_RE = re.compile(r"\s*\[(?:\+|-|!)\]\s*$")


def strip_arp(arp: str) -> str:
    """Reduce an ARP graph to its AI-lish V1 core.

    Removes lines that are solely [STRIDE: ...], [T:N], or [BRANCH: ...], and
    strips a trailing [+]/[-]/[!] valence token from any remaining line. Blank
    lines are dropped so the result compares cleanly against `ail_v1`.
    """
    out: list[str] = []
    for line in arp.splitlines():
        if STRIDE_RE.match(line) or TENSION_RE.match(line) or BRANCH_RE.match(line):
            continue
        line = VALENCE_TRAIL_RE.sub("", line)
        if line.strip():
            out.append(line.rstrip())
    return "\n".join(out)


def normalize_core(s: str) -> str:
    """Normalise an `ail_v1` string for comparison: drop blank lines and
    trailing whitespace (the round-trip is modulo blanks and trailing ws)."""
    return "\n".join(l.rstrip() for l in s.splitlines() if l.strip())


# ---------------------------------------------------------------------------
# Locating / building the ailishcheck binary
# ---------------------------------------------------------------------------

def _candidate_binaries() -> list[Path]:
    """Plausible locations for the prebuilt `ailishcheck` binary.

    Primary location is `../ailish/target/debug/ailishcheck` relative to this
    file. Because `target/` is gitignored, a git worktree may not carry it; in
    that case we also probe ancestor checkouts that share the same
    `tools/ailish/` source tree, and honour an `AILISHCHECK_BIN` override.
    """
    cands: list[Path] = []
    env = os.environ.get("AILISHCHECK_BIN")
    if env:
        cands.append(Path(env))
    cands.append(HERE.parent / "ailish" / "target" / "debug" / "ailishcheck")
    p = HERE
    seen = set()
    for _ in range(10):
        p = p.parent
        if p in seen:
            break
        seen.add(p)
        cand = p / "tools" / "ailish" / "target" / "debug" / "ailishcheck"
        if cand not in cands:
            cands.append(cand)
    return cands


def resolve_ailishcheck(build_if_missing: bool = True) -> Path:
    """Return a path to a working `ailishcheck` binary, building it if needed."""
    for c in _candidate_binaries():
        if c.is_file() and os.access(c, os.X_OK):
            return c
    if not build_if_missing:
        raise FileNotFoundError("ailishcheck binary not found")
    crate = HERE.parent / "ailish"
    print(f"ailishcheck not found; building in {crate} ...", file=sys.stderr)
    subprocess.run(
        ["cargo", "build", "--bin", "ailishcheck", "--locked"],
        cwd=crate,
        check=True,
    )
    built = crate / "target" / "debug" / "ailishcheck"
    if not built.is_file():
        raise FileNotFoundError(f"build did not produce {built}")
    return built


def ailishcheck_ok(binary: Path, core: str) -> tuple[bool, str]:
    """Write `core` to a temp file and run ailishcheck. Returns (ok, output)."""
    with tempfile.NamedTemporaryFile("w", suffix=".ail", delete=False) as tf:
        tf.write(core)
        tf.write("\n")
        path = tf.name
    try:
        proc = subprocess.run([str(binary), path], capture_output=True, text=True)
        out = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, out
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# validate subcommand
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    jsonl = Path(args.jsonl)
    if not jsonl.is_file():
        print(f"error: {jsonl} not found", file=sys.stderr)
        return 2
    binary = resolve_ailishcheck()
    rows = []
    with jsonl.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rows.append((i, json.loads(line)))

    print(f"ailishcheck: {binary}")
    print(f"validating {len(rows)} rows from {jsonl}\n")
    header = f"{'id':38} {'strip':>6} {'ailishcheck':>12}"
    print(header)
    print("-" * len(header))

    failures = 0
    for _, rec in rows:
        rid = rec.get("id", "?")
        # (a) ARP-strip round trip: strip(arp) must reproduce ail_v1.
        stripped = strip_arp(rec["arp"])
        want = normalize_core(rec["ail_v1"])
        strip_ok = stripped == want
        # (b) ailishcheck on the V1 core (parse + guardrail).
        check_ok, out = ailishcheck_ok(binary, rec["ail_v1"])
        if not (strip_ok and check_ok):
            failures += 1
        print(f"{rid:38} {'PASS' if strip_ok else 'FAIL':>6} "
              f"{'PASS' if check_ok else 'FAIL':>12}")
        if not strip_ok:
            print("    strip round-trip mismatch:")
            print("    --- stripped(arp) ---")
            for l in stripped.splitlines():
                print(f"    | {l}")
            print("    --- ail_v1 ---")
            for l in want.splitlines():
                print(f"    | {l}")
        if not check_ok:
            print(f"    ailishcheck: {out}")

    print("-" * len(header))
    print(f"{len(rows) - failures}/{len(rows)} rows pass "
          f"(strip round-trip + ailishcheck)")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# gen subcommand — template-based emitter
# ---------------------------------------------------------------------------
#
# A spec is a dict describing a record. `frames` is the AI-lish V1 core as a
# list of frame dicts; each frame renders to one or more lines. The emitter:
#   1. renders `ail_v1` from `frames`,
#   2. derives `arp` by interleaving the spec's ARP annotations,
#   3. builds the natural-language `read` from problem/state/solution clauses,
#   4. validates `ail_v1` via ailishcheck,
#   5. appends to the JSONL only if valid.
#
# A frame spec:
#   {"reg": "R:tool",
#    "lines": [
#       {"text": '%0 = fetch(remote="origin")', "valence": "+"},
#       {"text": "%1 = read(path=log.txt)"},
#    ]}
# `valence` (optional) appends a [+]/[-]/[!] token to that line in `arp` only.
#
# Top-level ARP annotations on the spec:
#   "stride":   list[str]            -> "[STRIDE: a -> b -> c]" before frame 0
#   "tensions": {line_index: N}      -> a [T:N] line before that global line
#   "branches": {line_index: "a | b; condition: X"} -> [BRANCH: ...] before line
# `line_index` is 0-based over all rendered lines across every frame.


def render_core(frames: list[dict]) -> str:
    """Render the AI-lish V1 core (no ARP primitives) from a frames spec."""
    out: list[str] = []
    for fr in frames:
        reg = f"[{fr['reg']}]"
        for j, ln in enumerate(fr["lines"]):
            prefix = reg + " " if j == 0 else " " * (len(reg) + 1)
            out.append(prefix + ln["text"])
    return "\n".join(out)


def render_arp(spec: dict) -> str:
    """Render the dense ARP graph: the core plus interleaved primitives.

    The result, passed through strip_arp(), reproduces render_core(frames).
    """
    frames = spec["frames"]
    stride = spec.get("stride")
    tensions = spec.get("tensions", {})
    branches = spec.get("branches", {})

    rendered: list[str] = []
    for fr in frames:
        reg = f"[{fr['reg']}]"
        for j, ln in enumerate(fr["lines"]):
            prefix = reg + " " if j == 0 else " " * (len(reg) + 1)
            text = prefix + ln["text"]
            if ln.get("valence"):
                text = f"{text} [{ln['valence']}]"
            rendered.append(text)

    out: list[str] = []
    if stride:
        out.append("[STRIDE: " + " → ".join(stride) + "]")
    for idx, text in enumerate(rendered):
        if idx in tensions:
            out.append(f"[T:{tensions[idx]}]")
        if idx in branches:
            out.append(f"[BRANCH: {branches[idx]}]")
        out.append(text)
    return "\n".join(out)


def build_read(spec: dict) -> str:
    """One-paragraph natural-language gloss: problem -> state -> solution."""
    return (
        f"The problem was {spec['problem_clause']} "
        f"The state was {spec['state_clause']} "
        f"The solution was {spec['solution_clause']}"
    )


def render_record(spec: dict) -> dict:
    core = render_core(spec["frames"])
    arp = render_arp(spec)
    # Self-check the round trip before we even hit ailishcheck.
    assert strip_arp(arp) == normalize_core(core), (
        f"spec {spec['id']}: render_arp does not strip back to render_core"
    )
    return {
        "id": spec["id"],
        "title": spec["title"],
        "difficulty": spec["difficulty"],
        "tags": spec["tags"],
        "problem": spec["problem"],
        "state": spec["state"],
        "solution": spec["solution"],
        "ail_v1": core,
        "arp": arp,
        "read": build_read(spec),
    }


# Extension point: add spec dicts here and re-run `gen` to keep generating.
SPECS: list[dict] = [
    {
        "id": "arp-009-flaky-ci-rerun",
        "title": "Flaky CI: a transient network failure cleared on rerun, then a clean merge",
        "difficulty": "exciting",
        "tags": ["ci", "flaky-test", "rerun", "R:risk", "R:commit"],
        "problem": "A CI run failed on a transient network timeout, not a real regression.",
        "state": "The red check blocked the merge even though the failure was non-deterministic infrastructure noise.",
        "solution": "Diagnose the failure as transient, rerun CI to a clean pass, then merge.",
        "problem_clause": "a CI run that failed on a transient network timeout rather than a real regression.",
        "state_clause": "a red check blocking the merge despite the failure being non-deterministic infrastructure noise.",
        "solution_clause": "to diagnose the failure as transient, rerun CI to a clean pass, and then merge.",
        "stride": ["read_ci_log", "diagnose_transient", "rerun_ci", "merge"],
        "tensions": {0: 70, 6: 15},
        "branches": {2: "treat_as_regression | rerun_as_transient; condition: failure_is_network_timeout"},
        "frames": [
            {"reg": "R:tool", "lines": [
                {"text": '%0 = read(path=ci/run.log)', "valence": "-"},
            ]},
            {"reg": "R:risk", "lines": [
                {"text": '%1 = check_permission(verb="merge", tool=`gh`) ; state="ci_red"', "valence": "-"},
                {"text": '%2 = block(action="merge_on_red", reason="ci_failed")'},
            ]},
            {"reg": "R:think", "lines": [
                {"text": '%3 = combine(%0, %1)'},
            ]},
            {"reg": "R:bench", "lines": [
                {"text": '%4 = test(target=%3) ; pass=12, rerun=true', "valence": "+"},
                {"text": 'gate(ci:pass) ∵ %4'},
            ]},
            {"reg": "R:artifact", "lines": [
                {"text": 'gate(no_cjk:pass) ∵ %3'},
            ]},
            {"reg": "R:commit", "lines": [
                {"text": '%5 = merge(pr=210) ∵ %4', "valence": "+"},
            ]},
        ],
    },
]


def cmd_gen(args: argparse.Namespace) -> int:
    jsonl = Path(args.jsonl)
    binary = resolve_ailishcheck()
    existing_ids = set()
    if jsonl.is_file():
        with jsonl.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_ids.add(json.loads(line)["id"])

    appended = 0
    for spec in SPECS:
        if spec["id"] in existing_ids:
            print(f"skip   {spec['id']} (already in dataset)")
            continue
        rec = render_record(spec)
        ok, out = ailishcheck_ok(binary, rec["ail_v1"])
        if not ok:
            print(f"INVALID {spec['id']}: {out}", file=sys.stderr)
            continue
        with jsonl.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        existing_ids.add(spec["id"])
        appended += 1
        print(f"append {spec['id']} (ailishcheck PASS)")

    print(f"\nappended {appended} new valid record(s) to {jsonl}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="validate every row (strip round-trip + ailishcheck)")
    pv.add_argument("--jsonl", default=str(DEFAULT_JSONL))
    pv.set_defaults(func=cmd_validate)

    pg = sub.add_parser("gen", help="render specs, validate, and append valid rows")
    pg.add_argument("--jsonl", default=str(DEFAULT_JSONL))
    pg.set_defaults(func=cmd_gen)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
