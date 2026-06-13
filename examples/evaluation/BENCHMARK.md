# Vaked Compiler Benchmarks

This document describes the **evaluation suite** for Vaked's compiler (vakedc) performance and determinism. These benchmarks measure:

1. **Compilation performance** (parse, check, lower time)
2. **Artifact footprint** (output size)
3. **Determinism oracle** (byte-identical output verification)

## Setup

### Prerequisites

- Python 3.9+
- `vakedc` available as `python3 -m vakedc` from the repo root
- Example `.vaked` files in `vaked/examples/`

### Running Benchmarks

```bash
# From the repo root:
python3 examples/evaluation/bench.py [options]
```

**Options:**
- `--example GLOB` — match examples to benchmark (default: `*.vaked`)
- `--iterations N` — determinism oracle iterations (default: 100)
- `--verbose` — print per-iteration timing
- `--json PATH` — write JSON results to PATH

## Benchmarks

### 1. Single-Run Performance

For each `.vaked` example:

```
parse <file>   → lexing + parsing (LPG construction)
check <file>   → Goal 2 type-checking (conformance, POLA, constraints)
lower <file>   → Goal 3 lowering (parse → check → lower, full pipeline)
```

**Metrics:**
- Wall-clock time (seconds)
- Memory RSS (peak resident set size, MB)
- Artifact sizes (JSON graph, emitted files)

**Interpretation:**
- Parse time should scale linearly with file size (no semantic analysis yet)
- Check time depends on graph complexity (conformance + capability flow)
- Lower time includes check + text emission
- Regression detection: if check/lower time grows unexpectedly, schema or POLA logic may be inefficient

### 2. Determinism Oracle

For each example, compile 100 times (or configurable `--iterations`):

```python
for i in range(100):
    result = run_vakedc_lower(example)
    hash_output = sha256(result.provenance_json + result.all_artifacts)
    assert all_hashes == hashes[0], f"Iteration {i} hash mismatch"
```

**Metrics:**
- Determinism: ✅ if all hashes identical, ❌ if any diverge
- Variance: mean, stddev, min, max of per-iteration timing

**Interpretation:**
- Determinism is a **hard requirement** (0012 §1). Variance is informational (JIT warmup, GC, etc.).
- Failure = bug (non-deterministic ordering, floating-point arithmetic, time/random source)

### 3. Artifact Footprint

For each example, measure lowering output:

```
flake.nix        — Nix spine (materialization)
gen/RUNTIME.md   — runtime documentation
gen/zig/*.json   — fiber/daemon configs (JSON)
gen/catalog/*.jsonl — index projections (JSONL)
provenance.json  — artifact provenance map
```

**Metrics:**
- Total size (bytes)
- Per-artifact breakdown (table)
- Compression ratio (gzip)

**Interpretation:**
- Expected to scale ~linearly with declaration size
- Bloat may indicate inefficient emitter (e.g., redundant fields, poor projection)

## Case Studies

### Operator-Field (Small)

**File:** `vaked/examples/operator-field.vaked`  
**Size:** ~500 lines  
**Declarations:** 1 runtime (orchestrator), 2 fibers (agent, supervisor), 1 index (documentation)  
**Capabilities:** `fs.repo_rw`, `network.loopback`, `process.signal`  

**Expected timings:**
- Parse: ~5–10ms
- Check: ~2–5ms (simple graph, no deep delegation)
- Lower: ~10–15ms (emit flake, 2 fiber configs)

**Artifacts:** ~20KB total

---

### AgentField-SWE (Medium)

**File:** `vaked/examples/agentfield-swe.vaked`  
**Size:** ~1500 lines  
**Declarations:** 3 runtimes, ~8 fibers, 4 indexes, 2 streams  
**Capabilities:** complex capability graph (file I/O, network, process control)  

**Expected timings:**
- Parse: ~20–40ms
- Check: ~10–20ms (larger graph, deeper capability flow)
- Lower: ~30–50ms (emit flake, 8 fiber configs, catalog)

**Artifacts:** ~100KB total

---

### Memory/Workflow (Medium)

**File:** `vaked/examples/primitives/memory.vaked`  
**Size:** ~600 lines  
**Declarations:** 1 runtime, 3 fibers, 1 catalog (memory trace schema), 1 stream  
**Capabilities:** `memory.read`, `memory.write`, `ebpf.syscall_trace`  

**Expected timings:**
- Parse: ~10–20ms
- Check: ~5–10ms
- Lower: ~20–30ms

**Artifacts:** ~40KB total

---

## Results Interpretation

### Performance Regression Checklist

If benchmarks show unexpected slowdown:

1. **Parse time increased?** → Grammar added (`vaked/grammar/vaked-v0-plus.ebnf`), or lexer complexity grew.
2. **Check time increased?** → Type-checking rules added (0011), or new constraint/capability checks.
3. **Lower time increased?** → New emitter targets (0012 §7), or projection logic grew.
4. **Artifact size ballooned?** → Provenance entries, redundant field emission, or new schema fields.

**Mitigation:** Profile with `cProfile` and identify bottleneck. Example:

```bash
python3 -m cProfile -s cumtime -m vakedc lower vaked/examples/operator-field.vaked 2>&1 | head -30
```

### Determinism Failure Checklist

If hashes diverge:

1. **Ordering non-deterministic?** → JSON/SQLite key order depends on dict iteration (Python <3.7) or set iteration. Check `emit.py::to_canonical_json`.
2. **Timestamp/random injection?** → Verify no `time.time()`, `random.random()`, `uuid.uuid4()` in emitters.
3. **Floating-point arithmetic?** → Hashing should use exact-equality; check `inputsHash` calculation (0012 §6.2).
4. **External dependency version?** → Nix's semantic versioning or MLIR dialect changes could affect output. Unlikely, but check `flake.lock`.

**Mitigation:** Run with `--verbose` to inspect per-iteration output and identify first divergence.

---

## Specification Tests

Beyond performance, the test suite verifies **correctness**:

- **Differential oracle** (`tests/spec/test_vakedc.py`): vakedc's accept/reject verdict matches EBNF recognizer (grammar compliance).
- **Golden snapshot** (`tests/spec/golden/operator-field.graph.json`): LPG is byte-for-byte identical to hand-verified fixture.
- **Cross-artifact provenance** (`tests/spec/test_vakedc.py`): artifact spans in `provenance.json` match graph nodes.
- **Determinism** (this suite): repeated lowering → identical artifacts.

---

## Paper Use

For the research paper, report:

# Source: examples/evaluation/baseline.json (single_run; ~50ms interpreter
# startup floor is included in every number). See METHODOLOGY.md for caveats.
```
Benchmark Results (seconds, from baseline.json single_run):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example             Parse      Check      Lower
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
operator-field      0.068      0.060      0.063
agentfield-swe      0.070      0.070      0.073
memory              0.061      0.057      0.058
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Determinism: 100% (20 iterations per example, zero hash divergences among valid examples)

Artifact Sizes:
- operator-field:    22 KB (flake.nix 8KB, gen/ 14KB)
- agentfield-swe:   108 KB (flake.nix 12KB, gen/ 96KB)
- memory:            43 KB (flake.nix 9KB, gen/ 34KB)
```

**Claim:** "Vaked's compiler provides fast, deterministic checking and code generation suitable for interactive development and reproducible infrastructure deployment."
