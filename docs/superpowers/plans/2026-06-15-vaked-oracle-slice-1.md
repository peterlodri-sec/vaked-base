# vaked-oracle Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/oracle/` — a standalone LLM-assisted reverse-engineering subsystem that, driven by a ralph decision loop, reverse-engineers the `llama-cli` runtime (Ghidra pseudo-C → llm4decompile-6.7B) with Frida + eBPF dynamic evidence, scores decompilation fidelity against ground-truth source, and emits a finding record that bridges to the aegis kernel's evidence seam.

**Architecture:** Standalone subsystem mirroring `tools/dogfood/`. Each external tool is split into a **pure parser** (unit-tested with captured fixtures) and a **thin impure runner** (integration-verified on dev-cx53). The loop reuses `tools/ralph/ralphcore.py` (chain ledger, budget, control) read-only. eBPF runs in a **root watcher service**; the unprivileged `revdev` client reaches it over a unix socket.

**Tech Stack:** Python 3 stdlib (no pytest — tests run via `python3 tools/oracle/test_oracle.py`), `ralphcore` (hash chain/budget/control), Ghidra `analyzeHeadless`, llama.cpp `llama-server` (llm4decompile-6.7B GGUF), `frida`, `bpftrace`/eBPF, NixOS module for the watcher, Vaked (`vakedc check`).

**Spec:** `docs/superpowers/specs/2026-06-15-vaked-oracle-design.md`

---

## File Structure

```
tools/oracle/
  __init__.py          empty package marker
  schema.py            finding record build/validate; function-entry builder
  ledger.py            append-only decision ledger over ralphcore chain (.oracle/events.jsonl)
  fidelity.py          normalized-token similarity scorer (refined-C vs ground truth)
  ghidra_frontend.py   parse_decomp() [pure] + run_ghidra() [impure] + DecompileExport.py (Ghidra script)
  llm_refine.py        build_prompt()/parse_completion() [pure] + refine() [impure HTTP]
  dynamic_frida.py     parse_frida_trace() [pure] + run_frida() [impure] + hook.js
  watcher_client.py    encode_request()/decode_response() [pure] + query_watcher() [impure socket]
  watcher_daemon.py     root daemon: unix socket → PID-scoped bpftrace → JSON  (runs as root on dev-cx53)
  bridge.py            finding → observed_effects {writes,deletes} + transition_xref
  policy.py            pure decision policy: (loop state) → next action
  loop.py              tick loop: control/budget gate → policy → run producers → append ledger
  oracle.py            CLI: `oracle run --target … --funcs …`
  test_oracle.py       all stdlib unit tests
  Taskfile.yml         dev-cx53 ops (model fetch, ghidra, run, watcher, deploy)
  DecompileExport.py   Ghidra post-script (lives here, copied to scriptPath at run)
  hook.js              Frida instrumentation script
hosts/dev-cx53/oracle-ebpf-watcher.nix   NixOS root systemd service + socket
vaked/examples/oracle-re-loop.vaked       RE loop as a checked Vaked capability graph
docs/oracle/{README.md, v0.md, integration.md}
.gitignore                                add `.oracle/`
```

Runtime state lives in `.oracle/` (gitignored): `events.jsonl` (ledger), `findings/<hash>.json`, `cache/`.

---

## Task 1: Package scaffold + gitignore

**Files:**
- Create: `tools/oracle/__init__.py`
- Create: `tools/oracle/test_oracle.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create the empty package marker**

```bash
mkdir -p tools/oracle
: > tools/oracle/__init__.py
```

- [ ] **Step 2: Create the test runner skeleton**

Create `tools/oracle/test_oracle.py`:

```python
#!/usr/bin/env python3
"""vaked-oracle unit tests (stdlib only; run: python3 tools/oracle/test_oracle.py)."""
import os
import sys

# allow `import schema` etc. when run from repo root or tools/oracle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --- tests are added below by later tasks ---


if __name__ == "__main__":
    def _run():
        tests = sorted((n, f) for n, f in dict(globals()).items()
                       if n.startswith("test_") and callable(f))
        passed = failed = 0
        for name, fn in tests:
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except Exception as e:
                print(f"FAIL  {name}: {type(e).__name__}: {e}")
                failed += 1
        print(f"\n{passed} passed, {failed} failed")
        return 1 if failed else 0
    raise SystemExit(_run())
```

- [ ] **Step 3: Run the empty suite (proves the runner works)**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `0 passed, 0 failed`, exit 0.

- [ ] **Step 4: Add `.oracle/` to gitignore**

Append to `.gitignore` (after the existing `.dogfood/` line):

```
.oracle/                # vaked-oracle runtime state (ledger, findings, cache)
```

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/__init__.py tools/oracle/test_oracle.py .gitignore
git commit -m "feat(oracle): scaffold tools/oracle package + test runner"
```

---

## Task 2: Finding record schema (`schema.py`)

**Files:**
- Create: `tools/oracle/schema.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `tools/oracle/test_oracle.py` (above the `__main__` block):

```python
import schema  # noqa: E402


def test_function_entry_defaults_nullable_dynamic():
    e = schema.function_entry(name="sample_fn", addr="0x1000",
                              pseudo_c_sha="ab" * 32, refined_c="int f(){}")
    assert e["name"] == "sample_fn"
    assert e["fidelity"] == {"score": None, "method": schema.FIDELITY_METHOD}
    assert e["dynamic"] == {"frida": None, "ebpf": None}


def test_build_finding_shape_and_kind():
    fn = schema.function_entry(name="f", addr="0x1", pseudo_c_sha="0" * 64, refined_c="x")
    fdg = schema.build_finding(
        target={"path": "/p", "sha256": "0" * 64, "source_ref": "v1"},
        decompiler={"model": "llm4decompile-6.7b-v2", "model_sha256": "0" * 64, "temperature": 0},
        functions=[fn], confidence=0.5)
    assert fdg["kind"] == "oracle_finding" and fdg["v"] == 1
    assert fdg["observed_effects"] == {"writes": [], "deletes": []}
    assert fdg["transition_xref"] is None
    assert fdg["functions"][0]["name"] == "f"


def test_validate_rejects_bad_kind():
    bad = {"kind": "nope", "v": 1}
    try:
        schema.validate_finding(bad)
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'schema'`.

- [ ] **Step 3: Implement `schema.py`**

Create `tools/oracle/schema.py`:

```python
"""vaked-oracle finding record schema (see docs/oracle/v0.md)."""
from __future__ import annotations

FINDING_KIND = "oracle_finding"
FINDING_V = 1
FIDELITY_METHOD = "normalized-token-similarity"


def function_entry(*, name: str, addr: str, pseudo_c_sha: str, refined_c: str | None,
                   fidelity_score: float | None = None,
                   frida: dict | None = None, ebpf: dict | None = None) -> dict:
    """One analyzed function. Dynamic evidence is independently nullable."""
    return {
        "name": name,
        "addr": addr,
        "pseudo_c_sha": pseudo_c_sha,
        "refined_c": refined_c,
        "fidelity": {"score": fidelity_score, "method": FIDELITY_METHOD},
        "dynamic": {"frida": frida, "ebpf": ebpf},
    }


def build_finding(*, target: dict, decompiler: dict, functions: list[dict],
                  confidence: float, observed_effects: dict | None = None,
                  transition_xref: str | None = None) -> dict:
    """Assemble the finding payload (the ledger entry will add the chain fields)."""
    return {
        "kind": FINDING_KIND,
        "v": FINDING_V,
        "target": target,
        "decompiler": decompiler,
        "functions": functions,
        "observed_effects": observed_effects or {"writes": [], "deletes": []},
        "transition_xref": transition_xref,
        "confidence": confidence,
    }


