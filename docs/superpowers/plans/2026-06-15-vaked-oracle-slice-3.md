# vaked-oracle slice 3 — agentic reverser — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Swap the oracle loop's fixed `policy.next_action` for an LLM-driven brain over a bounded action set `{decompile, refine, investigate, finalize}`, plus a hybrid `investigate` action backed by crabcc (C ground-truth source) with a binutils fallback. Replay-stable, deterministic fallback, grounds via slice-2.

**Architecture:** New `agent.py` (LLM brain + parse + fallback + litellm client) and `investigate.py` (crabcc/binutils adapter). `loop.run_loop` gains optional `decide=`/`investigate=` params — defaults preserve slice-1/2 behavior exactly. `LoopState` gains `observations`. CLI `run --agent` wires the brain.

**Tech Stack:** Pure-Python stdlib (urllib for HTTP, subprocess for crabcc/nm). Local LLM via revdev `oq`/litellm `:4000`. All M3-safe except the gated on-box acceptance.

**Spec:** `docs/superpowers/specs/2026-06-15-vaked-oracle-slice-3-design.md`

---

## Key facts (verified)

- `loop.run_loop(*, functions, target, decompiler_meta, ledger_, decompile, refine, dynamic, budget_iters=50, control_path=None)` calls `policy.next_action(state)` each tick and logs `{"kind":"decision", **act, "iter":iters}`.
- `policy.LoopState` is a dataclass `(functions, results, iters, budget_iters)`; `policy.next_action` returns `{"action":"decompile"|"refine"|"finalize", "fn"?}`; `FIDELITY_THRESHOLD=0.75`, `MAX_REFINE=2`.
- `ledger.Ledger(path)`: `.append(payload)->entry`, `.entries()`, `.verify()`.
- crabcc 6.3.0: `crabcc --root <dir> lookup <sym|callers|refs|outline|fuzzy> <name>` → JSON. Indexes C, not C++ (`.cpp` skipped).
- `oracle.py` `run` subparser + `cmd_run` build the producers and call `loop.run_loop`.
- `test_oracle.py` is a stdlib runner; add `test_*` functions. Baseline: 41 passing.

---

## File Structure

- **Create:** `tools/oracle/agent.py` — `build_prompt`, `parse_action`, `make_policy`, `LiteLLMClient`.
- **Create:** `tools/oracle/investigate.py` — `crabcc_query`, `binutils_query`, `make_investigator`.
- **Modify:** `tools/oracle/policy.py` — add `observations` field to `LoopState`.
- **Modify:** `tools/oracle/loop.py` — `decide=`/`investigate=` params; handle `investigate`; thread `observations`.
- **Modify:** `tools/oracle/oracle.py` — `run --agent` + LLM/crabcc flags; wire brain in `cmd_run`.
- **Modify:** `tools/oracle/test_oracle.py` — 8 new tests (41→49).
- **Modify:** `docs/oracle/README.md` + `docs/oracle/v0.md` — agentic-mode note.

---

## Task 1: `agent.py` — the LLM brain (parse + fallback)

**Files:** Create `tools/oracle/agent.py`; Test `tools/oracle/test_oracle.py`.

- [ ] **Step 1: Write failing tests** (append to `test_oracle.py`)

```python
# --- slice 3: agentic reverser ---------------------------------------------
import agent as _agent  # noqa: E402
import investigate as _inv  # noqa: E402


def _state(functions=("a", "b"), results=None, iters=0, budget=20, observations=None):
    return policy.LoopState(functions=list(functions), results=results or {},
                            iters=iters, budget_iters=budget,
                            observations=observations or [])


def test_agent_decide_parses_llm_action():
    decide = _agent.make_policy(lambda p: '{"action":"decompile","fn":"a","rationale":"start"}')
    act = decide(_state())
    assert act["action"] == "decompile" and act["fn"] == "a" and act["rationale"] == "start"


def test_agent_decide_falls_back_on_garbage():
    decide = _agent.make_policy(lambda p: "not json at all")
    assert decide(_state()) == policy.next_action(_state())   # deterministic fallback


def test_agent_decide_rejects_out_of_menu():
    d1 = _agent.make_policy(lambda p: '{"action":"rm","fn":"a"}')
    assert d1(_state()) == policy.next_action(_state())          # bad action -> fallback
    d2 = _agent.make_policy(lambda p: '{"action":"decompile","fn":"zzz"}')
    assert d2(_state()) == policy.next_action(_state())          # fn not in functions -> fallback
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'agent'`)

