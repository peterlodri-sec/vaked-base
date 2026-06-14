# Vaked compiler scalability — analysis v0.1

> Status: **MEASURED.** A controlled multi-point sweep ran on GitHub Actions
> (`ubuntu-latest`, Python 3.12) via the `scalability-sweep` workflow. The sweep
> found a **super-linear `lower` stage**, the root cause was isolated to a single
> O(N²) pass (`enrich_graph` → `_node_for_chain`), a fix was applied, and the
> **same sweep was re-run to confirm the curve dropped to linear.** Both curves
> are committed (`scalability-curve-before.csv`, `scalability-curve-after.csv`).
> Numbers below are GHA medians, not the dev machine (repo rule: NEVER BUILD ON
> DEVELOPER MACHINE).

This document establishes a *credibility-grade* scalability curve for the
`vakedc` front-end (`parse → check → lower`). It exists because the project's
headline claim — "100k workers verified (273ms avg, deterministic)" — and the
credibility review's adverse observations ("1.6s @ 1024", "25s @ 10k") were
**not** produced by a controlled, multi-point sweep. This analysis replaces the
single-point anecdote with a method, a harness, a measured curve, and a fix that
the before/after curve justifies.

**Bottom line:** the review was right that growth was super-linear — but the
suspected cause (`_children_of`, §3.2) was **not** it. The measurement refuted
the original O(n log n) prediction (§3.3, now corrected), root-causing pointed at
an unanalyzed pre-emit pass, and indexing that pass took `lower` from an
empirical slope of **~1.7→2.0 (quadratic)** to **~1.0 (linear)**, turning a
N=100 000 compile that **exceeded the 40-minute CI wall** into a 70-second one.

---

## 1. Methodology

### 1.1 Input — synthetic flat architecture

The sweep does **not** use the committed `vaked/examples/swe-swarm-100k-workers-scalability.vaked`.
That file is a stub: its header describes 100k workers, but the body declares
only a handful of representative `node`s with `# ... omitted ...` comments. It
cannot measure scaling — there is nothing at scale in it.

Instead, `scripts/benchmark-scalability-sweep.py` **generates** a deterministic,
self-contained flat-architecture source for each size `N`:

```
use "./engine.vaked"           # sidecar the harness writes; defines `engine zigDaemon`

runtime "scale-sweep" {
  systems = ["x86_64-linux"]
  stream workIn { source = agentpipe.transcripts; type = Agent.Transcript; retention = 7d }

  fiber worker00001 { engine = zigDaemon; input = stream.workIn; output = artifacts.w00001 }
  ... N of them ...
  fiber aggregatorA { engine = zigDaemon; input = stream.workIn; output = artifacts.aggA }
  fiber aggregatorB { engine = zigDaemon; input = stream.workIn; output = artifacts.aggB }
}
```

- **1 runtime · 1 stream · N worker fibers · 2 aggregator fibers.** Every fiber
  shares the single stream as `input` and emits one distinct artifact.
- **Flat, not nested:** the runtime's `contains` fan-out is exactly `N + 2`
  fibers + 1 stream. No `mesh`, no `workflow`, no deep nesting. This isolates the
  **runtime-decomposition / graph-enrichment** cost from the *other* potentially
  quadratic path (the per-workflow scan; see §3.4).
- **Deterministic & hermetic:** `generate_synthetic_vaked(n)` is a pure function
  of `n` — byte-identical output for a given N, no clock, no RNG, no network. This
  is why the curve is reproducible.

The generated source **parses, checks, and lowers with zero diagnostics**.
Lowering it produces `flake.nix`, `gen/RUNTIME.md`, and one `gen/zig/<fiber>.json`
per fiber.

### 1.2 N range, iterations, environment

| Parameter | Value |
|-----------|-------|
| N (worker fibers) | {100, 1000, 10000, 30000, 100000} |
| Iterations K per N | 3 (median reported; sufficient — the curve is smooth and the effect is >4×) |
| Stages timed | `parse`, `check`, `lower` (each a separate `python3 -m vakedc <stage>` subprocess) |
| Aggregation | per-stage **median** across K clean iterations; `min` also recorded |
| Host | GitHub Actions `ubuntu-latest`, Python 3.12, vakedc stdlib-only (no install) |

Five N spanning three decades give a log-log line with enough points to read a
slope and watch it bend (§3). Note the original run used the doc's default
{100, 1000, 10000, 100000} × K=10; at N=100 000 the **pre-fix** pipeline blew the
40-minute job wall (the super-linear `lower`, §3.3), which is itself the first
hard datum. The reported curves use K=3 and add N=30 000 so the bend is visible
and 100 000 completes within budget.