def validate_finding(f: dict) -> None:
    """Raise ValueError if the finding is structurally invalid."""
    if f.get("kind") != FINDING_KIND:
        raise ValueError(f"bad kind: {f.get('kind')!r}")
    if f.get("v") != FINDING_V:
        raise ValueError(f"bad version: {f.get('v')!r}")
    for key in ("target", "decompiler", "functions", "observed_effects", "confidence"):
        if key not in f:
            raise ValueError(f"missing key: {key}")
    oe = f["observed_effects"]
    if set(oe) != {"writes", "deletes"}:
        raise ValueError("observed_effects must have exactly writes+deletes")
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `3 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/schema.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): finding record schema + validation"
```

---

## Task 3: Decision ledger (`ledger.py`)

Reuses `ralphcore` chain primitives. The finding is persisted as a ledger entry payload; its chain fields come from the entry.

**Files:**
- Create: `tools/oracle/ledger.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import ledger  # noqa: E402
import tempfile  # noqa: E402


def test_ledger_append_and_verify():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        e0 = lg.append({"kind": "decision", "action": "decompile", "fn": "f"})
        e1 = lg.append({"kind": "finding", "confidence": 0.9})
        assert e0["seq"] == 0 and e0["prev"] == ledger.GENESIS_HASH
        assert e1["seq"] == 1 and e1["prev"] == e0["hash"]
        assert lg.verify() is True


def test_ledger_detects_tamper():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "events.jsonl")
        lg = ledger.Ledger(path)
        lg.append({"kind": "decision", "n": 1})
        lg.append({"kind": "decision", "n": 2})
        # corrupt the first entry's payload on disk
        lines = open(path).read().splitlines()
        lines[0] = lines[0].replace('"n": 1', '"n": 999')
        open(path, "w").write("\n".join(lines) + "\n")
        lg2 = ledger.Ledger(path)
        assert lg2.verify() is False
        assert len(lg2.valid_prefix()) == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ledger'`.

- [ ] **Step 3: Implement `ledger.py`**

Create `tools/oracle/ledger.py`:

```python
"""Append-only, hash-chained decision ledger for an oracle RE session.

Reuses tools/ralph/ralphcore.py chain primitives (do NOT reimplement the chain).
"""
from __future__ import annotations

import json
import os
import sys

# import ralphcore from the sibling tools/ralph
_RALPH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ralph")
sys.path.insert(0, _RALPH)
import ralphcore  # noqa: E402

GENESIS_HASH = ralphcore.GENESIS_HASH


class Ledger:
    """JSONL of ralphcore chain entries. One entry per decision / finding."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._entries = self._load()

    def _load(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        for line in open(self.path):
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def append(self, payload: dict) -> dict:
        prev = self._entries[-1]["hash"] if self._entries else GENESIS_HASH
        seq = len(self._entries)
        entry = ralphcore.make_entry(prev, seq, payload)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._entries.append(entry)
        return entry

    def entries(self) -> list[dict]:
        return list(self._entries)

    def verify(self) -> bool:
        return ralphcore.verify_chain(self._entries)

    def valid_prefix(self) -> list[dict]:
        return ralphcore.longest_valid_prefix(self._entries)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `5 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/ledger.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): hash-chained decision ledger over ralphcore"
```

---

## Task 4: Fidelity scorer (`fidelity.py`)

**Files:**
- Create: `tools/oracle/fidelity.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import fidelity  # noqa: E402


def test_fidelity_identical_is_one():
    src = "int add(int a, int b) { return a + b; }"
    assert fidelity.score(src, src) == 1.0


def test_fidelity_unrelated_is_low():
    a = "int add(int a, int b) { return a + b; }"
    b = "while (true) { printf(\"zzz\"); }"
    assert fidelity.score(a, b) < 0.4


def test_fidelity_handles_empty():
    assert fidelity.score("", "") == 0.0
    assert fidelity.score("int x;", "") == 0.0
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'fidelity'`.

- [ ] **Step 3: Implement `fidelity.py`**

Create `tools/oracle/fidelity.py`:

```python
"""Decompilation fidelity: normalized-token similarity vs ground-truth source.

Slice 1 method only. Token set = C identifiers/keywords/operators after stripping
comments and collapsing whitespace. Score = Jaccard over token multisets (Dice).
A later cycle replaces this with a tree-sitter AST diff.
"""
from __future__ import annotations

import re
from collections import Counter

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_TOKEN = re.compile(r"[A-Za-z_]\w*|[^\sA-Za-z_]")


def _tokens(code: str) -> Counter:
    code = _COMMENT.sub(" ", code)
    return Counter(_TOKEN.findall(code))


def score(a: str, b: str) -> float:
    """Dice coefficient over token multisets; 0.0 if either side is empty."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = sum((ta & tb).values())
    return round(2 * inter / (sum(ta.values()) + sum(tb.values())), 4)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `8 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/fidelity.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): normalized-token fidelity scorer"
```

---

## Task 5: LLM refine — prompt build + completion parse (`llm_refine.py`)

The pure parts (prompt assembly, response parsing) are unit-tested. The HTTP call is a thin runner verified on dev-cx53.

**Files:**
- Create: `tools/oracle/llm_refine.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import llm_refine  # noqa: E402


def test_build_prompt_inserts_pseudo_c():
    p = llm_refine.build_prompt("int f(){return 1;}")
    assert "int f(){return 1;}" in p
    assert p.endswith(llm_refine.PROMPT_SUFFIX)


def test_parse_completion_extracts_content():
    # llama.cpp native /completion returns {"content": "..."}
    assert llm_refine.parse_completion({"content": "int f(){...}"}) == "int f(){...}"


def test_parse_completion_missing_content_raises():
    try:
        llm_refine.parse_completion({"oops": 1})
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm_refine'`.

- [ ] **Step 3: Implement `llm_refine.py`**

Create `tools/oracle/llm_refine.py`:

```python
"""Refine Ghidra pseudo-C into source-like C via llm4decompile-6.7B on llama-server.

The prompt template follows the llm4decompile decompile-refine convention; confirm
the exact wording against the chosen GGUF's model card at implementation time
(open item in the spec). build_prompt/parse_completion are pure and tested; refine()
is the thin HTTP runner (integration-verified on dev-cx53 with llama-server up).
"""
from __future__ import annotations

import json
import urllib.request

# llm4decompile refine template: pseudo-C in, source C out.
PROMPT_PREFIX = "# This is the decompiled pseudo-code:\n"
PROMPT_SUFFIX = "\n# What is the original source code?\n"

DEFAULT_SERVER = "http://127.0.0.1:8080/completion"  # llama-server native endpoint


def build_prompt(pseudo_c: str) -> str:
    return f"{PROMPT_PREFIX}{pseudo_c}{PROMPT_SUFFIX}"


def parse_completion(resp: dict) -> str:
    """Extract generated text from a llama.cpp /completion response."""
    return resp["content"]


def refine(pseudo_c: str, *, server: str = DEFAULT_SERVER, n_predict: int = 1024,
           timeout: float = 600.0) -> str:
    """POST to llama-server, temperature=0 for determinism. Impure."""
    body = json.dumps({
        "prompt": build_prompt(pseudo_c),
        "temperature": 0,
        "n_predict": n_predict,
        "stop": ["# This is", "# What is"],
    }).encode()
    req = urllib.request.Request(server, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_completion(json.loads(r.read().decode())).strip()
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `11 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/llm_refine.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): llm4decompile refine (prompt+parse pure, HTTP runner)"
```

---

## Task 6: Ghidra frontend — decomp parse + headless runner (`ghidra_frontend.py`, `DecompileExport.py`)

**Files:**
- Create: `tools/oracle/ghidra_frontend.py`
- Create: `tools/oracle/DecompileExport.py` (Ghidra post-script)
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import ghidra_frontend as gf  # noqa: E402


def test_parse_decomp_reads_json_map():
    blob = '{"sample_fn": "int sample_fn(void){return 0;}", "g": "void g(){}"}'
    got = gf.parse_decomp(blob)
    assert got["sample_fn"].startswith("int sample_fn")
    assert set(got) == {"sample_fn", "g"}


def test_parse_decomp_bad_json_raises():
    try:
        gf.parse_decomp("not json")
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghidra_frontend'`.

- [ ] **Step 3: Implement `ghidra_frontend.py`**

Create `tools/oracle/ghidra_frontend.py`:

```python
"""Static frontend: Ghidra analyzeHeadless → decompiler pseudo-C per function.

