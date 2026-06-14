# Vaked compiler scalability — analysis v0.1

> Status: **measurement slots pending a controlled run on `dev-cx53` / GHA.**
> The harness (`scripts/benchmark-scalability-sweep.py`) and the complexity
> analysis below are complete and reviewed; the numeric cells in §2/§4/§5 are
> marked **TO MEASURE** and must be filled from a build-host sweep — **not** the
> developer machine (repo rule: NEVER BUILD ON DEVELOPER MACHINE; N=100000 is a
> multi-MB source and ~100k graph nodes run K times).

This document establishes a *credibility-grade* scalability curve for the
`vakedc` front-end (`parse → check → lower`). It exists because the project's
headline claim — "100k workers verified (273ms avg, deterministic)" — and the
credibility review's adverse observations ("1.6s @ 1024", "25s @ 10k") were
**not** produced by a controlled, multi-point sweep. This analysis replaces the
single-point anecdote with a method, a harness, and a falsifiable reading of the
resulting log-log slope.

---

## 1. Methodology

### 1.1 Input — synthetic flat architecture

The sweep does **not** use the committed `vaked/examples/swe-swarm-100k-workers-scalability.vaked`.
That file is a 147-line *stub*: its header describes 100k workers, but the body
declares only a handful of representative `node`s with `# ... omitted ...`
comments. It cannot measure scaling — there is nothing at scale in it.

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
  fibers + 1 stream. No `mesh`, no `workflow`, no deep nesting. This deliberately
  isolates the **runtime-decomposition** cost (`_runtime_view` → `_children_of`)
  — the exact code the credibility review's numbers would have stressed — from
  the *other* potentially-quadratic path (the per-workflow scan; see §3.4).
- **Deterministic & hermetic:** `generate_synthetic_vaked(n)` is a pure function
  of `n` — byte-identical output for a given N, no clock, no RNG, no network, no
  dependency on the repo's `examples/` tree (the engine is a sidecar the harness
  writes next to the source). This is why the curve is reproducible.

The generated source **parses, checks, and lowers with zero diagnostics**
(verified at small N on the dev machine — a trivial correctness check, not a
scaling run). Lowering it produces `flake.nix`, `gen/RUNTIME.md`, and one
`gen/zig/<fiber>.json` per fiber.

### 1.2 N range and iterations

| Parameter | Value |
|-----------|-------|
| N (worker fibers) | {100, 1000, 10000, 100000} |
| Iterations K per N | 10 (default; `--iters`) |
| Stages timed | `parse`, `check`, `lower` (each a separate `python3 -m vakedc <stage>` subprocess) |
| Aggregation | per-stage **median** across the K clean iterations (robust to scheduler jitter on a shared build host); `min` also recorded |

Four N spanning three decades give a log-log line with enough points to read a
slope (§3). 10 iterations let the median shrug off one-off GC pauses / page
faults on a shared host.

### 1.3 How to run it (build host only)

On **`dev-cx53`** (the preferred build target — Linux, 30GB RAM, Tailscale):

```bash
ssh dev-cx53 'cd <repo> && git fetch origin && git checkout docs/scalability-curve && \
  PYTHONPATH=. python3 scripts/benchmark-scalability-sweep.py \
    --sweep --iters 10 --out artifacts/scalability-curve.csv'
```

Equivalently from inside the repo on the build host:

```bash
PYTHONPATH=. python3 scripts/benchmark-scalability-sweep.py \
    --sweep --iters 10 --out artifacts/scalability-curve.csv
```

This writes `artifacts/scalability-curve.csv` (one row per N, per-stage medians)
and a sibling `artifacts/scalability-curve.json` (full per-iteration rows + host
+ timestamp). Fallback target: GitHub Actions (a workflow invoking the same
command). The generator alone is dev-safe for inspection:
`python3 scripts/benchmark-scalability-sweep.py --emit-only --n 1000 --out /tmp/x.vaked`.

> **Why not the dev machine?** N=100000 emits a ~3–4 MB source file, builds a
> ~100k-node graph, and runs the whole pipeline 10×. That is squarely a "build"
> under the project rule. Run it on `dev-cx53` / GHA and paste the CSV medians
> into §2.

---

## 2. Results

**Per-stage wall-clock, median of K=10 iterations. TO MEASURE — run on `dev-cx53`/GHA per §1.3.**

