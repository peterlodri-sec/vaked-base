#!/usr/bin/env python3
"""compiler-limit — find the vakedc compile-time LIMIT (the N where a stage > THRESHOLD).

Generates `.vaked` files of growing top-level decl-count N (unique names → clean
check, so timing reflects real work, not diagnostics), times `vakedc check` and
`vakedc lower` (median of K runs), fits the empirical complexity exponent between
adjacent points, and reports the N where each stage crosses THRESHOLD seconds.

Usage:
    python3 tools/bench/compiler-limit.py [--threshold 30] [--runs 3] \
        [--ns 1000,4000,8000,16000,20000] [--json out.json]

Run from the repo root (needs the vakedc package + vaked/schema/builtins.vaked).
Pure stdlib; no deps. CPU-bound — numbers are machine-specific (record the host).
"""
import argparse, json, math, os, shutil, subprocess, sys, tempfile, time


def gen(n: int) -> str:
    # N unique top-level schema decls. Unique names avoid the #25 name-collision
    # diagnostic, so `check` returns clean and the timing is pure compile work.
    return "\n".join(
        f"schema s{i} {{ field f : String {{ nonempty }} }}" for i in range(n)
    )


def median(xs):
    xs = sorted(xs)
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def time_cmd(cmd, runs):
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True)
        ts.append(time.perf_counter() - t)
    return median(ts), r.returncode


def crossing(points, threshold):
    """First N where time > threshold, interpolated on the local power law."""
    for i in range(1, len(points)):
        (n0, t0), (n1, t1) = points[i - 1], points[i]
        if t0 <= threshold < t1 and t0 > 0:
            k = math.log(t1 / t0) / math.log(n1 / n0)  # local exponent
            return round(n0 * (threshold / t0) ** (1 / k))
    return None


def exponents(points):
    out = []
    for i in range(1, len(points)):
        (n0, t0), (n1, t1) = points[i - 1], points[i]
        if t0 > 0:
            out.append((n1, math.log(t1 / t0) / math.log(n1 / n0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=30.0)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--ns", default="1000,4000,8000,16000,20000")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    ns = [int(x) for x in a.ns.split(",")]

    tmp = tempfile.mkdtemp(prefix="ailish-bench-")
    check, lower = [], []
    print(f"host cores={os.cpu_count()}  runs={a.runs}  threshold={a.threshold}s")
    print(f"{'N':>8} {'KB':>7} {'check_s':>9} {'lower_s':>9}")
    try:
        for n in ns:
            p = os.path.join(tmp, f"L_{n}.vaked")
            open(p, "w").write(gen(n))
            kb = os.path.getsize(p) // 1024
            ct, _ = time_cmd(["python3", "-m", "vakedc", "check", p], a.runs)
            out = os.path.join(tmp, f"out_{n}")
            lt, _ = time_cmd(["python3", "-m", "vakedc", "lower", p, "--out", out], a.runs)
            shutil.rmtree(out, ignore_errors=True)
            check.append((n, ct)); lower.append((n, lt))
            print(f"{n:>8} {kb:>7} {ct:>9.2f} {lt:>9.2f}")
            if lt > a.threshold and ct > a.threshold:
                break
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    res = {
        "cores": os.cpu_count(), "threshold_s": a.threshold, "runs": a.runs,
        "check": check, "lower": lower,
        "check_exponents": exponents(check), "lower_exponents": exponents(lower),
        "check_limit_N": crossing(check, a.threshold),
        "lower_limit_N": crossing(lower, a.threshold),
    }
    print(f"\nLIMIT (compile > {a.threshold}s):  check N≈{res['check_limit_N']}  "
          f"lower N≈{res['lower_limit_N']}  (lower is the binding stage)")
    print("lower exponents (≈complexity):",
          ", ".join(f"{n}:{k:.2f}" for n, k in res["lower_exponents"]))
    if a.json:
        json.dump(res, open(a.json, "w"), indent=2)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