parse_decomp() is pure (tested). run_ghidra() is the impure runner; it invokes
analyzeHeadless with DecompileExport.py as a postScript, which writes a JSON map
{func_name: pseudo_c} to the output path. analyzeHeadless lives under the nix
ghidra package's support/ dir; pass its path explicitly (open item / Taskfile var).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile


def parse_decomp(blob: str) -> dict[str, str]:
    """Parse the {func: pseudo_c} JSON emitted by DecompileExport.py."""
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ValueError(f"bad decomp json: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("decomp json must be an object")
    return {str(k): str(v) for k, v in data.items()}


def run_ghidra(*, analyze_headless: str, binary: str, functions: list[str],
               project_dir: str | None = None, timeout: float = 1800.0) -> dict[str, str]:
    """Impure. Returns {func: pseudo_c}. Raises CalledProcessError on ghidra failure."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tmp = project_dir or tempfile.mkdtemp(prefix="oracle-ghidra-")
    out_json = os.path.join(tmp, "decomp.json")
    cmd = [
        analyze_headless, tmp, "oracleProj",
        "-import", binary, "-overwrite",
        "-scriptPath", script_dir,
        "-postScript", "DecompileExport.py", out_json, ",".join(functions),
    ]
    subprocess.run(cmd, check=True, timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return parse_decomp(open(out_json).read())
```

- [ ] **Step 4: Create the Ghidra post-script**

Create `tools/oracle/DecompileExport.py`:

```python
# Ghidra post-script (Jython). Run by analyzeHeadless:
#   -postScript DecompileExport.py <out_json> <comma,separated,func,names>
# Writes {func_name: pseudo_c} JSON for the requested functions.
import json
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

args = getScriptArgs()            # noqa: F821 (Ghidra-injected)
out_path = args[0]
wanted = set(a for a in args[1].split(",") if a)

ifc = DecompInterface()
ifc.openProgram(currentProgram)   # noqa: F821
monitor = ConsoleTaskMonitor()

result = {}
fm = currentProgram.getFunctionManager()   # noqa: F821
for fn in fm.getFunctions(True):
    name = fn.getName()
    if wanted and name not in wanted:
        continue
    res = ifc.decompileFunction(fn, 60, monitor)
    if res and res.decompileCompleted():
        result[name] = res.getDecompiledFunction().getC()

with open(out_path, "w") as fh:
    json.dump(result, fh)
```

- [ ] **Step 5: Run to verify pass (pure parser tests)**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `13 passed, 0 failed`.

- [ ] **Step 6: Commit**

```bash
git add tools/oracle/ghidra_frontend.py tools/oracle/DecompileExport.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): ghidra headless frontend + decomp export script"
```

---

## Task 7: Frida dynamic evidence — trace parse + runner (`dynamic_frida.py`, `hook.js`)

**Files:**
- Create: `tools/oracle/dynamic_frida.py`
- Create: `tools/oracle/hook.js`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import dynamic_frida as dfr  # noqa: E402


def test_parse_frida_aggregates_calls():
    # hook.js emits one JSON line per call event
    lines = [
        '{"fn": "ggml_compute", "dur_ns": 1000}',
        '{"fn": "ggml_compute", "dur_ns": 3000}',
        '{"fn": "llama_decode", "dur_ns": 500}',
    ]
    got = dfr.parse_frida_trace("\n".join(lines))
    assert got["ggml_compute"]["calls"] == 2
    assert got["ggml_compute"]["timing_ms"] == 0.004  # (1000+3000)ns -> ms, rounded
    assert got["llama_decode"]["calls"] == 1


def test_parse_frida_ignores_noise_lines():
    got = dfr.parse_frida_trace('garbage\n{"fn":"f","dur_ns":1000}\n[frida] log')
    assert got["f"]["calls"] == 1
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'dynamic_frida'`.

- [ ] **Step 3: Implement `dynamic_frida.py`**

Create `tools/oracle/dynamic_frida.py`:

```python
"""Userspace dynamic evidence via Frida (no root; ptrace on revdev's own process).

parse_frida_trace() is pure (tested). run_frida() is the impure runner: it launches
the target via sample-run (bubblewrap, no-net) under frida with hook.js, which emits
one JSON line per hooked-function call. Aggregates to {fn: {calls, timing_ms}}.
"""
from __future__ import annotations

import json
import os
import subprocess


def parse_frida_trace(text: str) -> dict[str, dict]:
    """Aggregate per-function call events. Non-JSON / non-event lines are ignored."""
    agg: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        fn = ev.get("fn")
        if fn is None:
            continue
        slot = agg.setdefault(fn, {"calls": 0, "_ns": 0})
        slot["calls"] += 1
        slot["_ns"] += int(ev.get("dur_ns", 0))
    for fn, slot in agg.items():
        slot["timing_ms"] = round(slot.pop("_ns") / 1e6, 6)
    return agg


def run_frida(*, target_cmd: list[str], functions: list[str],
              sample_run: str = "sample-run", timeout: float = 300.0) -> dict[str, dict]:
    """Impure. Run target under frida+hook.js inside sample-run; return aggregated trace."""
    hook = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook.js")
    env = dict(os.environ, ORACLE_HOOK_FUNCS=",".join(functions))
    cmd = [sample_run, "frida", "-q", "-l", hook, "-f", *target_cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return parse_frida_trace(proc.stdout)
```

- [ ] **Step 4: Create the Frida hook script**

Create `tools/oracle/hook.js`:

```javascript
// Frida hook: attach to the functions named in ORACLE_HOOK_FUNCS (comma list),
// emit one JSON line per call with wall-clock duration. Resolve by export symbol;
// functions not exported are skipped (slice 1 hooks exported symbols only).
const names = (Recv ? "" : "");  // placeholder no-op to keep linters quiet
const wanted = (Process.env && Process.env.ORACLE_HOOK_FUNCS
                ? Process.env.ORACLE_HOOK_FUNCS : "").split(",").filter(Boolean);

wanted.forEach(function (fn) {
  const addr = Module.findExportByName(null, fn);
  if (!addr) { return; }
  Interceptor.attach(addr, {
    onEnter() { this._t0 = Process.getCurrentThreadId(); this._start = Date.now(); },
    onLeave() {
      const durNs = (Date.now() - this._start) * 1e6;
      send(JSON.stringify({ fn: fn, dur_ns: durNs }));
    },
  });
});
```

> Note: `send()` output is captured on stdout by `frida -q`. If the chosen frida
> version routes `send()` to a message channel instead of stdout, switch the
> emit to `console.log(...)` — `parse_frida_trace` reads stdout either way.

- [ ] **Step 5: Run to verify pass (pure parser tests)**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `15 passed, 0 failed`.

- [ ] **Step 6: Commit**

```bash
git add tools/oracle/dynamic_frida.py tools/oracle/hook.js tools/oracle/test_oracle.py
git commit -m "feat(oracle): frida userspace dynamic evidence + hook.js"
```

---

## Task 8: eBPF watcher client protocol (`watcher_client.py`)

**Files:**
- Create: `tools/oracle/watcher_client.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import watcher_client as wc  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402


def test_encode_decode_roundtrip():
    req = wc.encode_request(pid=1234, duration_s=5)
    assert json.loads(req.decode())["pid"] == 1234
    resp = wc.decode_response(json.dumps(
        {"ok": True, "syscalls": {"openat": 3}, "mmaps": ["model.gguf"], "files": []}).encode())
    assert resp["syscalls"]["openat"] == 3


def test_decode_response_error_raises():
    try:
        wc.decode_response(json.dumps({"ok": False, "error": "no such pid"}).encode())
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "no such pid" in str(e)


def test_query_watcher_against_fake_socket():
    with tempfile.TemporaryDirectory() as d:
        sock_path = os.path.join(d, "w.sock")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path); srv.listen(1)

        def serve():
            conn, _ = srv.accept()
            conn.recv(4096)
            conn.sendall(json.dumps({"ok": True, "syscalls": {"mmap": 1},
                                     "mmaps": [], "files": []}).encode())
            conn.close()
        t = threading.Thread(target=serve, daemon=True); t.start()
        out = wc.query_watcher(sock_path, pid=42, duration_s=1)
        assert out["syscalls"]["mmap"] == 1
        srv.close()
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'watcher_client'`.

- [ ] **Step 3: Implement `watcher_client.py`**

Create `tools/oracle/watcher_client.py`:

```python
"""Client for the root eBPF watcher daemon (revdev side; no caps needed).

Protocol: connect to the unix socket, send one JSON request line, read one JSON
response line. Request: {"pid": int, "duration_s": int}. Response:
{"ok": bool, "syscalls": {name: count}, "mmaps": [str], "files": [str], "error"?: str}.
"""
from __future__ import annotations

import json
import socket

DEFAULT_SOCK = "/run/oracle-watcher.sock"


def encode_request(*, pid: int, duration_s: int) -> bytes:
    return (json.dumps({"pid": pid, "duration_s": duration_s}) + "\n").encode()


def decode_response(raw: bytes) -> dict:
    resp = json.loads(raw.decode())
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "watcher error"))
    return {"syscalls": resp.get("syscalls", {}),
            "mmaps": resp.get("mmaps", []),
            "files": resp.get("files", [])}


def query_watcher(sock_path: str = DEFAULT_SOCK, *, pid: int, duration_s: int,
                  timeout: float = 120.0) -> dict:
    """Impure. Returns {syscalls, mmaps, files}; raises on watcher error/unreachable."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(sock_path)
    try:
        s.sendall(encode_request(pid=pid, duration_s=duration_s))
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
        return decode_response(b"".join(chunks))
    finally:
        s.close()
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `18 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/watcher_client.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): eBPF watcher client protocol"
```

---

## Task 9: eBPF watcher daemon (`watcher_daemon.py`)

Runs as **root** on dev-cx53. The protocol mirrors `watcher_client`. The bpftrace parse is pure-testable; the socket loop + bpftrace exec is integration-verified at deploy.

**Files:**
- Create: `tools/oracle/watcher_daemon.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import watcher_daemon as wd  # noqa: E402


def test_parse_bpftrace_syscall_counts():
    # bpftrace prints @syscalls[name]: count maps after exit
    out = "@syscalls[openat]: 4\n@syscalls[mmap]: 2\n@files[/m/model.gguf]: 1\n"
    parsed = wd.parse_bpftrace(out)
    assert parsed["syscalls"] == {"openat": 4, "mmap": 2}
    assert parsed["files"] == ["/m/model.gguf"]


def test_handle_request_bad_pid_returns_error():
    resp = wd.handle_request({"pid": -1, "duration_s": 1}, run=lambda pid, dur: {})
    assert resp["ok"] is False and "pid" in resp["error"]
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'watcher_daemon'`.

- [ ] **Step 3: Implement `watcher_daemon.py`**

Create `tools/oracle/watcher_daemon.py`:

```python
"""Root eBPF watcher daemon: unix socket -> PID-scoped bpftrace -> JSON.

Runs as root (NixOS systemd service, see hosts/dev-cx53/oracle-ebpf-watcher.nix).
The unprivileged revdev client never gains caps. parse_bpftrace + handle_request
are pure (tested); serve()/_run_bpftrace are the impure socket+exec loop.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess

DEFAULT_SOCK = "/run/oracle-watcher.sock"
_SYS = re.compile(r"@syscalls\[(?P<name>[^\]]+)\]:\s*(?P<n>\d+)")
_FILE = re.compile(r"@files\[(?P<path>[^\]]+)\]:\s*\d+")


def parse_bpftrace(out: str) -> dict:
    syscalls, files = {}, []
    for m in _SYS.finditer(out):
        syscalls[m.group("name")] = int(m.group("n"))
    for m in _FILE.finditer(out):
        files.append(m.group("path"))
    return {"syscalls": syscalls, "mmaps": [f for f in files if f.endswith(".gguf")],
            "files": files}


def _bpftrace_program(pid: int) -> str:
    return (
        f"tracepoint:raw_syscalls:sys_enter /pid == {pid}/ "
        f"{{ @syscalls[ksym(args.id)] = count(); }} "
        f"tracepoint:syscalls:sys_enter_openat /pid == {pid}/ "
        f"{{ @files[str(args.filename)] = count(); }}"
    )


def _run_bpftrace(pid: int, duration_s: int) -> dict:
    prog = _bpftrace_program(pid)
    proc = subprocess.run(["timeout", str(duration_s), "bpftrace", "-e", prog],
                          capture_output=True, text=True)
    return parse_bpftrace(proc.stdout)


def handle_request(req: dict, *, run=_run_bpftrace) -> dict:
    pid = req.get("pid")
    dur = int(req.get("duration_s", 5))
    if not isinstance(pid, int) or pid <= 0:
        return {"ok": False, "error": f"bad pid: {pid!r}"}
    try:
        data = run(pid, dur)
    except Exception as e:  # noqa: BLE001 - daemon must never crash on a request
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, **data}


def serve(sock_path: str = DEFAULT_SOCK) -> None:  # pragma: no cover (impure loop)
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    os.chmod(sock_path, 0o660)  # group-restricted; revdev added to the socket group
    srv.listen(4)
    while True:
        conn, _ = srv.accept()
        try:
            raw = conn.recv(65536)
            resp = handle_request(json.loads(raw.decode()))
            conn.sendall(json.dumps(resp).encode())
        except Exception:  # noqa: BLE001
            try:
                conn.sendall(json.dumps({"ok": False, "error": "bad request"}).encode())
            except OSError:
                pass
        finally:
            conn.close()


if __name__ == "__main__":  # pragma: no cover
    serve()
```

- [ ] **Step 4: Run to verify pass (pure tests)**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `20 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/watcher_daemon.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): root eBPF watcher daemon (bpftrace parse + socket serve)"
```

---

## Task 10: Kernel bridge (`bridge.py`)

**Files:**
- Create: `tools/oracle/bridge.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import bridge  # noqa: E402


def test_bridge_emits_observed_effects_shape():
    fdg = schema.build_finding(
        target={"path": "/p", "sha256": "0" * 64, "source_ref": "v"},
        decompiler={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
        functions=[], confidence=0.0)
    oe = bridge.to_observed_effects(fdg, files_written=["/p/notes.md"])
    assert oe == {"writes": ["/p/notes.md"], "deletes": []}


def test_bridge_attaches_transition_xref():
    fdg = schema.build_finding(
        target={"path": "/p", "sha256": "0" * 64, "source_ref": "v"},
        decompiler={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
        functions=[], confidence=0.0)
    out = bridge.attach_transition(fdg, "deadbeef" * 8)
    assert out["transition_xref"] == "deadbeef" * 8
    assert out is not fdg  # non-mutating
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'bridge'`.

- [ ] **Step 3: Implement `bridge.py`**

Create `tools/oracle/bridge.py`:

```python
"""Bridge an oracle finding to the aegis kernel's evidence seam.

The kernel (tools/dogfood/) consumes observed_effects = {writes, deletes}. Oracle
runs produce files (findings, reports) in its workspace; to_observed_effects exposes
those as the kernel-compatible shape. attach_transition links a finding to a kernel
transition by its content hash (double-dogfood; null in slice 1).
"""
from __future__ import annotations

import copy


def to_observed_effects(finding: dict, *, files_written: list[str] | None = None,
                        files_deleted: list[str] | None = None) -> dict:
    return {"writes": sorted(files_written or []), "deletes": sorted(files_deleted or [])}


def attach_transition(finding: dict, transition_hash: str) -> dict:
    out = copy.deepcopy(finding)
    out["transition_xref"] = transition_hash
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `22 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/bridge.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): kernel evidence-seam bridge"
```

---

## Task 11: Decision policy (`policy.py`)

The pure brain of the ralph loop: given the current loop state, decide the next action. Deterministic and fully unit-tested.

**Files:**
- Create: `tools/oracle/policy.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_oracle.py`:

```python
import policy  # noqa: E402


def test_policy_decompiles_unprocessed_function_first():
    state = policy.LoopState(functions=["a", "b"], results={}, iters=0, budget_iters=10)
    act = policy.next_action(state)
    assert act == {"action": "decompile", "fn": "a"}


def test_policy_refines_low_fidelity():
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": 0.2, "refined": True, "refine_passes": 0}},
        iters=1, budget_iters=10)
    assert policy.next_action(state) == {"action": "refine", "fn": "a"}


