# vaked-oracle slice 4 — reverser debate-panel team (design)

**Date:** 2026-06-15
**Branch:** `feat/oracle-reverser-team` (worktree `.worktrees/oracle-slice4`), **stacked on**
`feat/oracle-agentic-reverser` (PR #276) — rebase onto `main` after #276 merges.
**Status:** approved design (topology + models chosen) → implementation plan next

## Goal

Turn the single agentic loop into a **coordinated multi-model reverser team**: for each
target function, a **debate panel** of diverse models independently produces a candidate
decompilation, and a big **judge** model picks-or-merges the best. A deterministic
coordinator runs the rounds over the shared hash-chained ledger (the blackboard); every
candidate + verdict is recorded → full audit. One sentence: *several different LLMs each
take a crack at reversing a function, and a stronger model adjudicates — diversity beats
any single model, and the whole debate is logged.*

## Decisions (from brainstorm)

- **Topology:** debate / consensus panel (per function: N panelists → 1 judge). Highest
  quality + model diversity.
- **Models:** maximum diversity — each panelist a different model. Mix local
  (qwen-coder-3b `:8091` temp=0, llm4decompile `:8090`) + OpenRouter. **OpenRouter
  defaults:** `DEFAULT_OUTSIDE_MODEL = "deepseek/deepseek-v4-flash"` — a 284B/13B-active
  MoE, 1M ctx, **$0.098 in / $0.196 out per 1M** (panelist tier); the judge uses the
  reasoning tier `REASONING_OUTSIDE_MODEL = "deepseek/deepseek-v4-pro"` (1.6T/49B-active).
  Endpoint `OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"`, key env
  `OPENROUTER_API_KEY`. Both support **reasoning efforts** (`high`/`xhigh`/`max`) — the
  judge runs `high` (escalate to `max` for hard merges); flash panelists run non-think (or
  `high`). DeepSeek recommends **`temperature=1.0`** for V4 (not 0), so OpenRouter
  panelists/judge use their recommended sampling. Note: V4 ships **no Jinja chat template**
  (custom `encoding/`) — irrelevant here since OpenRouter does OpenAI→model encoding
  server-side; it would only matter for a *local* deepseek deploy.
- **Determinism:** local panelists at `temperature=0` are individually reproducible;
  OpenRouter models (temp=1.0 + reasoning) are nondeterministic by design → the invariant
  relaxes to **fully audited** (every candidate + verdict hash-chained), not
  bit-reproducible. The coordinator's control flow stays deterministic.

## Background — reuse (slices 1-3, on `feat/oracle-agentic-reverser`)

- `agent.LiteLLMClient(endpoint, model, key)` — OpenAI-chat client (temp=0). Slice 4
  **generalizes** it to
  `agent.OpenAIChatClient(endpoint, model, key, *, temperature=0, reasoning_effort=None, extra_headers=None)`
  and keeps `LiteLLMClient` as a thin alias (back-compat, temp=0). `reasoning_effort`
  (when set) adds OpenRouter's `"reasoning": {"effort": <high|xhigh|max>}` to the body;
  `temperature` lets OpenRouter entries use DeepSeek's recommended `1.0`. OpenRouter is just
  a different endpoint+key+model (optional `HTTP-Referer`/`X-Title` headers).
- `loop.py` per-function pseudo-C producer (`decompile`), `fidelity.score`, `schema`
  finding builder, `ledger.Ledger` (ralphcore hash chain), `investigate.make_investigator`
  (crabcc/binutils), slice-2 `dogfood_bridge.ground_finding`.

## Architecture

### 1. The debate round — `tools/oracle/panel.py`

```python
@dataclass
class Panelist:
    name: str            # stable id for the ledger / ordering
    client: callable     # OpenAIChatClient (prompt -> str)

def candidate_prompt(fn, pseudo_c, context) -> str: ...   # "refine this pseudo-C; reply with C only"
def judge_prompt(fn, candidates, context) -> str: ...     # "pick the best index or merge; reply JSON"

def run_panel(fn, pseudo_c, context, panelists, *, max_workers) -> list[dict]:
    """Parallel (concurrent.futures.ThreadPoolExecutor, stdlib). Returns one entry per
    panelist: {"panelist": name, "model": ..., "refined_c": str|None, "error": str|None}.
    A panelist client error => refined_c=None, error set (NEVER raises). Results sorted by
    panelist name (order-stable for the ledger)."""

def judge_candidates(fn, candidates, context, judge_client) -> dict:
    """Returns {"mode":"pick"|"merge", "index": int|None, "refined_c": str, "rationale": str,
    "drew_from": [names]}. Parses the judge's JSON; on parse/zero-candidate failure falls
    back to the highest-fidelity candidate, else the first non-null, else the raw pseudo-C."""

def debate_function(fn, pseudo_c, context, panelists, judge_client, *, score=None,
                    ground_truth=None, max_workers=4) -> dict:
    """candidates = run_panel(...); (optional per-candidate fidelity vs ground_truth);
    verdict = judge_candidates(...); chosen = verdict['refined_c']; chosen_fidelity =
    score(chosen, ground_truth). Returns {candidates, verdict, chosen, fidelity}."""
```

Degrade rules (never crash the round): a panelist error drops that candidate; the judge
runs with ≥1 candidate; **zero** candidates ⇒ judge skipped, chosen = pseudo-C (fidelity
None). A missing/unreachable judge ⇒ pick the highest-fidelity (or first) candidate.

### 2. The coordinator — `tools/oracle/team.py`

```python
def run_team(*, functions, target, decompiler_meta, ledger_, decompile,
             panelists, judge_client, score=None, ground_truth=None,
             investigate=None, budget_calls=60, control_path=None,
             max_workers=4) -> dict:
```

Deterministic: for each function → `decompile(fn)` (slice-1 pseudo-C) → optional
`investigate` → `debate_function(...)` → append to the ledger:
`{"kind":"candidate", fn, panelist, model, refined_sha, fidelity?}` per candidate,
`{"kind":"verdict", fn, mode, drew_from, rationale}`, then build a `function_entry`
(chosen refined-C + fidelity). Budget = **total model calls** across panelists+judge
(`budget_calls`); each call decrements; exhaustion finalizes (records remaining funcs as
skipped). `control_path` `{"stop":true}` halts (ledger `{"kind":"decision","action":"control_stop"}`).
Assemble + `schema.validate_finding` → return finding (slice-2 ground unchanged).

### 3. Model roster — `tools/oracle/panel.example.json`

```json
{
  "panelists": [
    {"name": "infra-light",  "endpoint": "http://127.0.0.1:8091/v1/chat/completions", "model": "qwen2.5-coder-3b-instruct", "key_env": null, "temperature": 0},
    {"name": "static-armor", "endpoint": "http://127.0.0.1:8090/v1/chat/completions", "model": "llm4decompile",            "key_env": null, "temperature": 0},
    {"name": "feketecs",     "endpoint": "https://openrouter.ai/api/v1/chat/completions", "model": "deepseek/deepseek-v4-flash", "key_env": "OPENROUTER_API_KEY", "temperature": 1.0}
  ],
  "judge": {"name": "anstetten", "endpoint": "https://openrouter.ai/api/v1/chat/completions", "model": "deepseek/deepseek-v4-pro", "key_env": "OPENROUTER_API_KEY", "temperature": 1.0, "reasoning_effort": "high"}
}
```

Codenames (see `docs/oracle/CODENAMES.md`): coordinator = **brett-shaw**, judge =
**anstetten**, panel = **praetorian** (infra-light / static-armor / feketecs), recon =
**sherlock**, ledger = **katedralis**, parallel run = **opium-waltz**, OpenRouter egress =
**the-cordon**, host (dev-cx53) = **bolygorozsa**.

`tools/oracle/panel.py:load_roster(path) -> (panelists, judge_client)` builds an
`OpenAIChatClient` per entry; `key_env` is **a variable name, never a literal key**
(read from `os.environ`). An entry whose `key_env` is set but absent from the
environment, or whose endpoint is unreachable, is **dropped with a logged note** (no
silent omission) — the panel runs with whoever is available; all-local works with no
secret. Constants in `panel.py`: `OPENROUTER_ENDPOINT`, `DEFAULT_OUTSIDE_MODEL =
"deepseek/deepseek-v4-flash"`, `REASONING_OUTSIDE_MODEL = "deepseek/deepseek-v4-pro"`.

### 4. CLI — `tools/oracle/oracle.py`

`oracle team --target <bin> --funcs a,b --panel panel.json [--source-dir <gt>]
[--crabcc-root <gt>] [--budget-calls 60] [--max-workers 4]`. `cmd_team` loads the roster,
wires `decompile` (slice-1 producer) + `investigate` + `ground_truth`, runs `run_team`,
persists + prints the per-function chosen-model + confidence. Deterministic `run`/`ground`/
`verify-xref` untouched.

### 5. Coordination = the ledger blackboard

No separate IPC: the hash-chained `ledger.Ledger` is the shared record. Every candidate,
verdict, and the final finding are appended in order; `ledger.verify()` holds; the run is
fully reconstructible from the chain (audited, even where the judge is nondeterministic).

## Testing — `tools/oracle/test_oracle.py` (extend; pure-Python, M3-safe; fakes only)

1. `test_panel_runs_all_candidates_order_stable` — fake clients (canned per name) →
   `run_panel` returns one entry per panelist, sorted by name; each has `refined_c`.
2. `test_panel_panelist_error_degrades` — one fake client raises → that candidate
   `refined_c=None, error set`; others fine; `run_panel` never raises.
3. `test_judge_pick_parses` — fake judge returns `{"mode":"pick","index":1,...}` →
   `judge_candidates` returns candidate[1]'s C + `drew_from`.
4. `test_judge_merge_parses` — fake judge returns `{"mode":"merge","refined_c":"..."}` →
   merged C returned.
5. `test_judge_fallback_on_garbage` — judge returns non-JSON → falls back to highest-
   fidelity candidate (or first non-null).
6. `test_debate_function_end_to_end` — fake panelists + judge + fake score → `chosen`,
   `fidelity`, `candidates`, `verdict` all present.
7. `test_run_team_drives_and_records` — fake decompile + 2 panelists + judge over 2
   functions → finding `kind==oracle_finding`; ledger has `candidate`×N + `verdict`×2 +
   `finding`; `ledger.verify()` True.
8. `test_run_team_budget_calls_stops` — tiny `budget_calls` → team finalizes early
   (remaining functions recorded skipped); no unbounded calls.
9. `test_load_roster_keyenv_and_degrade` — roster with an `OPENROUTER_API_KEY` panelist;
   key absent from env ⇒ that panelist dropped (logged), local panelists kept; no literal
   key in the config object.
10. `test_openai_client_openrouter_config` — `OpenAIChatClient` for an OpenRouter entry
    builds the right endpoint/model and reads the key from env (no live call).

Target: 52 + 10 = 62 passing.

## On-box acceptance (dev-cx53)

Keyless local panel proven first: panelists = qwen-coder-3b (`:8091`, up) + llm4decompile
(`:8090`, `task llm:serve`), judge = qwen (`:8091`) — **no secret**. Then, *if* you provide
`OPENROUTER_API_KEY`, swap the judge to `deepseek/deepseek-v4-pro` + add the
`deepseek-v4-flash` panelist for the full diverse panel. `oracle team --target
libllama.so.0 --funcs llama_decode,…` → confirm per-function candidates + verdicts +
finding in the ledger; record evidence in `docs/oracle/v0.md`.

## Dogfeed dimension — vakedc + ARP into the whole (recursive)

Three ways the team consumes/produces Vaked's own stack (other dev's ARP-IR + L2
lanes stay **read-only** — consume/emit only, never modify):