### 1.3 How to run it

The `scalability-sweep` workflow (`.github/workflows/scalability-sweep.yml`,
`workflow_dispatch`, inputs `sizes` / `iters`) runs:

```bash
PYTHONPATH=. python3 scripts/benchmark-scalability-sweep.py \
    --sweep --sizes <csv> --iters <K> --out artifacts/scalability-curve.csv
```

and uploads `scalability-curve.{csv,json}` as an artifact. The generator alone is
dev-safe for inspection:
`python3 scripts/benchmark-scalability-sweep.py --emit-only --n 1000 --out /tmp/x.vaked`.

> **Why GHA, not the dev machine?** N=100 000 emits a ~3–4 MB source file, builds a
> ~100k-node graph, and runs the whole pipeline K×. That is squarely a "build"
> under the project rule.

---

## 2. Results

Per-stage wall-clock, **median of K=3 iterations**, GHA `ubuntu-latest` / Python 3.12.
The two curves are committed alongside this doc:
`scalability-curve-before.csv` (pre-fix) and `scalability-curve-after.csv` (post-fix).

### 2.1 Before the fix — `lower` is super-linear

| N (workers) | fibers | parse (ms) | check (ms) | lower (ms) | total (ms) |
|-------------|--------|-----------|-----------|-----------|-----------|
| 100 | 102 | 79.7 | 89.7 | 123.1 | 328.2 |
| 300 | 302 | 115.8 | 123.1 | 213.5 | 449.9 |
| 1 000 | 1 002 | 246.5 | 249.8 | 653.1 | 1 149.1 |
| 3 000 | 3 002 | 635.1 | 621.6 | 2 242.9 | 3 494.8 |
| 10 000 | 10 002 | 2 145.9 | 2 041.4 | 13 537.0 | 17 702.7 |
| 30 000 | 30 002 | 6 774.5 | 6 545.2 | 89 985.0 | 103 403.8 |
| 100 000 | 100 002 | — | — | **DNF** | **DNF** (exceeded the 40-min CI wall) |

`parse` and `check` track linearly. `lower` does not: between N=10 000 and
N=30 000 (a 3× step) it grows **6.65×**, an empirical slope of **1.72**, and the
slope *rises* with N (1.12 → 1.21 → 1.49 → 1.72 across successive segments) —
the signature of an O(N²) term overtaking a linear one. Extrapolating the slope
puts the N=100 000 `lower` near ~700 s, consistent with the observed 40-minute
timeout.

### 2.2 After the fix — all three stages linear

| N (workers) | fibers | parse (ms) | check (ms) | lower (ms) | total (ms) |
|-------------|--------|-----------|-----------|-----------|-----------|
| 100 | 102 | 110.1 | 98.2 | 220.4 | 416.3 |
| 1 000 | 1 002 | 262.8 | 260.8 | 651.3 | 1 175.0 |
| 10 000 | 10 002 | 2 307.9 | 2 193.6 | 6 961.0 | 11 429.1 |
| 30 000 | 30 002 | 7 408.3 | 6 842.3 | 20 599.6 | 34 811.6 |
| 100 000 | 100 002 | 24 972.6 | 23 615.6 | **70 294.7** | 118 883.0 |

`lower` now grows **10.1×** from N=10 000 to N=100 000 (a 10× step) — an empirical
slope of **1.00**. N=100 000 **completes in ~70 s** (was: did-not-finish in 40 min).

### 2.3 Before vs after at shared N (the fix's effect)

| N | `lower` before (ms) | `lower` after (ms) | speedup |
|---|--------------------|--------------------|---------|
| 1 000 | 653.1 | 651.3 | 1.00× (quadratic term negligible here) |
| 10 000 | 13 537.0 | 6 961.0 | 1.94× |
| 30 000 | 89 985.0 | 20 599.6 | **4.37×** |
| 100 000 | DNF (~700 s est.) | 70 294.7 | **DNF → 70 s** |

The speedup **grows with N** — exactly what removing an O(N²) term (and leaving
the O(N) remainder) predicts: at N=1 000 the quadratic term is invisible; by
N=30 000 it dominated 77% of `lower`'s time.