Run: `python3 tools/oracle/test_oracle.py 2>&1 | grep -E "agent|Error" | head`

- [ ] **Step 3: Write `tools/oracle/agent.py`**

```python
"""Agentic brain for the oracle loop — an LLM picks the next action (slice 3).

Replaces policy.next_action's fixed round-robin with an LLM decision over the same
bounded action set {decompile, refine, investigate, finalize}. Deterministic at the
action layer; the LLM only selects among recorded primitives. Any parse/validation
failure falls back to policy.next_action, so a flaky model can never derail or
unbound the loop. temperature=0 ⇒ replayable.
"""
from __future__ import annotations

import json
import os
import urllib.request

import policy

ACTIONS = ("decompile", "refine", "investigate", "finalize")


def build_prompt(state, *, threshold=0.75, max_refine=2) -> str:
    lines = ["You are a reverse-engineering planner. Pick ONE next action.",
             f"Functions under analysis: {state.functions}",
             "Current results (fn -> fidelity / refine_passes / has_dynamic):"]
    for fn in state.functions:
        r = state.results.get(fn)
        if r is None:
            lines.append(f"  {fn}: not yet decompiled")
        else:
            lines.append(f"  {fn}: fidelity={r.get('fidelity')} "
                         f"refine_passes={r.get('refine_passes', 0)} "
                         f"has_dynamic={bool(r.get('frida') or r.get('ebpf'))}")
    obs = getattr(state, "observations", []) or []
    if obs:
        lines.append("Recent investigations:")
        lines += [f"  {json.dumps(o)[:300]}" for o in obs[-5:]]
    lines.append(f"Budget: iter {state.iters}/{state.budget_iters}.")
    lines.append(f"Rules: decompile a function before refining it; refine only functions "
                 f"below fidelity {threshold} with < {max_refine} refine passes; use "
                 f"investigate to learn a function's signature/callers/refs; finalize when "
                 f"no useful action remains or budget is low.")
    lines.append('Reply with ONE JSON object only, e.g. '
                 '{"action":"decompile","fn":"NAME","rationale":"..."} or '
                 '{"action":"investigate","query":{"kind":"sym","name":"NAME"},"rationale":"..."} or '
                 '{"action":"finalize","rationale":"..."}. action in ' + str(list(ACTIONS)) + ".")
    return "\n".join(lines)


def parse_action(raw: str, state) -> dict:
    """Extract + validate the first JSON action object. Raises ValueError on any
    violation (caller falls back to the deterministic policy)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in LLM reply")
    obj = json.loads(raw[start:end + 1])
    act = obj.get("action")
    if act not in ACTIONS:
        raise ValueError(f"action {act!r} not in {ACTIONS}")
    rationale = str(obj.get("rationale", ""))
    if act in ("decompile", "refine"):
        fn = obj.get("fn")
        if fn not in state.functions:
            raise ValueError(f"fn {fn!r} not in functions")
        return {"action": act, "fn": fn, "rationale": rationale}
    if act == "investigate":
        q = obj.get("query")
        if not isinstance(q, dict) or "kind" not in q or "name" not in q:
            raise ValueError("investigate needs query{kind,name}")
        return {"action": "investigate",
                "query": {"kind": str(q["kind"]), "name": str(q["name"])},
                "rationale": rationale}
    return {"action": "finalize", "rationale": rationale}


def make_policy(llm_call, *, model="?", threshold=0.75, max_refine=2):
    """decide(state) -> action using llm_call(prompt)->str. Deterministic fallback."""
    def decide(state):
        try:
            raw = llm_call(build_prompt(state, threshold=threshold, max_refine=max_refine))
            act = parse_action(raw, state)
            act["model"] = model
            return act
        except Exception:  # noqa: BLE001 — any failure ⇒ deterministic policy
            return policy.next_action(state)
    return decide


class LiteLLMClient:
    """Thin OpenAI-chat client for the local litellm gateway (revdev `oq`, :4000)."""

    def __init__(self, *, endpoint="http://127.0.0.1:4000/v1/chat/completions",
                 model="qwen2.5-coder:7b", key=None, timeout=120):
        self.endpoint, self.model = endpoint, model
        self.key = key or os.environ.get("LITELLM_KEY", "")
        self.timeout = timeout

    def __call__(self, prompt: str) -> str:
        body = json.dumps({"model": self.model, "temperature": 0,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(self.endpoint, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (loopback gateway)
            return json.load(r)["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Add the `observations` field to `policy.LoopState`**

In `tools/oracle/policy.py`, change the imports + dataclass:

```python
from dataclasses import dataclass, field
```

```python
@dataclass
class LoopState:
    functions: list[str]
    results: dict[str, dict]
    iters: int
    budget_iters: int
    observations: list = field(default_factory=list)