| N (workers) | fibers | parse (ms) | check (ms) | lower (ms) | total (ms) |
|-------------|--------|-----------|-----------|-----------|-----------|
| 100 | 102 | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ |
| 1 000 | 1 002 | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ |
| 10 000 | 10 002 | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ |
| 100 000 | 100 002 | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ | _TO MEASURE_ |

> The CSV columns map 1:1 to this table: `parse_ms_median`, `check_ms_median`,
> `lower_ms_median`, `total_ms_median`. Copy the four data rows in verbatim.

**Constant-offset caveat (read before interpreting small-N rows):** each stage
is a separate Python process, so every cell carries a fixed
interpreter-startup + import cost (~50–65 ms observed at tiny N on the dev
machine). That offset *dominates* the N=100 row and partly the N=1000 row, and
will flatten the apparent slope at the low end. The slope must therefore be read
from the **large-N** end (N=10000 → 100000), where the algorithmic term has
overtaken the constant. (A future revision can add an in-process mode that
calls `parse_source`/`check_source`/`lower` directly to strip the offset; v0.1
keeps the subprocess model for parity with `benchmark-100k-scalability.py`.)

---

## 3. Complexity analysis

### 3.1 Reading the log-log slope

Plot `log(total_ms_minus_offset)` against `log(N)`. Fit a line; its **slope is
the empirical complexity exponent**:

| Slope (large-N end) | Reading |
|---------------------|---------|
| ≈ **1.0** | **O(n)** — linear. Doubling N doubles the time. Expected for a flat arch given the analysis below. |
| ≈ **1.0–1.2** | O(n log n) — the repeated sort term (§3.3) showing through. Still healthy. |
| ≈ **2.0** | **O(n²)** — quadratic. Doubling N quadruples the time. A red flag; would corroborate the review's "25s @ 10k". |
| > 2 | super-quadratic — would indicate a nested scan we have not accounted for. |

Concretely: between N=10000 and N=100000 (a 10× step), a linear stage's median
should rise ~10×; a quadratic stage ~100×. That ratio is the single most
important number this sweep produces.

### 3.2 The `_children_of` scan — the thing under suspicion

`vakedc/lower.py:206-215`:

```python
def _children_of(graph, parent_id):
    out = []
    for e in graph.edges:                      # O(E) — full edge-list scan
        if e.label == "contains" and e.source == parent_id:
            child = graph.get_node(e.target)   # O(1) — dict .get (graph.py:103)
            if child is not None:
                out.append(child)
    return out
```

Each call is **O(E)**: it walks the entire edge list to find the `contains`
children of one parent. There is **no adjacency index** in `graph.py` — edges are
a flat `list` (`graph.py:93`), and `Graph.edges` (`graph.py:137-139`) returns a
**fresh `list(self._edges)` copy on every access**, so each call also pays an
O(E) copy on top of the O(E) scan.

### 3.3 Is it called once (flat → O(n)) or recursively (hierarchical → O(n²))?

**Honest verdict: for this flat architecture it is called a *small constant*
number of times per `lower`, so `lower` is O(n log n) — NOT quadratic. But the
constant is not 1, and a hierarchical input would change the story.**

The chain:

- `_runtime_view(graph)` (`lower.py:300-322`) calls `_children_of` **exactly
  once** (`lower.py:305`), for the single `runtime` node. It is **not** recursive
  — it does one scan, then partitions the result by kind (`_by_kind`, in-memory).
  So **one** `_runtime_view` call costs `nodes_sorted()` (O(n log n),
  `lower.py:301` → `graph.py:141`) + one `_children_of` (O(E)).
- **But `_runtime_view` is called ~13 times per full `lower`**: once in
  `lower()` itself (`lower.py:2261`) and once inside *each* emitter that fires
  (`emit_nix_spine` `lower.py:367`, `emit_docs_runtime` `lower.py:636`,
  `emit_zig_daemoncfg` `lower.py:900`, and the cohort/plane emitters at
  `lower.py:1336, 1471, 1621, 1647, 1770, 1915, 2012, 2147, 2261`). For the
  **flat fiber arch** only three of those actually run (`nix.spine`,
  `docs.runtime`, `zig.daemoncfg` — the rest gate on absent cohorts), so
  `_runtime_view` fires ~4× and `_children_of` ~4×.
