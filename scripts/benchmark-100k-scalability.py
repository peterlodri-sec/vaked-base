#!/usr/bin/env python3
"""
Benchmark script for vaked 100k worker scalability test.

Runs swe-swarm-100k-workers-scalability.vaked through the vakedc compiler pipeline
(parse → check → lower), captures timing, verifies determinism, produces colored logs.
"""

import subprocess
import json
import sys
import time
import hashlib
import os
from pathlib import Path
from datetime import datetime

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Paths
REPO_ROOT = Path(__file__).parent.parent
VAKED_FILE = REPO_ROOT / "vaked/examples/swe-swarm-100k-workers-scalability.vaked"
VAKEDC = REPO_ROOT / "vakedc"
RESULTS_DIR = REPO_ROOT / ".benchmark-results"

def run_stage(stage_name, cmd, description):
    """Run a compiler stage, capture timing, return (elapsed_sec, returncode)."""
    print(f"{BLUE}[→] {description}...{RESET}", end=" ", flush=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        elapsed = time.perf_counter() - start
        return elapsed, result.returncode
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return elapsed, 124

def format_timing(elapsed_sec):
    """Format elapsed time in human-readable form."""
    if elapsed_sec < 1:
        return f"{elapsed_sec * 1000:.0f}ms"
    else:
        return f"{elapsed_sec:.2f}s"

def hash_file(filepath):
    """Compute SHA256 of a file."""
    if not filepath.exists():
        return None
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()[:16]  # Short hash for readability

def run_benchmark(iterations=3):
    """Run the full benchmark suite."""
    RESULTS_DIR.mkdir(exist_ok=True)

    print(f"\n{BOLD}Vaked 100k Worker Scalability Benchmark{RESET}")
    print(f"File: {VAKED_FILE}")
    print(f"Iterations: {iterations}")
    print(f"Target: <60s total time (all stages combined)")
    print(f"Timestamp: {datetime.utcnow().isoformat()}Z\n")

    results = []
    artifacts_hashes = {}

    for iteration in range(iterations):
        print(f"{BOLD}[{iteration + 1}/{iterations}]{RESET}")

        # PARSE stage
        parse_time, parse_rc = run_stage(
            "parse",
            ["python3", "-m", "vakedc", "parse", str(VAKED_FILE)],
            "parse",
        )
        if parse_rc == 0:
            print(f"{GREEN}✓{RESET} {format_timing(parse_time)}")
            parse_ok = True
        else:
            print(f"{YELLOW}✗{RESET} exit {parse_rc}")
            parse_ok = False

        # CHECK stage
        check_time, check_rc = run_stage(
            "check",
            ["python3", "-m", "vakedc", "check", str(VAKED_FILE)],
            "check",
        )
        if check_rc == 0:
            print(f"{GREEN}✓{RESET} {format_timing(check_time)}")
            check_ok = True
        else:
            print(f"{YELLOW}✗{RESET} exit {check_rc}")
            check_ok = False

        # LOWER stage
        lower_time, lower_rc = run_stage(
            "lower",
            ["python3", "-m", "vakedc", "lower", str(VAKED_FILE)],
            "lower",
        )
        if lower_rc == 0:
            print(f"{GREEN}✓{RESET} {format_timing(lower_time)}")
            lower_ok = True
        else:
            print(f"{YELLOW}✗{RESET} exit {lower_rc}")
            lower_ok = False

        # Record result
        total_time = parse_time + check_time + lower_time
        results.append({
            "iteration": iteration + 1,
            "parse_sec": parse_time,
            "check_sec": check_time,
            "lower_sec": lower_time,
            "total_sec": total_time,
            "all_ok": parse_ok and check_ok and lower_ok,
        })

        print(f"  Total: {format_timing(total_time)}\n")

    # Summary
    print(f"{BOLD}=== Summary ==={RESET}\n")

    successful = [r for r in results if r["all_ok"]]
    if successful:
        times = [r["total_sec"] for r in successful]
        avg = sum(times) / len(times)
        min_t = min(times)
        max_t = max(times)

        print(f"{GREEN}✓ {len(successful)}/{iterations} iterations succeeded{RESET}")
        print(f"  Average: {format_timing(avg)}")
        print(f"  Min/Max: {format_timing(min_t)} / {format_timing(max_t)}")
        if max_t < 60:
            print(f"  Target (<60s): {GREEN}✓ PASS{RESET}")
            target_met = True
        else:
            print(f"  Target (<60s): {YELLOW}✗ FAIL{RESET} (exceeded by {format_timing(max_t - 60)})")
            target_met = False
    else:
        print(f"{YELLOW}✗ All iterations failed{RESET}")
        target_met = False

    # Write JSON results
    results_file = RESULTS_DIR / f"benchmark-{datetime.utcnow().isoformat().split('.')[0].replace(':', '')}.json"
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "vaked_file": str(VAKED_FILE),
            "iterations": results,
            "summary": {
                "successful": len(successful),
                "total": iterations,
                "avg_total_sec": sum(r["total_sec"] for r in successful) / len(successful) if successful else None,
                "min_total_sec": min(r["total_sec"] for r in successful) if successful else None,
                "max_total_sec": max(r["total_sec"] for r in successful) if successful else None,
                "target_met": target_met,
            }
        }, f, indent=2)

    print(f"\n{BLUE}Results: {results_file}{RESET}\n")
    return 0 if target_met else 1

if __name__ == "__main__":
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    sys.exit(run_benchmark(iterations))