**Constant-offset caveat:** each stage is a separate Python process, so every cell
carries a fixed interpreter-startup + import cost (~50–75 ms, visible as the N=100
floor). It dominates the N=100 row and partly N=1 000; the slope is read from the
**large-N** end (N≥10 000), where the algorithmic term has overtaken the offset.

---

## 3. Complexity analysis — prediction, refutation, root cause

### 3.1 Reading the log-log slope

Plot `log(stage_ms)` against `log(N)`; the **slope is the empirical complexity
exponent**. Between a 10× step in N: a linear stage rises ~10×; a quadratic stage
~100×. That ratio is the single most important number this sweep produces.

| Slope (large-N end) | Reading |
|---------------------|---------|
| ≈ **1.0** | O(n) — linear. The measured post-fix `lower`, and `parse`/`check` throughout. |
| ≈ **1.0–1.2** | O(n log n) — a repeated-sort term showing through. Healthy. |
| ≈ **1.7–2.0** | super-linear / quadratic — the measured **pre-fix `lower`**. |

### 3.2 The original suspicion — `_children_of` — was wrong

The first draft of this analysis fingered `_children_of` (`vakedc/lower.py`), an
O(E) full-edge scan with no adjacency index, called via `_runtime_view`. That code
*is* wasteful (it re-copies and re-scans the edge list), but the measurement shows
it is **not** the super-linear term: `_runtime_view` calls `_children_of` a small
constant number of times per `lower` (once per firing emitter; ~3–4 for the flat
arch), so its total cost is O(n log n) with a small constant — a *constant-factor*
inefficiency, not a complexity-class regression. **Fixing it would not have moved
the curve.** This is exactly why the prediction had to be checked against a
measurement rather than shipped.

### 3.3 What the measurement actually found — `enrich_graph`

`vakedc lower` runs the full pipeline `parse → resolve → check → lower`, and just
before emitting it runs **`enrich_graph(graph, items)`** (`lower.py`), a pass that
re-attaches config sub-blocks (e.g. a fiber's `policy { … }`) the minimal resolver
drops. That pass was the O(N²):

```python
def enrich_graph(graph, items):
    def walk(decl, chain):
        node = _node_for_chain(graph, chain)   # called once PER DECL
        ...
        for st in decl.body:
            if isinstance(st, P.Decl):
                walk(st, chain + [st.name])
    for it in items:
        if isinstance(it, P.Decl):
            walk(it, [it.name])

def _node_for_chain(graph, chain):
    suffix = "#" + "/".join(chain)
    for n in graph.nodes:                       # O(N) scan, + graph.nodes is a fresh O(N) copy
        if n.id.endswith(suffix) and n.provenance is not None:
            return n
    return None
```

`walk` runs once per declaration → **O(N) calls**, each doing a full **O(N)** node
scan (worse: `Graph.nodes` returns `list(self._nodes.values())`, a fresh O(N) copy
per access). That is **O(N²)**. At N=30 000 that is ~9×10⁸ comparisons ≈ the
measured 90 s; at N=100 000 it is ~10¹⁰ ≈ the 40-minute timeout. The flat sweep
isolated it cleanly because `enrich_graph` walks *every* decl regardless of shape.

### 3.4 The other latent super-linear path (still not exercised here)

`_workflow_steps_edges` (`lower.py`) calls `_children_of(graph, wf.id)` **once per
workflow node** and separately re-scans the full edge list for `routes_to` edges,
giving **O(W·E)** for W workflows. The synthetic flat arch declares **zero**
workflows, so this path is dormant in the sweep and is **not** fixed by §6. A
workflow-heavy sweep would be needed to characterize it; flagged for follow-up.

### 3.5 Status of the review's adverse numbers

The review's "1.6s @ 1024 · 25s @ 10k" implied a slope ≈1.21 between those points —
the framing called it quadratic, but two points cannot distinguish O(n log n) +
overhead from O(n²). This sweep **supersedes** them: it confirms the *direction*
(super-linear) the review sensed, locates the *actual* cause (`enrich_graph`, which
the review did not name), and shows the fixed front-end is linear. Treat the prior
"273ms @ 100k" and "25s @ 10k" figures as retired in favor of §2.

---

## 4. Per-stage breakdown

| Stage | What it does | Measured slope (large-N) | Reading |
|-------|--------------|--------------------------|---------|
| `parse` | lex + recursive-descent parse → AST (`parser.py`) | **~1.03** (before & after) | O(n) — linear in source bytes/decls ✓ |
| `check` | resolve + 0011 type/closed-world/POLA checks (`check.py`) | **~1.03** (before & after) | O(n) on the flat arch ✓ (see note) |
| `lower` | `enrich_graph` + `_runtime_view` ×≈4 + per-fiber emit | **1.72→2.0 before**, **1.00 after** | was O(n²) (`enrich_graph`), now O(n) |

- `lower` was the steepest stage and its large-N slope was well above 1.2 → §3.3
  located the cause → §6 fixed it; the post-fix re-run confirms ≈1.0.
- **`check` note:** the flat arch declares **no capabilities**, so the POLA
  use-check's worst case (O(n²) in *capabilities per principal*, see the paper's
  Future Work) is not exercised here; on this input `check` is measured linear.
  That separate concern is out of scope for this doc.