def test_policy_finalizes_when_all_above_threshold():
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": 0.95, "refined": True, "refine_passes": 0}},
        iters=1, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}


def test_policy_finalizes_when_budget_exhausted():
    state = policy.LoopState(functions=["a", "b"], results={}, iters=10, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}


def test_policy_stops_refining_after_max_passes():
    state = policy.LoopState(
        functions=["a"],
        results={"a": {"fidelity": 0.2, "refined": True, "refine_passes": policy.MAX_REFINE}},
        iters=5, budget_iters=10)
    assert policy.next_action(state) == {"action": "finalize"}
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'policy'`.

- [ ] **Step 3: Implement `policy.py`**

Create `tools/oracle/policy.py`:

```python
"""Pure decision policy for the oracle ralph loop.

Round-robin: decompile each function once, then refine any below the fidelity
threshold (bounded by MAX_REFINE passes), then finalize. Budget-exhaustion or
control-stop forces finalize (handled by the loop; the policy only sees budget).
"""
from __future__ import annotations

from dataclasses import dataclass

FIDELITY_THRESHOLD = 0.75
MAX_REFINE = 2


@dataclass
class LoopState:
    functions: list[str]
    results: dict[str, dict]   # fn -> {"fidelity": float, "refined": bool, "refine_passes": int}
    iters: int
    budget_iters: int