- Therefore per `lower`: `≈4 × O(n log n + E)`. With a flat arch the resolver
  emits one `contains` edge per child, so **E = O(n)**, giving **O(n log n)**
  overall — dominated by the repeated `nodes_sorted()`, with the edge scans a
  lower-order O(n) term. **This predicts a log-log slope of ≈1.0–1.1, not 2.0.**

So the design is **flat → roughly linear** *for this input shape*. The
`_children_of` scan is wasteful (it is O(E) where an indexed lookup would be
O(children), and it is repeated ~4× over the same parent), but the waste is a
**constant factor**, not a complexity-class regression — *as long as the input
is flat and `_children_of` is never called inside a per-node loop.*

### 3.4 The genuine super-linear risk (not exercised here)

There **is** a code path where `_children_of` runs inside a per-node loop:
`_workflow_steps_edges` (`lower.py:1882-1890`) calls `_children_of(graph, wf.id)`
**once per workflow node**, and then *separately* scans the full edge list again
for `routes_to` edges:

```python
steps = [n for n in _children_of(graph, wf.id) if n.kind == "node"]   # O(E) per workflow
ids = {n.id: n.name for n in steps}
edges = [(ids[e.source], ids[e.target])
         for e in graph.edges                                          # O(E) per workflow
         if e.label == "routes_to" and e.source in ids and e.target in ids]
```

For a runtime with **W workflows**, `emit_workflow_spec` (`lower.py:1909`) runs
this for each, giving **O(W·E)** — quadratic in the workflow/edge count. The
synthetic flat arch declares **zero workflows**, so this path is dormant in the
sweep. A *workflow-heavy* sweep would be needed to characterize it, and it is the
most plausible origin of the review's "25s @ 10k" if those numbers came from a
mesh-/workflow-heavy input rather than a flat one.

### 3.5 Status of the review's adverse numbers

The credibility review's "**1.6s @ 1024 · 25s @ 10k**" observations imply a slope
of `log(25/1.6) / log(10000/1024) ≈ log(15.6)/log(9.77) ≈ 1.21` between those two
points — *sub-quadratic*, consistent with O(n log n) plus overhead, **not** the
O(n²) the framing suggests. However, those two points are **unconfirmed by a
controlled sweep**: we do not know the input shape (flat vs mesh vs workflow), the
machine, the iteration count, or whether interpreter startup was included. **This
sweep supersedes them.** Until §2 is filled, treat both the "273ms @ 100k" claim
and the "25s @ 10k" counter-claim as *unverified*.

---

## 4. Per-stage breakdown

Fill from the same run as §2. The point is to attribute the curve to a stage, so
mitigation (if any) targets the right code.

| Stage | What it does | Expected dominant term | Slope at large N (**TO MEASURE**) |
|-------|--------------|------------------------|-----------------------------------|
| `parse` | lex + recursive-descent parse → AST items (`parser.py`) | O(n) in source bytes / decls | _TO MEASURE_ |
| `check` | resolve + 0011 type/closed-world checks (`check.py`); `_check_ref_resolution` does per-runtime ref walks | O(n) to O(n log n) | _TO MEASURE_ |
| `lower` | `_runtime_view` ×≈4 (each O(n log n)) + per-fiber emit (`zig.daemoncfg`, O(n)) | O(n log n) (repeated sort) | _TO MEASURE_ |

Reading guide once filled:
- If **`lower`** is the steepest stage and its slope > 1.2, the repeated
  `_runtime_view`/`_children_of` work is the culprit → apply §6.
- If **`check`** dominates, the mitigation is elsewhere (out of scope for this
  doc — open a separate item against `check.py`).
- If all three track ≈1.0, the front-end is linear and no change is warranted;
  record that as the verified result and close the risk.

---

## 5. Projection to 1M

The repo claims "1M projected". Project it **honestly** from the measured slope,
not from the single 100k anecdote:

```
total_ms(1e6)  ≈  total_ms(1e5) × (1e6 / 1e5)^slope
              =  total_ms(1e5) × 10^slope
```

| Assumed slope | 1M total from a measured 100k of T | Verdict |
|---------------|------------------------------------|---------|
| 1.0 (linear) | 10·T | ships if T(100k) ≲ a few s |
| 1.2 (n log n) | ~15.8·T | likely still fine |
| 2.0 (quadratic) | 100·T | **does not ship** without §6 |

