# Experiment — compiler compile-time LIMIT + agent concurrency cap

**Date:** 2026-06-14 · **Status:** measured (results below) · **Host:** macOS M1, 8 cores
**Harness:** [`tools/bench/compiler-limit.py`](../../../tools/bench/compiler-limit.py)

## Context

Two operational ceilings govern how hard this project can push its automation:
1. **Compiler LIMIT** — how large a `.vaked` program `vakedc` can compile before a
   stage exceeds a 30s budget (the practical interactive/CI ceiling).
2. **Agent concurrency cap** — how many subagents the Workflow engine runs at once.

This documents the theory for both and load-tests the compiler to find (1).

## Part 1 — compiler load test

### Method

`tools/bench/compiler-limit.py` generates a `.vaked` file of N unique top-level
`schema` decls (unique names → clean `check`, so timing is pure compile work, not
diagnostics), times `vakedc check` and `vakedc lower` (median of 3), fits the
empirical complexity exponent `k` between adjacent points (`t ∝ N^k`), and
interpolates the N where each stage crosses 30s. Reproduce:

```
python3 tools/bench/compiler-limit.py --runs 3 --threshold 30
```

### Results (median of 3, M1 8-core)

| N | KB | check_s | lower_s |
|---|---|---|---|
| 4000 | 182 | 0.28 | 0.97 |
| 8000 | 366 | 0.53 | 3.45 |
| 16000 | 739 | 1.03 | 12.96 |
| 20000 | 926 | 1.31 | 19.31 |
| 24000 | 1114 | 1.58 | 27.95 |

`lower` complexity exponents between adjacent points: **1.83, 1.91, 1.79, 2.03 → O(N²)**.

### Finding

- **`lower` is the binding stage and is superlinear (≈ O(N²))** — doubling N
  multiplies `lower` time by ~3–8×, while `check` stays near-linear at small N and
  only turns superlinear far later.
- **LIMIT (a stage > 30s):** `lower` at **N ≈ 25k decls (~1.16 MB)** — bracketed,
  not extrapolated: 24k = 27.95 s, 25k = 30.46 s, 26k = 32.22 s (idle host). `check`
  only crosses near **N ≈ 70k+**. So `lower`'s ~quadratic hot path is the real ceiling.
- **Measurement isolation matters (cross-experiment finding):** re-running the same
  26k/28k bracket *while the 24-agent probe (Part 2) saturated the CPU* gave
  26k = 112 s, 28k = 59 s — non-monotone garbage, `lower` inflated ~4×. The load test
  MUST run on an idle host; this is a live instance of the Part-1×Part-2 compounding
  below.
- **Why:** `check` was made near-linear by the #29 bisect fix (token-span lookups
  no longer scan every token). `lower` (`vakedc/lower.py`, ~100 KB) has no such
  fix and exhibits the same pre-#29 quadratic shape — a strong candidate for the
  same treatment. The #58 `eventd` O(n²)-append history is the same class of bug.

### Recommendation

Profile `vakedc/lower.py` for the O(N²) hot path (likely an inner scan over all
decls/nodes per decl, mirroring #29). A bisect/index fix would push the `lower`
30s LIMIT from ~20k toward `check`'s ~70k. File as a follow-up perf issue; this is
not a blocker for current program sizes (real Vaked files are << 1k decls).

## Part 2 — agent concurrency cap (measured + theory)

The Workflow engine caps **concurrent** `agent()` calls at:

```
N_concurrent = min(16, cpu_cores − 2)
```

- **This host (8 cores): N_concurrent = 6.** Excess agents queue and run as slots free.
- **Lifetime cap:** ≤ 1000 agents total per workflow (runaway backstop), and ≤ 4096
  items per single `parallel()` / `pipeline()` call.

### Measured (probe: `.claude/workflows/agent-concurrency-probe.js`)

Fanned out **24 agents** in one `parallel()`; each ran a single `time.sleep(6)`
between two epoch stamps and returned the interval. Max number of overlapping
sleep-windows = the real concurrent-slot count.

| metric | value |
|---|---|
| agents launched / returned | 24 / 24 |
| **max concurrent (overlapping intervals)** | **6** |
| matches `min(16, cores−2)` on 8 cores | ✅ 6 |
| wall span (24 agents) | 149.6 s |

**Cap = 6, confirmed empirically.** Note the 149.6 s wall for 24 × 6 s of *sleep*:
ideal at 6-wide would be ~24 s, so throughput is **per-agent-latency-bound** (LLM
spawn + reason + return ≫ the 6 s), not sleep-bound. Practical batch wall-clock ≈
`ceil(total / 6) × per_agent_latency`, where `per_agent_latency` (tens of seconds)
dominates — budget on that, not on the nominal task time.

### Why these numbers

- **`cpu_cores − 2`:** subagents are CPU- and context-bound; leaving 2 cores frees
  the orchestrator loop + OS so the machine doesn't thrash under oversubscription.
- **`min(…, 16)`:** a hard ceiling bounds peak memory and model-API rate regardless
  of core count — a 64-core box still caps at 16 concurrent to avoid rate-limit
  storms and runaway spend.
- **Consequence for batches:** a "30–40 agent" batch is not 30–40 *simultaneous* —
  it's ≤ 6 here at any instant, the rest queued. Wall-clock ≈ (total_agents / 6) ×
  per-agent time. Plan fan-out width against `N_concurrent`, not the total.

### The two limits interact

A batch that has each agent invoke `vakedc lower` on a large program multiplies the
Part-1 cost by the queue depth. With `lower` superlinear, the safe regime is
**small programs × ≤6 concurrent**; large programs should be compiled once and the
artifact shared, not recompiled per agent.

## Reproduce / extend

```
python3 tools/bench/compiler-limit.py --ns 4000,8000,16000,20000,24000 --json limits.json
```
Numbers are machine-specific (CPU-bound) — always record the host core count.