def next_action(state: LoopState) -> dict:
    if state.iters >= state.budget_iters:
        return {"action": "finalize"}
    # 1. any function not yet decompiled?
    for fn in state.functions:
        if fn not in state.results:
            return {"action": "decompile", "fn": fn}
    # 2. any below threshold with refine budget left?
    for fn in state.functions:
        r = state.results[fn]
        if (r.get("fidelity") or 0.0) < FIDELITY_THRESHOLD and r.get("refine_passes", 0) < MAX_REFINE:
            return {"action": "refine", "fn": fn}
    # 3. done
    return {"action": "finalize"}
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `27 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/policy.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): pure ralph-loop decision policy"
```

---

## Task 12: Loop orchestrator (`loop.py`)

Wires policy + producers + ledger + budget/control into the tick loop. Uses dependency-injected producer callables so the loop is unit-testable with fakes.

**Files:**
- Create: `tools/oracle/loop.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test**

Add to `test_oracle.py`:

```python
import loop  # noqa: E402


def test_loop_runs_to_finalize_with_fakes():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))

        def fake_decompile(fn):  # returns (pseudo_c, refined_c, fidelity)
            return (f"pseudo {fn}", f"int {fn}(){{}}", 0.9)

        def fake_refine(fn, prev):
            return (f"int {fn}(){{}} // refined", 0.95)

        def fake_dynamic(fn):
            return ({"calls": 1, "timing_ms": 0.1}, {"syscalls": {"mmap": 1}, "mmaps": [], "files": []})

        result = loop.run_loop(
            functions=["a", "b"],
            target={"path": "/bin/llama-cli", "sha256": "0" * 64, "source_ref": "vX"},
            decompiler_meta={"model": "llm4decompile-6.7b-v2", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=fake_decompile, refine=fake_refine, dynamic=fake_dynamic,
            budget_iters=20, control_path=None)

        assert result["kind"] == "oracle_finding"
        assert len(result["functions"]) == 2
        assert all(f["fidelity"]["score"] >= 0.75 for f in result["functions"])
        # ledger has decision entries + a final finding entry, and verifies
        kinds = [e["payload"]["kind"] for e in lg.entries()]
        assert "finding" in kinds and lg.verify() is True
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop'`.

- [ ] **Step 3: Implement `loop.py`**

Create `tools/oracle/loop.py`:

```python
"""Oracle ralph loop: control/budget gate -> policy -> run producer -> append ledger.

Producers are injected callables so the loop is testable with fakes:
  decompile(fn) -> (pseudo_c, refined_c, fidelity)
  refine(fn, prev_refined) -> (refined_c, fidelity)
  dynamic(fn) -> (frida_dict|None, ebpf_dict|None)
Control: if control_path is given, a JSON file with {"stop": true} halts the loop
(read each tick), mirroring ralph's live control.
"""
from __future__ import annotations

import json
import os

import policy
import schema


def _control_stop(control_path: str | None) -> bool:
    if not control_path or not os.path.exists(control_path):
        return False
    try:
        return bool(json.load(open(control_path)).get("stop"))
    except (OSError, json.JSONDecodeError):
        return False


def run_loop(*, functions, target, decompiler_meta, ledger_,
             decompile, refine, dynamic, budget_iters=50, control_path=None) -> dict:
    results: dict[str, dict] = {}
    iters = 0
    while True:
        if _control_stop(control_path):
            ledger_.append({"kind": "decision", "action": "control_stop"})
            break
        state = policy.LoopState(functions=functions, results=results,
                                 iters=iters, budget_iters=budget_iters)
        act = policy.next_action(state)
        ledger_.append({"kind": "decision", **act, "iter": iters})
        if act["action"] == "finalize":
            break
        fn = act["fn"]
        if act["action"] == "decompile":
            pseudo_c, refined_c, fid = decompile(fn)
            fr, eb = dynamic(fn)
            results[fn] = {"pseudo_c": pseudo_c, "refined": refined_c, "fidelity": fid,
                           "refine_passes": 0, "frida": fr, "ebpf": eb}
        elif act["action"] == "refine":
            refined_c, fid = refine(fn, results[fn]["refined"])
            results[fn]["refined"] = refined_c
            results[fn]["fidelity"] = fid
            results[fn]["refine_passes"] += 1
        iters += 1

    # assemble finding
    import hashlib
    fn_entries = []
    for fn in functions:
        r = results.get(fn)
        if not r:
            continue
        pseudo_sha = hashlib.sha256(r["pseudo_c"].encode()).hexdigest()
        fn_entries.append(schema.function_entry(
            name=fn, addr="0x0", pseudo_c_sha=pseudo_sha, refined_c=r["refined"],
            fidelity_score=r["fidelity"], frida=r["frida"], ebpf=r["ebpf"]))
    scores = [e["fidelity"]["score"] for e in fn_entries if e["fidelity"]["score"] is not None]
    confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
    finding = schema.build_finding(target=target, decompiler=decompiler_meta,
                                   functions=fn_entries, confidence=confidence)
    schema.validate_finding(finding)
    ledger_.append({"kind": "finding", "confidence": confidence,
                    "n_functions": len(fn_entries)})
    return finding
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `28 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/loop.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): ralph-loop orchestrator (policy+producers+ledger)"
```

---

## Task 13: CLI (`oracle.py`)

Wires the real producers (ghidra/llm/frida/watcher) into `run_loop` and persists the finding. Producer wiring is impure; a `--smoke` path uses a trivial built-in target for the CI smoke test (Task 16).

**Files:**
- Create: `tools/oracle/oracle.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test (arg parsing + finding persistence are pure-ish)**