1. **Team declared in Vaked (vakedc → POLA).** `vaked/examples/oracle-reverser-team.vaked`
   declares the panel as a `mesh` of agent nodes (panelists + judge), each with
   capabilities: `model`, `mem.append` (the ledger), `fs.repo_ro` (source), and a
   `networkMembrane` restricting egress to `openrouter.ai` for the OpenRouter
   panelists / `[]` (none) for the local ones. Passes `vakedc check`. `team.py` derives
   each panelist's allowed egress from the lowered `graph.json` (reusing slice-2's
   `scope_from_vaked` approach) — so the team's network-POLA is **declared in Vaked, not
   hand-coded**. This is the bounded, high-value dogfeed: vakedc configures the team.
2. **RE vakedz as a target (recursive RE).** Point the team at the `vakedz` Zig compiler
   binary (`zig-out/bin/vakedz`) — the oracle reverse-engineering Vaked's own front-end.
   No ground truth needed (the judge picks without fidelity); pure "who-knows" exploration.
3. **ARP-shaped trace emission.** The debate fan-out (per-fn panelists → judge) *is* a
   parallel-compute graph — exactly what the ARP IR models. Optionally emit the team run
   as an ARP-shaped trace artifact (nodes = candidate computations, edges = judge
   dependency) for the other dev's ARP research to consume. **Read-only emission**; uses
   their published node/edge schema, touches none of their code.

Recommendation: **#1 in slice 4** (bounded, reuses `scope_from_vaked`, on-brand POLA
dogfood). **#2 + #3 → a slice-5 "recursive dogfeed"** where "who knows? :D" gets explored
without risking slice-4's shippability.

## Out of scope / future

- Worker-swarm + hierarchical topologies (we chose the panel) — not built.
- Arbitrary-binary RE without ground truth: the panel works there too (judge picks
  without fidelity); the confidence heuristic is a later refinement.
- Cross-function team reasoning (panel is per-function) — future.

## Constraints

Never compile on the M3 (panel/coordinator + all tests pure-Python; only the on-box run
touches dev-cx53). revdev unprivileged. Snyk OFF. `tools/ralph` + `eventd` call-only.
OpenRouter keys via env-var names only — never committed. Don't touch the execution ARP
IR or L2 eBPF-LSM.