---

## 5. Projection to 1M (from the measured post-fix slope)

```
lower_ms(1e6)  ≈  lower_ms(1e5) × (1e6 / 1e5)^slope  =  70 295 ms × 10^1.0  ≈  703 s
total_ms(1e6)  ≈  118 883 ms × 10^1.0  ≈  1 189 s  (~20 min, parse+check+lower, K=1-equivalent)
```

| Slope | 1M `lower` from measured 100k = 70.3 s | Verdict |
|-------|-----------------------------------------|---------|
| ~1.0 (measured, post-fix) | ~703 s | **Linear — the "1M projected" claim holds as a complexity statement.** Absolute time is large (pure-Python, single-process), but it scales, and a 1M-fiber declaration is far outside any realistic hand-authored topology. |
| ~2.0 (pre-fix) | ~7 000 s (~2 h) | would **not** have shipped — which is why the fix was necessary, not optional. |

The honest claim for the paper: **front-end compilation is linear in declaration
size** (all three stages slope ≈1.0 post-fix); the "1M" figure is a *projection
from the measured slope*, not a measured point.

---

## 6. Mitigation — APPLIED (the fix the before/after curve justifies)

§3.3 located the O(N²) in `enrich_graph`'s per-decl `_node_for_chain` scan. The fix
replaces the per-decl O(N) scan with **one O(N) index pass**:

```python
# lower.py — inside enrich_graph, built once before walk()
index = {}
for _n in graph.nodes:
    if _n.provenance is None:
        continue
    _h = _n.id.find("#")
    if _h != -1:
        index.setdefault(_n.id[_h:], _n)        # '#<chain>' -> first node with that suffix

def walk(decl, chain):
    node = index.get("#" + "/".join(chain))     # O(1) lookup, was O(N) scan
    ...
```

A node id is `<basename>#<chain>` with exactly one `#`, and `graph.nodes` is
insertion-ordered, so keeping the **first** node per suffix reproduces the prior
`endswith` first-match exactly. `enrich_graph` goes O(N²) → O(N); the now-unused
`_node_for_chain` is removed.

### 6.1 Acceptance (met)

- **Slope:** post-fix `lower` large-N slope **1.00** (§2.2), down from 1.72→2.0.
- **Absolute:** N=30 000 `lower` 90 s → 20.6 s (4.4×); N=100 000 DNF (>40 min) → 70 s.
- **Byte-identical output:** the lowering-fixtures golden, agentfield/OTP golden
  trees, `vakedc lower` provenance test, and the determinism baseline (100%
  convergence) all stay **byte-identical** — the fix is purely a lookup change.

### 6.2 Not done (scoped out, flagged)

- The `_children_of` edge-list re-copy/re-scan (§3.2) is a constant-factor waste,
  not on the critical path; an adjacency index in `graph.py` would still tidy it
  but the curve does not demand it.
- The O(W·E) `_workflow_steps_edges` path (§3.4) needs a workflow-heavy sweep to
  characterize and is untouched here.

---

## Appendix — artifacts & reproducibility

- **Harness:** `scripts/benchmark-scalability-sweep.py` (`--sweep` / `--emit-only`).
- **Workflow:** `.github/workflows/scalability-sweep.yml` (`workflow_dispatch`).
- **Committed curves:** `scalability-curve-before.csv` / `.json` (pre-fix),
  `scalability-curve-after.csv` / `.json` (post-fix) — GHA `ubuntu-latest`, Py 3.12.
- **Fix:** `vakedc/lower.py` `enrich_graph` (suffix index; `_node_for_chain` removed).
- **Determinism:** the generator is a pure function of N; same N ⇒ byte-identical
  source ⇒ byte-identical artifacts (0012 §2.1), so re-runs differ only in timing.