Add to `test_oracle.py`:

```python
import oracle as oracle_cli  # noqa: E402


def test_persist_finding_writes_hashed_file():
    with tempfile.TemporaryDirectory() as d:
        fdg = schema.build_finding(
            target={"path": "/p", "sha256": "0" * 64, "source_ref": "v"},
            decompiler={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            functions=[], confidence=0.0)
        path = oracle_cli.persist_finding(fdg, findings_dir=d)
        assert os.path.exists(path) and path.endswith(".json")
        assert json.load(open(path))["kind"] == "oracle_finding"


def test_parse_args_funcs_splits_csv():
    ns = oracle_cli.parse_args(["run", "--target", "/bin/x", "--funcs", "a,b,c"])
    assert ns.funcs == ["a", "b", "c"] and ns.target == "/bin/x"
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 tools/oracle/test_oracle.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'oracle'`.

- [ ] **Step 3: Implement `oracle.py`**

Create `tools/oracle/oracle.py`:

```python
#!/usr/bin/env python3
"""vaked-oracle CLI: drive the RE ralph loop end-to-end on a target binary.

Usage:
  oracle run --target /path/to/llama-cli --funcs ggml_compute,llama_decode \
             --analyze-headless <path> --server http://127.0.0.1:8080/completion \
             --source-dir <llama.cpp src> --watcher-sock /run/oracle-watcher.sock \
             --infer-cmd "llama-cli -m model.gguf -p hello -n 8"
Heavy work runs on dev-cx53; never on the M3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge      # noqa: E402
import dynamic_frida as dfr  # noqa: E402
import fidelity    # noqa: E402
import ghidra_frontend as gf  # noqa: E402
import ledger      # noqa: E402
import llm_refine  # noqa: E402
import loop        # noqa: E402
import watcher_client as wc  # noqa: E402

ORACLE_DIR = os.environ.get("ORACLE_DIR", ".oracle")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="oracle")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--target", required=True)
    r.add_argument("--funcs", required=True, type=lambda s: [x for x in s.split(",") if x])
    r.add_argument("--analyze-headless", default=os.environ.get("ANALYZE_HEADLESS", "analyzeHeadless"))
    r.add_argument("--server", default=llm_refine.DEFAULT_SERVER)
    r.add_argument("--source-dir", default=None, help="llama.cpp source for fidelity ground truth")
    r.add_argument("--watcher-sock", default=wc.DEFAULT_SOCK)
    r.add_argument("--infer-cmd", default=None, help="command to drive a live inference")
    r.add_argument("--budget-iters", type=int, default=50)
    r.add_argument("--control", default=None)
    return p.parse_args(argv)


def persist_finding(finding: dict, *, findings_dir: str) -> str:
    os.makedirs(findings_dir, exist_ok=True)
    h = hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()
    path = os.path.join(findings_dir, f"{h}.json")
    with open(path, "w") as fh:
        json.dump(finding, fh, indent=2, sort_keys=True)
    return path


def _ground_truth(source_dir: str | None, fn: str) -> str | None:
    """Best-effort: grep the source tree for the function body. None if unavailable."""
    if not source_dir:
        return None
    import subprocess
    try:
        out = subprocess.run(["grep", "-rl", fn + "(", source_dir],
                             capture_output=True, text=True, timeout=30).stdout
        first = out.splitlines()[0] if out.strip() else None
        return open(first).read() if first else None
    except Exception:  # noqa: BLE001
        return None


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_run(ns: argparse.Namespace) -> int:
    decomp_map = gf.run_ghidra(analyze_headless=ns.analyze_headless,
                               binary=ns.target, functions=ns.funcs)

    def decompile(fn):
        pseudo_c = decomp_map.get(fn, "")
        refined = llm_refine.refine(pseudo_c, server=ns.server) if pseudo_c else None
        gt = _ground_truth(ns.source_dir, fn)
        fid = fidelity.score(refined or "", gt) if (refined and gt) else None
        return (pseudo_c, refined, fid)

    def refine_fn(fn, prev):
        refined = llm_refine.refine(decomp_map.get(fn, ""), server=ns.server)
        gt = _ground_truth(ns.source_dir, fn)
        fid = fidelity.score(refined or "", gt) if (refined and gt) else None
        return (refined, fid)

    def dynamic(fn):
        frida = ebpf = None
        if ns.infer_cmd:
            try:
                frida = dfr.run_frida(target_cmd=ns.infer_cmd.split(), functions=[fn]).get(fn)
            except Exception:  # noqa: BLE001 (degrade, never crash)
                frida = None
        return (frida, ebpf)

    lg = ledger.Ledger(os.path.join(ORACLE_DIR, "events.jsonl"))
    finding = loop.run_loop(
        functions=ns.funcs,
        target={"path": ns.target, "sha256": _sha256_file(ns.target),
                "source_ref": ns.source_dir or "unknown"},
        decompiler_meta={"model": "llm4decompile-6.7b-v2", "model_sha256": "unknown", "temperature": 0},
        ledger_=lg, decompile=decompile, refine=refine_fn, dynamic=dynamic,
        budget_iters=ns.budget_iters, control_path=ns.control)
    finding["observed_effects"] = bridge.to_observed_effects(
        finding, files_written=[os.path.join(ORACLE_DIR, "findings")])
    path = persist_finding(finding, findings_dir=os.path.join(ORACLE_DIR, "findings"))
    print(f"finding: {path}  confidence={finding['confidence']}  chain_ok={lg.verify()}")
    return 0


def main(argv: list[str]) -> int:
    ns = parse_args(argv)
    if ns.cmd == "run":
        return cmd_run(ns)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

> Note: `dynamic()` wires Frida only; the eBPF watcher call (`wc.query_watcher`)
> is added in Task 15 once the watcher service is deployed, to keep this task's
> tests green without a live socket.

- [ ] **Step 4: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `30 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/oracle.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): CLI wiring (ghidra+llm+frida -> loop -> finding)"
```

---

## Task 14: Vaked POLA graph (`oracle-re-loop.vaked`)

Declare the loop's capabilities in Vaked so oracle's POLA is lowered from a declaration (symmetry with the aegis kernel). Validated with `vakedc check`.

**Files:**
- Create: `vaked/examples/oracle-re-loop.vaked`

- [ ] **Step 1: Inspect the existing pattern**

Run: `cat vaked/examples/ralph-dogfood-loop.vaked`
Note the `mesh`/`meshNode` structure, the `capabilities` refs, and `writeScope`.

- [ ] **Step 2: Author `vaked/examples/oracle-re-loop.vaked`**

Create `vaked/examples/oracle-re-loop.vaked` mirroring `ralph-dogfood-loop.vaked`, with two principals:

```
// vaked-oracle RE loop — POLA source of truth (lowered via scope_from_vaked.py).
// The analyst (revdev) writes only its workspace; the watcher reads kernel evidence.
mesh oracleReLoop {
  meshNode analyst {
    role = "re-analyst"
    capabilities = [ fs.repo_rw, network.loopback, mem.recall ]
    writeScope = [ ".oracle", "docs/oracle" ]
    model = "llm4decompile-6.7b-v2"
    track = "oracle-re"
  }
  meshNode watcher {
    role = "ebpf-witness"
    capabilities = [ fs.repo_ro, mem.append ]
  }
}
```

> Match the exact grammar of `ralph-dogfood-loop.vaked` (field order, `fs.*`/`network.*`
> ref spelling, block syntax). Adjust the snippet above to whatever that file uses;
> the two principals + the `writeScope` on `analyst` are the requirement.

- [ ] **Step 3: Validate it parses + checks**

Run: `python3 -m vakedc check vaked/examples/oracle-re-loop.vaked`
Expected: PASS (no check errors). If `vakedc` is invoked differently, mirror the
command shown in `tools/dogfood/README.md` / the dogfood Taskfile.

- [ ] **Step 4: Verify scope lowering**

Run:
```bash
python3 -m vakedc parse vaked/examples/oracle-re-loop.vaked   # produces .vaked/graph.json
python3 tools/dogfood/scope_from_vaked.py --principal analyst  # or the file's documented invocation
```
Expected: prints `[".oracle", "docs/oracle"]` for `analyst`; `[]` for `watcher` (read-only).

- [ ] **Step 5: Commit**

```bash
git add vaked/examples/oracle-re-loop.vaked
git commit -m "feat(oracle): RE loop as a checked Vaked capability graph (POLA source)"
```

---

## Task 15: eBPF watcher NixOS module + wire the client (`oracle-ebpf-watcher.nix`)

Deploys the root watcher on dev-cx53 and wires `oracle.py`'s `dynamic()` to call it. **Runs on the box; never build on the M3.**

**Files:**
- Create: `hosts/dev-cx53/oracle-ebpf-watcher.nix`
- Modify: `hosts/dev-cx53/default.nix` (import the module — confirm the host's import list filename)
- Modify: `tools/oracle/oracle.py:dynamic` (add the watcher call)

- [ ] **Step 1: Author the NixOS module**

Create `hosts/dev-cx53/oracle-ebpf-watcher.nix`:

```nix
{ config, lib, pkgs, ... }:

