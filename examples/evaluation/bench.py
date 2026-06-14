#!/usr/bin/env python3
"""bench.py — Vaked compiler benchmarking and determinism oracle.

Measures:
1. Single-run performance (parse/check/lower time, memory)
2. Determinism oracle (repeated compiles → identical artifacts)
3. Artifact footprint (output sizes)

Usage:
  python3 examples/evaluation/bench.py [--example GLOB] [--iterations N] [--json PATH] [--verbose]
"""

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent
EXAMPLES_DIR = REPO_ROOT / "vaked" / "examples"


def run_vakedc(*args, check=True) -> Tuple[int, str, str]:
    """Run vakedc and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, "-m", "vakedc", *args]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def measure_single_run(example_path: Path) -> Dict:
    """Measure parse, check, and lower times for a single example."""
    results = {}

    # Parse
    start = time.perf_counter()
    exit_code, _, stderr = run_vakedc("parse", str(example_path), "--print")
    elapsed_parse = time.perf_counter() - start
    results["parse_time"] = elapsed_parse
    if exit_code != 0:
        results["parse_error"] = stderr
        return results

    # Check
    start = time.perf_counter()
    exit_code, _, stderr = run_vakedc("check", str(example_path), "--json")
    elapsed_check = time.perf_counter() - start
    results["check_time"] = elapsed_check
    if exit_code != 0:
        results["check_error"] = stderr

    # Lower (includes parse + check + lower)
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmpdir:
        exit_code, _, stderr = run_vakedc("lower", str(example_path), "--out", tmpdir)
        elapsed_lower = time.perf_counter() - start

        if exit_code == 0:
            # Measure artifact sizes
            total_size = 0
            artifacts = {}
            for root, dirs, files in os.walk(tmpdir):
                for fname in files:
                    fpath = Path(root) / fname
                    size = fpath.stat().st_size
                    rel = fpath.relative_to(tmpdir)
                    artifacts[str(rel)] = size
                    total_size += size
            results["artifact_sizes"] = artifacts
            results["total_artifact_size"] = total_size
        else:
            results["lower_error"] = stderr

    results["lower_time"] = elapsed_lower
    return results


def measure_determinism(example_path: Path, iterations: int = 100) -> Dict:
    """Run vakedc lower N times and verify byte-identical output."""
    hashes = []
    timings = []
    errors = []

    for i in range(iterations):
        start = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, _, stderr = run_vakedc("lower", str(example_path), "--out", tmpdir)

            if exit_code != 0:
                errors.append((i, stderr))
                continue

            # Hash all artifacts + provenance
            hash_obj = hashlib.sha256()
            for root, dirs, files in os.walk(tmpdir):
                for fname in sorted(files):
                    fpath = Path(root) / fname
                    with open(fpath, "rb") as f:
                        hash_obj.update(f.read())
            hashes.append(hash_obj.hexdigest())

        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    results = {
        "iterations": iterations,
        "unique_hashes": len(set(hashes)),
        "deterministic": len(set(hashes)) == 1,
        "timings": timings,
        "errors": errors,
    }

    if timings:
        results["timing_mean"] = sum(timings) / len(timings)
        results["timing_min"] = min(timings)
        results["timing_max"] = max(timings)

    return results


def find_examples(pattern: str = "*.vaked") -> List[Path]:
    """Find all .vaked examples matching pattern."""
    all_examples = sorted(EXAMPLES_DIR.glob(f"**/{pattern}"))
    return [ex for ex in all_examples if ex.is_file()]


def format_bytes(size: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def main():
    parser = argparse.ArgumentParser(
        description="Vaked compiler benchmarking and determinism oracle."
    )
    parser.add_argument(
        "--example",
        default="*.vaked",
        help="Glob pattern for examples to benchmark (default: *.vaked)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Determinism oracle iterations (default: 100)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-iteration timing"
    )
    parser.add_argument(
        "--json",
        help="Write JSON results to this path",
    )

    args = parser.parse_args()

    examples = find_examples(args.example)
    if not examples:
        print(f"No examples found matching {args.example}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(examples)} example(s)")
    print()

    all_results = {}

    for example in examples:
        rel_path = example.relative_to(EXAMPLES_DIR)
        print(f"Benchmarking {rel_path}...")

        # Single-run performance
        single_results = measure_single_run(example)
        print(f"  Parse:  {single_results.get('parse_time', 0):.3f}s")
        print(f"  Check:  {single_results.get('check_time', 0):.3f}s")
        print(f"  Lower:  {single_results.get('lower_time', 0):.3f}s")

        if "total_artifact_size" in single_results:
            total_size = single_results["total_artifact_size"]
            print(f"  Artifacts: {format_bytes(total_size)}")

        # Determinism oracle
        print(f"  Running determinism oracle ({args.iterations} iterations)...")
        determ_results = measure_determinism(example, iterations=args.iterations)

        if determ_results["deterministic"]:
            print(f"    ✓ Deterministic (all {args.iterations} iterations identical)")
        else:
            print(
                f"    ✗ NOT deterministic ({determ_results['unique_hashes']} unique hashes)"
            )

        if determ_results["timings"]:
            mean = determ_results["timing_mean"]
            min_t = determ_results["timing_min"]
            max_t = determ_results["timing_max"]
            print(f"    Timing: {mean:.3f}s (min {min_t:.3f}s, max {max_t:.3f}s)")

        all_results[str(rel_path)] = {
            "single_run": single_results,
            "determinism": determ_results,
        }
        print()

    # Summary table
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"{'Example':<30} {'Parse':<10} {'Check':<10} {'Lower':<10}")
    print("-" * 70)
    for example, results in sorted(all_results.items()):
        sr = results["single_run"]
        parse_t = sr.get("parse_time", 0)
        check_t = sr.get("check_time", 0)
        lower_t = sr.get("lower_time", 0)
        print(f"{example:<30} {parse_t:>7.3f}s  {check_t:>7.3f}s  {lower_t:>7.3f}s")

    # Determinism summary
    print()
    print("Determinism:")
    det_count = sum(
        1 for r in all_results.values() if r["determinism"]["deterministic"]
    )
    print(f"  {det_count}/{len(all_results)} examples deterministic")

    # Write JSON if requested
    if args.json:
        with open(args.json, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults written to {args.json}")


if __name__ == "__main__":
    main()