```

- [ ] **Step 5: Run — expect PASS** (`44 passed`)

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -2`

- [ ] **Step 6: Commit**

```bash
git add tools/oracle/agent.py tools/oracle/policy.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): agent.py — LLM-driven loop brain with deterministic fallback"
```

---

## Task 2: `investigate.py` — crabcc + binutils adapter

**Files:** Create `tools/oracle/investigate.py`; Test `tools/oracle/test_oracle.py`.

- [ ] **Step 1: Write failing tests** (append to `test_oracle.py`)

```python
def test_investigate_crabcc_adapter_parses():
    def fake_runner(cmd, timeout=30):
        assert cmd[:5] == ["crabcc", "--root", "SRC", "lookup", "sym"]
        return 0, '[{"name":"ggml_compute_forward","signature":"int ggml_compute_forward(int)"}]'
    investigate = _inv.make_investigator(source_root="SRC", runner=fake_runner)
    obs = investigate({"kind": "sym", "name": "ggml_compute_forward"})
    assert obs["provider"] == "crabcc" and obs["result"][0]["name"] == "ggml_compute_forward"


def test_investigate_binutils_fallback():
    def fake_runner(cmd, timeout=30):
        return (0, "0000000000001234 T ggml_compute_forward\n") if cmd[0] == "nm" else (1, "")
    investigate = _inv.make_investigator(binary="/lib/libggml.so", runner=fake_runner)
    obs = investigate({"kind": "sym", "name": "ggml_compute_forward"})
    assert obs["provider"] == "binutils" and obs["result"]["found"] is True


def test_investigate_never_raises_returns_none():
    def boom(cmd, timeout=30):
        raise RuntimeError("crabcc exploded")
    investigate = _inv.make_investigator(source_root="SRC", runner=boom)
    assert investigate({"kind": "sym", "name": "x"})["provider"] == "none"
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'investigate'`)

- [ ] **Step 3: Write `tools/oracle/investigate.py`**