# Root eBPF watcher for vaked-oracle. Exposes a unix socket; the unprivileged
# revdev client (watcher_client.py) requests PID-scoped bpftrace evidence. revdev
# never gains CAP_BPF/CAP_PERFMON — the socket is the entire attenuation surface.
let
  watcher = ../../tools/oracle/watcher_daemon.py;
in
{
  systemd.services.oracle-ebpf-watcher = {
    description = "vaked-oracle eBPF watcher (root; PID-scoped bpftrace over a unix socket)";
    after = [ "network.target" ];
    wantedBy = [ "multi-user.target" ];
    path = [ pkgs.bpftrace pkgs.coreutils ];
    serviceConfig = {
      Type = "simple";
      ExecStart = "${pkgs.python3}/bin/python3 ${watcher}";
      Restart = "on-failure";
      RestartSec = 3;
      # socket is created at /run/oracle-watcher.sock, group-restricted (0o660)
      RuntimeDirectory = "oracle-watcher";
      Group = "oracle-watcher";
    };
  };

  users.groups.oracle-watcher = { };
  # let revdev reach the socket without caps
  users.users.revdev.extraGroups = [ "oracle-watcher" ];
}
```

> The socket path in `watcher_daemon.py` is `/run/oracle-watcher.sock`. If you prefer
> it under the systemd `RuntimeDirectory`, set the daemon's `DEFAULT_SOCK` to
> `/run/oracle-watcher/sock` and update `watcher_client.DEFAULT_SOCK` + Task 8/9 tests.

- [ ] **Step 2: Import the module in the host**

Find the host's module import list:
```bash
grep -rn "revdev.nix\|imports = \[" hosts/dev-cx53/ | head
```
Add `./oracle-ebpf-watcher.nix` to the same `imports = [ ... ]` that includes `./revdev.nix`.

- [ ] **Step 3: Wire the watcher into `oracle.py`'s `dynamic()`**

In `tools/oracle/oracle.py`, replace the `dynamic(fn)` body inside `cmd_run` with:

```python
    def dynamic(fn):
        frida = ebpf = None
        if ns.infer_cmd:
            import subprocess
            proc = subprocess.Popen(ns.infer_cmd.split())
            try:
                ebpf = wc.query_watcher(ns.watcher_sock, pid=proc.pid, duration_s=5)
            except Exception:  # noqa: BLE001 (degrade)
                ebpf = None
            try:
                frida = dfr.run_frida(target_cmd=ns.infer_cmd.split(), functions=[fn]).get(fn)
            except Exception:  # noqa: BLE001
                frida = None
            finally:
                proc.wait(timeout=60)
        return (frida, ebpf)
```

- [ ] **Step 4: Re-run unit tests (no live socket needed — `dynamic` is only called in `cmd_run`)**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `30 passed, 0 failed` (unchanged — the watcher call is inside the impure CLI path).

- [ ] **Step 5: Deploy + verify on dev-cx53 (ON THE BOX)**

```bash
ssh dev@100.105.72.88
cd ~/nix-base-revdev   # the live-config worktree
# copy/sync this branch's oracle-ebpf-watcher.nix into the nix-base host dir,
# then:
sudo nixos-rebuild switch --flake .#dev-cx53 \
  --option access-tokens "github.com=$(gh auth token)"
