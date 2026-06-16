# vaked-oracle slice 3 — agentic reverser (design)

**Date:** 2026-06-15
**Branch:** `feat/oracle-agentic-reverser` (worktree `.worktrees/oracle-slice3`, off `origin/main` `9f092fe`)
**Status:** approved design → implementation plan next

## Goal

Replace the oracle loop's hardcoded decision policy with an **LLM-driven brain**
that adaptively picks the next action from loop state, plus a hybrid **investigate**
action that queries read-only structural knowledge (crabcc over the C ground-truth
source, binary tools as fallback). Every action stays a recorded, replayable
primitive — "reverser_ai-style" planning, vaked-style audit. One sentence: *the
decompiler-LLM stops following a fixed round-robin and starts deciding what to
attack, refine, or investigate next — but the action layer remains deterministic.*

## Background — the seam (slice 1/2, on `origin/main`)

`tools/oracle/loop.run_loop(...)` is already a policy-driven loop that **logs every
decision to the ledger**:

```python
state = policy.LoopState(functions, results, iters, budget_iters)
act = policy.next_action(state)                       # {"action": ..., "fn": ...}
ledger_.append({"kind": "decision", **act, "iter": iters})
```

`policy.next_action` (pure) is a fixed round-robin: decompile each fn once → refine
any below `FIDELITY_THRESHOLD=0.75` (≤ `MAX_REFINE=2`) → finalize. Slice 3 swaps
this brain. Producers (`decompile`, `refine`, `dynamic`) are injected callables;
findings are grounded to the aegis kernel via slice-2 `dogfood_bridge`.

## crabcc capability (verified 2026-06-15, crabcc 6.3.0)

Empirical test: `.c` files index with full symbol/signature/caller data; `.cpp`
files are `skipped_unsupported`. **crabcc indexes C, not C++.** Consequence for the
llama.cpp ground truth:

- **Indexed:** the ggml tensor core (`ggml.c`, `ggml-*.c`) and C headers
  (`llama.h`, `ggml.h`) → full symbols + the **C-API signatures** of functions like
  `llama_decode` (declared in the C header even though implemented in C++).
- **Not indexed:** C++ implementation bodies (`llama-*.cpp`, `src/*.cpp`).