```python
"""Read-only structural investigation for the agentic reverser (slice 3).

The hybrid 'investigate' action: answer a function query (signature / callers /
refs / outline / fuzzy) from crabcc over the C ground-truth source (crabcc indexes
C, not C++ — so ggml.c + C headers like llama.h/ggml.h), falling back to binutils
over the target binary, else a 'none' observation. Never raises — investigation
must never crash the loop.
"""
from __future__ import annotations

import json
import subprocess

_CRABCC_KINDS = ("sym", "callers", "refs", "outline", "fuzzy")


def _run(cmd, *, timeout=30):
    """Run a command -> (rc, stdout). Injectable via make_investigator(runner=...)."""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # noqa: S603
    return p.returncode, p.stdout


def crabcc_query(query, *, source_root, crabcc="crabcc", runner=_run):
    kind, name = query.get("kind"), query.get("name")
    if kind not in _CRABCC_KINDS or not name:
        return None
    rc, out = runner([crabcc, "--root", source_root, "lookup", kind, name])
    if rc != 0 or not out.strip():
        return None
    try:
        result = json.loads(out)
    except json.JSONDecodeError:
        result = out.strip()[:1000]
    return {"query": query, "provider": "crabcc", "result": result}


def binutils_query(query, *, binary, runner=_run):
    kind, name = query.get("kind"), query.get("name")
    if not binary or not name:
        return None
    if kind in ("sym", "fuzzy"):
        rc, out = runner(["nm", "-C", "--defined-only", binary])
        if rc != 0:
            return None
        hits = [ln for ln in out.splitlines() if name in ln][:20]
        return {"query": query, "provider": "binutils",
                "result": {"symbols": hits, "found": bool(hits)}}
    return {"query": query, "provider": "binutils",
            "result": {"note": f"{kind} not available from a binary"}}


def make_investigator(*, source_root=None, binary=None, crabcc="crabcc", runner=_run):
    """investigate(query) -> observation. crabcc-preferred, binutils fallback, 'none'
    if neither usable. Never raises."""
    def investigate(query):
        try:
            if source_root:
                obs = crabcc_query(query, source_root=source_root, crabcc=crabcc, runner=runner)
                if obs is not None:
                    return obs
            if binary:
                obs = binutils_query(query, binary=binary, runner=runner)
                if obs is not None:
                    return obs
        except Exception:  # noqa: BLE001 — investigation must never crash the loop
            pass
        return {"query": query, "provider": "none", "result": None}
    return investigate
```