systemctl is-active oracle-ebpf-watcher          # expect: active
ls -l /run/oracle-watcher.sock                   # expect: srw-rw---- root oracle-watcher
# as revdev, smoke the socket against a live pid:
sudo -u revdev bash -lc 'sleep 30 & python3 tools/oracle/watcher_client.py --pid $! --duration 3'
```
Expected: JSON with a non-empty `syscalls` map.

> Note: `nix-base` (the box config) and `vaked-base` (this repo) are separate repos.
> The `.nix` module is authored here for review; deploying it means landing it in
> the `nix-base` host config. Coordinate that as a `nix-base` change (out of this
> repo's CI). Document the exact path mapping in `docs/oracle/integration.md`.

- [ ] **Step 6: Commit**

```bash
git add hosts/dev-cx53/oracle-ebpf-watcher.nix tools/oracle/oracle.py
git commit -m "feat(oracle): root eBPF watcher NixOS module + client wiring"
```

---

## Task 16: Taskfile, docs, CI smoke + acceptance demo

**Files:**
- Create: `tools/oracle/Taskfile.yml`
- Create: `docs/oracle/README.md`, `docs/oracle/v0.md`, `docs/oracle/integration.md`
- Test: `tools/oracle/test_oracle.py` (add the smoke test)

- [ ] **Step 1: Add a CI-able end-to-end smoke test on a trivial binary**

Add to `test_oracle.py`:

```python
def test_smoke_end_to_end_with_fakes_persists_and_verifies():
    """Full loop -> finding -> persist -> reload, all with fakes (no ghidra/llm/frida)."""
    import oracle as oc
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        finding = loop.run_loop(
            functions=["main"],
            target={"path": "/bin/true", "sha256": "0" * 64, "source_ref": "vX"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("pseudo", "int main(){return 0;}", 0.99),
            refine=lambda fn, prev: ("int main(){return 0;}", 0.99),
            dynamic=lambda fn: (None, None),
            budget_iters=10, control_path=None)
        path = oc.persist_finding(finding, findings_dir=os.path.join(d, "findings"))
        reloaded = json.load(open(path))
        schema.validate_finding(reloaded)
        assert reloaded["confidence"] >= 0.75 and lg.verify()
```

- [ ] **Step 2: Run to verify pass**

Run: `python3 tools/oracle/test_oracle.py`
Expected: `31 passed, 0 failed`.

- [ ] **Step 3: Create `tools/oracle/Taskfile.yml`**

```yaml
version: '3'

# vaked-oracle ops. Heavy tasks run on dev-cx53 (never the M3).
vars:
  TARGET: '{{.TARGET | default "/etc/profiles/per-user/revdev/bin/llama-cli"}}'
  FUNCS: '{{.FUNCS | default "llama_decode,ggml_compute_forward,llama_model_load"}}'
  SERVER: '{{.SERVER | default "http://127.0.0.1:8080/completion"}}'

tasks:
  default:
    cmds: [task --list]

  test:
    desc: run oracle unit tests
    cmds:
      - python3 tools/oracle/test_oracle.py

  model:fetch:
    desc: download the llm4decompile-6.7B GGUF into the oracle model dir (dev-cx53)
    cmds:
      - mkdir -p ~/oracle/models
      - echo "fetch the chosen GGUF (see docs/oracle/v0.md open items) into ~/oracle/models"

  llm:serve:
    desc: serve llm4decompile via llama-server on :8080 (dev-cx53)
    cmds:
      - llama-server -m ~/oracle/models/llm4decompile-6.7b-v2.gguf --port 8080 -c 4096

  run:
    desc: run the RE loop on the target (dev-cx53)
    cmds:
      - >
        python3 tools/oracle/oracle.py run
        --target {{.TARGET}} --funcs {{.FUNCS}}
        --analyze-headless "$ANALYZE_HEADLESS"
        --server {{.SERVER}}
        --source-dir "$LLAMA_CPP_SRC"
        --infer-cmd "{{.TARGET}} -m $LLAMA_DEMO_MODEL -p hi -n 8"
```

- [ ] **Step 4: Write the docs**

Create `docs/oracle/README.md` (onboarding: mental model, the recursive RE-the-LLM-runtime framing, quickstart `task -d tools/oracle test` then the dev-cx53 run, lane boundaries), `docs/oracle/v0.md` (copy the architecture + schema + open items from the spec), and `docs/oracle/integration.md` (the kernel evidence-seam bridge + the nix-base↔vaked-base watcher path mapping from Task 15).

Minimum content for each — no placeholders; mirror `docs/dogfood/README.md` structure. (Author full prose here; cross-link the spec at `docs/superpowers/specs/2026-06-15-vaked-oracle-design.md`.)

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/Taskfile.yml docs/oracle/ tools/oracle/test_oracle.py
git commit -m "feat(oracle): Taskfile, docs, CI smoke test"
```

---

## Task 17: Manual acceptance demo (dev-cx53)

Not a code task — the slice-1 acceptance run. **All on the box.**

- [ ] **Step 1: Prereqs on dev-cx53**
  - llm4decompile-6.7B GGUF fetched (`task -d tools/oracle model:fetch`, then place the GGUF).
  - `task -d tools/oracle llm:serve` running (llama-server :8080).
  - `analyzeHeadless` path exported as `ANALYZE_HEADLESS` (locate under the nix ghidra package).
  - llama.cpp source for the runtime's version checked out; export `LLAMA_CPP_SRC`.
  - `oracle-ebpf-watcher` service active (Task 15).

- [ ] **Step 2: Run the loop over ~3 functions**

```bash
task -d tools/oracle run \
  FUNCS="llama_decode,ggml_compute_forward,llama_model_load"
```

- [ ] **Step 3: Verify acceptance**
  - A finding JSON exists under `.oracle/findings/<hash>.json`.
  - It has 3 function entries, each with `refined_c` and a non-null `fidelity.score`.
  - At least one function has non-null `dynamic.frida` and/or `dynamic.ebpf`.
  - `chain_ok=True` printed (ledger replay-verifies).

- [ ] **Step 4: Record the result**

Append the demo transcript + the finding summary to `docs/oracle/v0.md` under an "Acceptance run (2026-…)" heading. Commit.

---

## Self-Review

**Spec coverage:**
- §1 context / recursion framing → docs (Task 16), README/v0.
- §2 goal/acceptance → Tasks 12 (loop), 17 (acceptance demo).
- §3 decisions → all tasks honor them (6.7B in llm_refine/CLI; Frida+eBPF in Tasks 7/9/15; standalone+bridge in Task 10).
- §4 components → Tasks 2–13 (one per file).
- §5 data flow → Task 12 loop + Task 13 CLI wiring.
- §6 finding schema → Task 2.
- §7 ralph loop (ledger/budget/control) → Tasks 3 (ledger over ralphcore), 11 (policy), 12 (control+budget gate).
- §8 eBPF watcher → Tasks 8 (client), 9 (daemon), 15 (nix module).
- §9 error handling / degrade → nullable producers in Tasks 9 (`handle_request` try), 12/13 (`dynamic` try/except), schema nullable fields (Task 2).
- §10 testing → unit tests every task + smoke (Task 16) + acceptance (Task 17).
- §11 boundaries → ralphcore imported read-only (Task 3); watcher socket attenuation (Tasks 9/15); sample-run no-net (Task 7); heavy-work-on-box notes (Tasks 13/15/17).
- §12 open items → flagged inline (model card template in Task 5; analyzeHeadless path in Tasks 6/16/17; ground-truth source mapping in Task 13/17; socket path in Task 15).
- POLA-from-Vaked (§7) → Task 14.

**Placeholder scan:** the only deferred specifics are genuine spec "open items" (exact GGUF variant/template wording, analyzeHeadless absolute path, exact `.vaked` grammar spelling) — each is called out with how to resolve it at implementation, and the pure logic around them is fully tested. No `TODO`/`add error handling`/`similar to` placeholders.

**Type consistency:** `schema.function_entry`/`build_finding` keys match `loop.run_loop`'s assembly and `bridge`/CLI reads; `ledger.append` returns ralphcore entries (`seq/prev/payload/hash`) consumed consistently in Tasks 3/12; `watcher_client`/`watcher_daemon` share the `{ok,syscalls,mmaps,files,error}` shape; `policy.LoopState` fields match `loop.run_loop` construction.

Running test counts are cumulative and consistent: 3→5→8→11→13→15→18→20→22→27→28→30→31.