So `investigate` is most powerful for C/ggml targets + any C-API signature; for
C++-only bodies it degrades to binary tools or the decompiled output. This steers
slice 3 toward the C surface (and dovetails with slice 5's ggml hot-path).

## Architecture

### 1. Parameterize the loop brain (backward-compatible)

`run_loop` gains two optional params; **defaults preserve slice-1/2 behavior exactly**:

```python
def run_loop(*, functions, target, decompiler_meta, ledger_,
             decompile, refine, dynamic, budget_iters=50, control_path=None,
             decide=None, investigate=None) -> dict:
    decide = decide or policy.next_action          # deterministic by default
    ...
```

When `decide is policy.next_action` (default) and `investigate is None`, the loop is
identical to today (all 41 existing tests stay green). When an agent brain is
injected, the loop additionally handles the `investigate` action.

### 2. Action space

`{decompile fn, refine fn, investigate <query>, finalize}`. The agent additionally
chooses **which** function (order is no longer fixed) and **whether** to refine or
finalize based on fidelity feedback. (A separate dynamic-`probe` action is deferred
to slice 5 — `decompile` already runs `dynamic(fn)` as today.)

`decompile`/`refine` targets must be in the provided `functions` list (bounded);
`investigate` queries are free-form read-only. `investigate` counts against
`budget_iters` like any tick (no unbounded investigation).

### 3. Agent brain — `tools/oracle/agent.py`

```python
def make_policy(llm_call, *, threshold=0.75, max_refine=2):
    """Return a decide(state) -> action using an injected llm_call(prompt)->str.
    Falls back to policy.next_action on any parse/validation failure."""
    def decide(state):
        prompt = build_prompt(state, threshold=threshold, max_refine=max_refine)
        try:
            raw = llm_call(prompt)
            return parse_action(raw, state)        # validated; raises on bad shape
        except Exception:                          # noqa: BLE001 — any failure ⇒ deterministic
            return policy.next_action(state)
    return decide
```

- `build_prompt(state, ...)` — compact rendering of: target, the function list, each
  function's current `{fidelity, refine_passes, has_dynamic}`, recent observations
  (last N), the action menu + the threshold/max_refine rules. Asks for **one JSON
  action** and a short `rationale`.
- `parse_action(raw, state)` — extract the first JSON object; validate `action ∈
  {decompile, refine, investigate, finalize}`; `fn ∈ state.functions` for
  decompile/refine; `query` present for investigate. Returns the normalized action
  dict (incl. `rationale`). Raises `ValueError` on any violation → fallback.
- `LiteLLMClient(endpoint="http://127.0.0.1:4000/v1/chat/completions", model, key)` —
  thin OpenAI-chat POST, `temperature=0` (replayable), returns the message content.
  Mirrors revdev's `oq` helper. **Injectable** — tests pass a fake `llm_call`.

### 4. Investigate — `tools/oracle/investigate.py`

```python
def make_investigator(*, source_root=None, binary=None, crabcc="crabcc") -> callable:
    """Return investigate(query) -> observation. crabcc-preferred (C subset of the
    ground-truth source), binary-tool fallback, graceful 'none' if neither works."""
```

- Query shape: `{"kind": "sym"|"callers"|"refs"|"outline"|"fuzzy", "name": "..."}`.
- **crabcc provider:** shell `crabcc --root <source_root> lookup <kind> <name>` (JSON
  out), trimmed to a compact observation. Requires a built index (`crabcc index
  build` at acceptance time).
- **binutils fallback:** `nm`/`objdump`/`strings` over `binary` for `sym`/`fuzzy`
  (symbol presence/addr); `callers`/`refs`/`outline` → `not_available` for binary-only.
- **Observation:** `{"query": <query>, "provider": "crabcc"|"binutils"|"none",
  "result": <compact>}`. Never raises — degrades to `provider:"none"`.
- Injectable — tests pass a fake investigator.

### 5. Loop handling of `investigate` (the only new loop branch)

```python
elif act["action"] == "investigate":
    obs = investigate(act["query"]) if investigate else {"provider": "none", "query": act["query"]}
    observations.append(obs)
    ledger_.append({"kind": "observation", "iter": iters, **obs})
```

`observations` is threaded into `LoopState` so the agent sees prior results. Decision
logging already records the chosen action; for agentic ticks the appended decision
also carries `rationale` + `model`.

### 6. Determinism / replay / audit

- `temperature=0` for all agent decisions.
- The ledger records, per tick: `{kind:decision, action, fn?/query?, rationale?,
  model?, iter}` and `{kind:observation, ...}`. The **recorded run replays from the
  ledger** (the actions are the record; no LLM re-call needed to verify the chain).
- ralphcore budget (`budget_iters`) + `control_path` `{"stop":true}` preserved.
- The assembled finding is unchanged in shape (slice-2 ground still applies).

### 7. Safety

Actions are a bounded menu, not arbitrary shell — the agent cannot execute code, only
select among recorded primitives + read-only investigate. revdev stays unprivileged
(eBPF via the watcher socket only); crabcc + binary tools are read-only; target is
FOSS. No untrusted-binary sandbox needed for slice 3 (known target).

## Data shapes

```
action  = {"action":"decompile","fn":str,"rationale":str?}
        | {"action":"refine","fn":str,"rationale":str?}
        | {"action":"investigate","query":{"kind":str,"name":str},"rationale":str?}
        | {"action":"finalize","rationale":str?}
observation = {"query":{...}, "provider":"crabcc"|"binutils"|"none", "result":<json>}
LoopState  += observations: list[dict]
```

## Testing — `tools/oracle/test_oracle.py` (extend; pure-Python, M3-safe)

Injected fakes — no live LLM/crabcc. All via `python3 tools/oracle/test_oracle.py`.

1. `test_agent_decide_parses_llm_action` — fake `llm_call` returns
   `'{"action":"decompile","fn":"a","rationale":"start"}'`; `make_policy(...)` decide
   returns that normalized action.
2. `test_agent_decide_falls_back_on_garbage` — fake `llm_call` returns `"not json"`;
   decide returns `policy.next_action(state)` (deterministic fallback).
3. `test_agent_decide_rejects_out_of_menu` — fake returns
   `'{"action":"rm","fn":"a"}'` (or `fn` not in `functions`) → fallback.
4. `test_loop_agentic_drives_to_finalize_with_fake_llm` — a scripted fake `llm_call`
   (decompile a → investigate → finalize) + fake producers + fake investigator drives
   `run_loop(decide=make_policy(fake), investigate=fake_inv)` to a valid finding; the
   ledger contains a `decision` with `rationale` and an `observation` entry.
5. `test_loop_records_observation` — agentic run with one investigate action →
   ledger has `{"kind":"observation","provider":"crabcc",...}`.
6. `test_investigate_crabcc_adapter_parses` — fake `subprocess` runner (injected)
   returns crabcc JSON for `lookup sym` → observation `provider:"crabcc"` with the
   trimmed result; runner error → `provider:"none"` (never raises).
7. `test_investigate_binutils_fallback` — no `source_root`, `binary` set, fake runner
   returns `nm` output → observation `provider:"binutils"`.
8. `test_loop_default_brain_unchanged` — `run_loop` with no `decide`/`investigate`
   produces the identical finding/ledger as the slice-1 deterministic path
   (back-compat guard).

Target: 41 existing + 8 new = 49 passing.

## CLI — `tools/oracle/oracle.py`

Add agentic flags to the `run` subcommand (default off ⇒ deterministic, unchanged):

```
--agent                         # enable the LLM-driven brain
--llm-endpoint  http://127.0.0.1:4000/v1/chat/completions
--llm-model     qwen2.5-coder:7b     # env: OQ_MODEL; key: LITELLM_KEY
--crabcc-root   <source_root>        # crabcc index root for investigate (the ground-truth source)
--binary-investigate                 # allow binutils fallback over --target
```

`cmd_run` wires `decide = agent.make_policy(LiteLLMClient(...))` and
`investigate = investigate.make_investigator(source_root=..., binary=...)` when
`--agent` is set; otherwise the deterministic path runs as today.

## On-box acceptance (dev-cx53 — BOX-GATED)

1. **Install crabcc on dev-cx53** (private repo `crabcc-labs/crabcc`, `cargo install`)
   — this is a **box build**: run the CLAUDE.md 3-gate protocol (Gate 1 target check,
   **Gate 2 user approval**, Gate 3 pre-flight). Falls back to skipping crabcc
   (binutils-only investigate) if the user declines the build.
2. `crabcc --root ~revdev/oracle/llama.cpp-src index build` (indexes the C subset:
   ggml + C headers).
3. Ensure the litellm gateway is up (`:4000`; `export LITELLM_KEY`) — the local LLM
   that `oq` already uses.
4. `oracle run --agent --target <libllama.so.0> --funcs ggml_compute_forward,llama_decode
   --crabcc-root ~revdev/oracle/llama.cpp-src ...` → confirm the agent adaptively
   decompiles/refines/investigates and grounds a finding; record the decision/observation
   trail + confidence in `docs/oracle/v0.md`.

## Out of scope (→ slice 4/5, `.DEV.TODO`)

- Off-the-shelf free-form agent CLIs (claude/pi/nullclaw) — the LLM-driven-policy +
  investigate hybrid is the chosen, auditable middle ground.
- Separate dynamic `probe` action + ggml deepening → slice 5.
- Arbitrary-binary RE without ground truth (no crabcc/source) → slice 4 (investigate
  already degrades to binary tools, which is the slice-4 path).

## Constraints

Never compile on the M3 (the brain + investigate adapter + all tests are pure-Python;
only the crabcc install + on-box run touch dev-cx53). revdev unprivileged. Snyk OFF.
`tools/ralph` + `eventd` call-only. Don't touch the execution ARP IR or L2 eBPF-LSM.