- [ ] **Step 4: Run — expect PASS** (`47 passed`)

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/investigate.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): investigate.py — crabcc (C) + binutils read-only adapter"
```

---

## Task 3: Loop integration — inject brain + handle `investigate`

**Files:** Modify `tools/oracle/loop.py`; Test `tools/oracle/test_oracle.py`.

- [ ] **Step 1: Write failing tests** (append to `test_oracle.py`)

```python
def test_loop_agentic_drives_to_finalize():
    with tempfile.TemporaryDirectory() as d:
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        script = iter([
            '{"action":"investigate","query":{"kind":"sym","name":"a"},"rationale":"scout"}',
            '{"action":"decompile","fn":"a","rationale":"go"}',
            '{"action":"finalize","rationale":"done"}',
        ])
        decide = _agent.make_policy(lambda p: next(script))
        investigate = _inv.make_investigator(source_root="SRC",
            runner=lambda cmd, timeout=30: (0, '[{"name":"a"}]'))
        finding = loop.run_loop(
            functions=["a"],
            target={"path": "/bin/x", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("p", "int a(){}", 0.9),
            refine=lambda fn, prev: ("int a(){}", 0.95),
            dynamic=lambda fn: (None, None),
            budget_iters=10, decide=decide, investigate=investigate)
        assert finding["kind"] == "oracle_finding"
        payloads = [e["payload"] for e in lg.entries()]
        kinds = [p["kind"] for p in payloads]
        assert "observation" in kinds and "finding" in kinds
        decs = [p for p in payloads if p["kind"] == "decision"]
        assert any(p.get("rationale") == "go" and p.get("model") for p in decs)
        assert lg.verify()


def test_loop_default_brain_unchanged():
    """No decide/investigate ⇒ identical finding + ledger to explicit policy.next_action."""
    def run(d, **extra):
        lg = ledger.Ledger(os.path.join(d, "events.jsonl"))
        f = loop.run_loop(
            functions=["a", "b"],
            target={"path": "/bin/x", "sha256": "0" * 64, "source_ref": "v"},
            decompiler_meta={"model": "m", "model_sha256": "0" * 64, "temperature": 0},
            ledger_=lg,
            decompile=lambda fn: ("p", f"int {fn}(){{}}", 0.9),
            refine=lambda fn, prev: (f"int {fn}(){{}}", 0.95),
            dynamic=lambda fn: (None, None),
            budget_iters=20, **extra)
        return f, [e["payload"] for e in lg.entries()]
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        f_default, led_default = run(d1)
        f_explicit, led_explicit = run(d2, decide=policy.next_action)
        assert f_default == f_explicit and led_default == led_explicit
```

- [ ] **Step 2: Run — expect FAIL** (`run_loop() got an unexpected keyword argument 'decide'`)

- [ ] **Step 3: Modify `tools/oracle/loop.py`**

Change the signature + loop body. Replace the `run_loop` signature line and the `while True:` decision block:

```python
def run_loop(*, functions, target, decompiler_meta, ledger_,
             decompile, refine, dynamic, budget_iters=50, control_path=None,
             decide=None, investigate=None) -> dict:
    decide = decide or policy.next_action
    results: dict[str, dict] = {}
    observations: list[dict] = []
    iters = 0
    while True:
        if _control_stop(control_path):
            ledger_.append({"kind": "decision", "action": "control_stop"})
            break
        state = policy.LoopState(functions=functions, results=results,
                                 iters=iters, budget_iters=budget_iters,
                                 observations=observations)
        act = decide(state)
        ledger_.append({"kind": "decision", **act, "iter": iters})
        if act["action"] == "finalize":
            break
        if act["action"] == "investigate":
            obs = (investigate(act["query"]) if investigate
                   else {"query": act["query"], "provider": "none", "result": None})
            observations.append(obs)
            ledger_.append({"kind": "observation", "iter": iters, **obs})
            iters += 1
            continue
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
```

(The finding-assembly block after the loop is unchanged.)

- [ ] **Step 4: Run — expect PASS** (`49 passed`)

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -2`

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/loop.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): loop accepts an injected decide brain + investigate action (back-compat default)"
```

---

## Task 4: CLI — `run --agent`

**Files:** Modify `tools/oracle/oracle.py`; Test `tools/oracle/test_oracle.py`.

- [ ] **Step 1: Write failing test** (append to `test_oracle.py`)

```python
def test_parse_args_agent_flags():
    ns = oracle_cli.parse_args(["run", "--target", "/bin/x", "--funcs", "a",
                                "--agent", "--crabcc-root", "/src", "--llm-model", "m7"])
    assert ns.agent is True and ns.crabcc_root == "/src" and ns.llm_model == "m7"
```

- [ ] **Step 2: Run — expect FAIL** (`unrecognized arguments: --agent`)

- [ ] **Step 3: Implement in `tools/oracle/oracle.py`**

Add to the `run` subparser (`r`), before the slice-2 subparsers:

```python
    r.add_argument("--agent", action="store_true", help="LLM-driven brain (default: deterministic policy)")
    r.add_argument("--llm-endpoint", default="http://127.0.0.1:4000/v1/chat/completions")
    r.add_argument("--llm-model", default=os.environ.get("OQ_MODEL", "qwen2.5-coder:7b"))
    r.add_argument("--crabcc-root", default=None, help="crabcc index root (ground-truth source) for investigate")
    r.add_argument("--binary-investigate", action="store_true", help="allow binutils investigate over --target")
```

In `cmd_run`, build the brain just before the `loop.run_loop(...)` call and pass it:

```python
    decide = investigate_fn = None
    if ns.agent:
        import agent as _agent
        import investigate as _inv
        llm = _agent.LiteLLMClient(endpoint=ns.llm_endpoint, model=ns.llm_model)
        decide = _agent.make_policy(llm, model=ns.llm_model)
        investigate_fn = _inv.make_investigator(
            source_root=ns.crabcc_root,
            binary=ns.target if ns.binary_investigate else None)
```

And add `decide=decide, investigate=investigate_fn` to the `loop.run_loop(...)` call.

- [ ] **Step 4: Run — expect PASS** (`50 passed`)

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/oracle.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): CLI 'run --agent' + --llm-*/--crabcc-root wiring"
```

---

## Task 5: Docs — agentic mode

