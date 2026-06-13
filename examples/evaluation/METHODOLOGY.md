# Evaluation Methodology & Claims Ledger

This document is the **honesty contract** for every performance and determinism
number cited in the Vaked paper, `CASE_STUDIES.md`, `BENCHMARK.md`, and the PR
comments. Its job is to make each claim reproducible and to label it clearly as
**Measured**, **Projected**, or **Retracted**. If a number appears in a paper
table but not in the ledger below, treat it as unverified.

It was added during the multi-round optimization pass on PR #103 after a fan-out
review found that the headline scaling numbers were not backed by the one real
data file (`baseline.json`), and that the 10,000-worker "timeout" was actually a
generator bug. See the PR's `REVIEW_MAP.md` for the full audit trail.

## 1. Environment

All numbers in this repo's evaluation were produced in the dev container, not on
the `vakedos` target host. Reproducers must record their own environment.

| Field | Value (this capture) |
|-------|----------------------|
| Compiler | `vakedc` (Python front-end), `python3 -m vakedc {parse,check,lower}` |
| Python | 3.11.15 |
| Cores used | 1 (vakedc is single-threaded; no parallel checking yet) |
| Timer | `time.perf_counter()` around a `subprocess` call (same as `bench.py`) |
| Reps | median of 3 unless noted (10k stages: 1 run) |
| Startup floor | every invocation pays a fixed **~50 ms** Python interpreter/import cost |

> **Measurement caveat.** Because each measurement shells out to a fresh
> interpreter, small examples are dominated by the ~50 ms startup floor. The
> per-stage parse/check/lower split is **not** independently isolated from this
> floor, so sub-100 ms numbers should be read as "startup-bound", not as the
> cost of the stage itself.

## 2. How to reproduce

```bash
# Small committed example (8 workers):
python3 -m vakedc check vaked/examples/swe-swarm-loadtest.vaked

# Large fixtures are generated, not committed:
make -C examples/evaluation loadtests          # writes the 1k + 10k fixtures
python3 -m vakedc lower vaked/examples/swe-swarm-10k-workers.vaked

# Full baseline + determinism oracle over all examples:
python3 examples/evaluation/bench.py --iterations 20 --json examples/evaluation/baseline.json
```

## 3. Claims ledger

Status legend: **M** = measured & reproducible here · **P** = projected/estimated
(not yet measured) · **R** = retracted (measurement contradicts the prior claim).

| # | Claim (as previously written) | Status | Reality / source |
|---|-------------------------------|--------|------------------|
| 1 | 8 workers: parse 83 / check 70 / lower 71 ms, deterministic, 0 diagnostics | **M** | `swe-swarm-loadtest.vaked`, median of 3 |
| 2 | 1024 workers: parse 385 / check 395 / lower 811 ms, checks clean | **M** | regenerate `--workers 1024`; median of 3 |
| 3 | 10,000 workers: parse 4.2 / check 4.3 / lower 16.3 s, 0 diagnostics, 10,007 artifacts, ~300 MB peak RSS | **M** | regenerate `--workers 10000`; single run |
| 4 | "10K workers: check **> 120 s timeout**; practical limit 5–10K fibers" | **R** | The 10k fixture did not parse (generator trailing-comma bug, fixed in this PR). Once valid it compiles end-to-end in **~25 s**. No timeout, no wall. |
| 5 | "Compiler scales **linearly** (O(n)) from 8 → 1024 workers" | **R** | `lower` time grows ~11× from 8→1024 workers and ~20× again from 1024→10000 — **super-linear**. `lower` is the real optimization target. |
| 6 | "64 workers: parse ~100 / check ~150 / lower ~200 ms" | **P** | never run; interpolated. Generate with `--workers 64` to measure. |
| 7 | Determinism: valid examples byte-identical across runs | **M** | `bench.py` determinism oracle + manual `lower` diff (sha256 stable) |
| 8 | "18/19 (or 19/19) examples deterministic over **100 iterations** (1900 total)" | **P** | `baseline.json` was recorded with **20** iterations, 19 example rows, and one row (`types/schema-constraints.vaked`) with `check=null` (a real prior failure). The 100-iteration / 1900-total figure is not what the committed data shows. Re-run with `--iterations 100` to substantiate, or cite 20. |
| 9 | `< 100 ms for typical declarations` | **M (narrow)** | true for the 3 small committed examples, but that is mostly the ~50 ms startup floor — not a scaling result. |

## 4. Known discrepancies to resolve before submission

- **10× conflict on `operator-field`.** The paper (§5.1) reports parse 68 / check
  60 / lower 63 **ms**; `BENCHMARK.md` reports the same example as 0.007 / 0.003 /
  0.012 **s** (7 / 3 / 12 ms). `baseline.json` (~60 ms) supports the paper. Until
  re-measured on a pinned machine, **trust `baseline.json`** and fix `BENCHMARK.md`.
- **swe-swarm rows are absent from `baseline.json`.** The 1k/10k numbers in §3
  above were captured ad hoc during this pass; fold them into `baseline.json`
  (run `bench.py` after `make loadtests`) so the headline numbers live in the
  measured artifact, not just prose.

## 5. What this demonstrates about the system

This methodology note is itself a data point for the "become a true research
project" thread: the discovery (10k "timeout" was a bug), the fix, the
re-measurement, and this ledger were produced in a single fan-out pass with
parallel review lanes cross-checking each other (see `REVIEW_MAP.md`). The
quality-control loop — *measure → contradict the claim → fix → re-measure →
record* — is the orchestration model the paper should describe, not just the
language.

## 6. Open gaps

- No machine metadata (CPU model, RAM, OS) is captured in `baseline.json`; add it.
- No fixed seed / warm-up policy is documented for the determinism oracle.
- The soundness argument for POLA enforcement is informal (no mechanized proof).
- The runtime (OTP + Zig daemons) is unimplemented; all numbers are compile-time.