**TO MEASURE:** once §2 has `total_ms_median` at N=100000 and the fitted slope,
compute the 1M projection here and state whether the "1M projected" claim holds.
Do **not** assert 1M until the slope is measured — a quadratic slope makes 1M
~100× the 100k time, which would break the claim.

---

## 6. Mitigation — conditional on a measured super-linear slope

**Do not implement this yet.** Apply it only if §4 shows `lower`'s large-N slope
is meaningfully > 1 (target the n-log-n sort + the O(E) scans), or if a
follow-up workflow-heavy sweep confirms the §3.4 O(W·E) path bites.

### 6.1 Precompute a `children_by_parent` adjacency map once

Build the adjacency index **once** per graph in O(E) and replace every
`_children_of` full-scan with an O(children) dict lookup.

**In `vakedc/graph.py`** — add a memoized adjacency index to `Graph`. The edge
list is append-only after build, so a lazily-built, cached map is safe:

```python
# graph.py — inside class Graph
def children_by_parent(self, label="contains"):
    """{parent_id: [child GraphNode, ...]} for edges of `label`, source order.
    Built once (O(E)) and cached; callers get O(children) lookups."""
    cache = getattr(self, "_children_cache", None)
    if cache is None:
        cache = {}
        self._children_cache = cache
    if label not in cache:
        idx = {}
        for e in self._edges:                       # the ONLY O(E) pass
            if e.label == label:
                child = self._nodes.get(e.target)
                if child is not None:
                    idx.setdefault(e.source, []).append(child)
        cache[label] = idx
    return cache[label]
```

(If any future code mutates edges after first lookup, invalidate by clearing
`self._children_cache` in `add_edge`.)

**In `vakedc/lower.py:206-215`** — replace the scan body of `_children_of`:

```python
def _children_of(graph, parent_id):
    """Direct `contains` children of a node, in source order. O(children) via
    the graph's adjacency index (built once, O(E)); was an O(E) full-edge scan."""
    return graph.children_by_parent("contains").get(parent_id, [])
```

This single change makes:
- `_runtime_view` (`lower.py:305`) O(children-of-runtime) per call instead of
  O(E) — even called ~4× it is now ~4× O(n) lookups + the shared one-time O(E)
  build;
- `_workflow_steps_edges` (`lower.py:1885`) O(children-of-workflow) per workflow
  for the `_children_of` half. (Its *second* scan — the `routes_to` filter at
  `lower.py:1888` — is a separate O(E) per workflow; if §3.4 proves the bottleneck,
  also add a `children_by_parent("routes_to")`-style index or precompute the
  `routes_to` adjacency once and reuse it across workflows.)

### 6.2 (Optional, same PR) memoize `_runtime_view`

Even with O(1) child lookup, `_runtime_view` still calls `nodes_sorted()`
(O(n log n)) on every one of its ~4 invocations. Computing it **once** in
`lower()` and threading the `_RuntimeView` to the emitters (instead of each
emitter re-deriving it) removes the repeated sort — turning ~4 sorts into 1.
This is a larger refactor (every emitter signature gains the view); gate it on
whether the sort term actually shows in §4.

### 6.3 Acceptance for the mitigation

After applying §6.1 (± §6.2), **re-run the same sweep** and confirm the large-N
`lower` slope drops to ≈1.0 (or the absolute 100k/1M times land under target).
The mitigation is justified only if the before/after sweep shows it.

---

## Appendix — artifacts & reproducibility

- **Harness:** `scripts/benchmark-scalability-sweep.py` (`--sweep` / `--emit-only`).
- **Outputs:** `artifacts/scalability-curve.csv` (per-N medians) +
  `artifacts/scalability-curve.json` (per-iteration rows, host, timestamp).
- **Sibling single-point script:** `scripts/benchmark-100k-scalability.py`
  (determinism + the 100k stub; not a curve).
- **Code under analysis:** `vakedc/lower.py:206` (`_children_of`),
  `vakedc/lower.py:300` (`_runtime_view`), `vakedc/lower.py:1882`
  (`_workflow_steps_edges`), `vakedc/graph.py:87` (`Graph`; no adjacency index).
- **Determinism:** the generator is a pure function of N; same N ⇒ byte-identical
  source ⇒ byte-identical artifacts (0012 §2.1), so re-runs differ only in timing.