**Files:** Modify `docs/oracle/README.md`, `docs/oracle/v0.md`.

- [ ] **Step 1: `docs/oracle/README.md`** — add two module rows (after `dogfood_bridge.py`):

```markdown
| `agent.py` | Slice-3 LLM-driven loop brain — `make_policy(llm_call)` picks the next action (decompile/refine/investigate/finalize) over the bounded set; `build_prompt`/`parse_action`; `LiteLLMClient` (local litellm `:4000`, temp=0); deterministic `policy.next_action` fallback on any parse failure |
| `investigate.py` | Slice-3 read-only structural lookup — `make_investigator(source_root, binary)` answers function queries from crabcc (C ground-truth source) with a binutils fallback; never raises |
```

- [ ] **Step 2: `docs/oracle/v0.md`** — add a subsection after the schema section:

```markdown
## Agentic mode (slice 3)

`oracle run --agent` replaces the fixed `policy.next_action` round-robin with an
LLM brain (`agent.py`, local litellm `:4000`, temp=0) that adaptively chooses the
next action over `{decompile, refine, investigate, finalize}` and *which* function
to attack. The hybrid `investigate` action queries crabcc over the C ground-truth
source (`ggml.c` + C headers; crabcc indexes C, not C++) with a binutils fallback.
Every decision (+ rationale, model) and observation is logged to the ledger, so an
agentic run replays from the chain exactly like a deterministic one; any LLM
parse/validation failure falls back to the deterministic policy. Findings ground to
the aegis kernel via slice-2 unchanged.
```

- [ ] **Step 3: Commit**

```bash
git add docs/oracle/README.md docs/oracle/v0.md
git commit -m "docs(oracle): agentic mode (slice 3) — agent.py + investigate.py"
```

---

## Task 6: On-box acceptance (dev-cx53 — BOX-GATED)

**Box-gated. crabcc install is a build → CLAUDE.md 3-gate (Gate-2 user approval required).**

- [ ] **Step 1: Deploy slice-3 code** — `git archive feat/oracle-agentic-reverser tools eventd | ssh dev@100.105.72.88 'cat >/tmp/s3.tar && sudo -n -u revdev tar -xf /tmp/s3.tar -C /home/revdev/oracle-code && rm /tmp/s3.tar'`.

- [ ] **Step 2: Install crabcc on dev-cx53 (GATED build)** — present Gate-1/2/3; on approval:
  `gh auth setup-git && CARGO_NET_GIT_FETCH_WITH_CLI=true cargo install --git https://github.com/crabcc-labs/crabcc --tag <latest> crabcc-cli --force` (as a user with the toolchain). If declined → skip crabcc, run with `--binary-investigate` only.

- [ ] **Step 3: Index the C ground truth** — `crabcc --root ~revdev/oracle/llama.cpp-src index build` (ggml + C headers).

- [ ] **Step 4: Bring up the LLM gateway** — ensure litellm `:4000` is up; `export LITELLM_KEY` (see `crabcc/install/ollama-stack/OLLAMA-AUTH.md`).

- [ ] **Step 5: Run the agentic loop** —
  `python3 tools/oracle/oracle.py run --agent --target <libllama.so.0> --funcs ggml_compute_forward,llama_decode --crabcc-root ~revdev/oracle/llama.cpp-src --source-dir ~revdev/oracle/llama.cpp-src ...`
  Confirm the ledger shows agent decisions (with rationale) + observations, and a finding is produced + groundable.

- [ ] **Step 6: Record + commit** — capture the decision/observation trail + confidence into `docs/oracle/v0.md`; commit.

---

## Final verification

1. M3: `python3 tools/oracle/test_oracle.py` → `50 passed, 0 failed`.
2. Back-compat: `test_loop_default_brain_unchanged` green (deterministic path identical).
3. No edits under `tools/ralph/` or `eventd/`: `git diff --name-only origin/main | grep -E "tools/ralph/|eventd/"` empty.
4. On-box: agentic run produces a finding with a logged decision+observation trail.
