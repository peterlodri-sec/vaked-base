# vaked-oracle slice 4a — reverser debate-panel team (core) — Implementation Plan

> REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Checkbox steps.

**Goal:** the core reverser team — a debate panel of diverse models per function, a judge
that picks/merges (adaptive reasoning effort), a deterministic coordinator over the ledger,
team memory (the-dossier), and a Serena C++ investigate provider. Defer 4b (dogfeed:
team-in-vaked / RE-vakedz / ARP emission).

**Architecture:** see `docs/superpowers/specs/2026-06-15-vaked-oracle-slice-4-design.md`
(§§1,1b,2,3,4,5,6,7). Codenames: `docs/oracle/CODENAMES.md`.

**Tech:** pure-Python stdlib (`concurrent.futures` for parallel panel, `urllib` HTTP,
`subprocess` for crabcc/serena/nm). Reuses slice-1 `decompile`/`fidelity`/`schema`,
slice-2 `dogfood_bridge.ground_finding`, slice-3 `agent`/`investigate`/`ledger`. M3-safe
(fakes); on-box keyless-local first, OpenRouter when `OPENROUTER_API_KEY` provided.

**Branch:** `feat/oracle-reverser-team` (stacked on #276 → rebase to main after it merges).

---

## Task 1: `panel.py` — clients, panel, judge, adaptive effort, debate

**Files:** Create `tools/oracle/panel.py`; Test `tools/oracle/test_oracle.py`.

`OpenAIChatClient(endpoint, model, key="", *, temperature=0, reasoning_effort=None, extra_headers=None)`
— `__call__(prompt)->str` POSTs OpenAI chat (`temperature`; if `reasoning_effort` set, add
`"reasoning": {"effort": reasoning_effort}`; merge `extra_headers`). (Generalizes
`agent.LiteLLMClient`; keep `LiteLLMClient` as a temp=0 alias.)

```python
ROSTER constants: OPENROUTER_ENDPOINT="https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OUTSIDE_MODEL="deepseek/deepseek-v4-flash"; REASONING_OUTSIDE_MODEL="deepseek/deepseek-v4-pro"
FIDELITY_THRESHOLD=0.75

@dataclass
class Panelist: name:str; client:callable

def candidate_prompt(fn, pseudo_c, context)->str   # "refine this pseudo-C to clean C; reply C only"
def run_panel(fn, pseudo_c, context, panelists, *, max_workers=4)->list[dict]
    # ThreadPoolExecutor; per panelist: {"panelist","model"?,"refined_c"|None,"error"|None}; sorted by name; never raises
def select_effort(candidates, fidelities)->str   # "none"|"high"|"max" (see spec §1b)
def judge_prompt(fn, candidates, context)->str
def judge_candidates(fn, candidates, context, judge_client, *, fidelities=None)->dict
    # parse {"mode","index"|None,"refined_c","rationale","drew_from"}; effort via judge_client; fallback: best-fidelity/first; never raises
def debate_function(fn, pseudo_c, context, panelists, judge_client, *, score=None, ground_truth=None, max_workers=4)->dict
    # {"candidates","verdict","chosen","fidelity","effort"}
def load_roster(path)->tuple[list[Panelist], callable]
    # build OpenAIChatClient per entry; key_env -> os.environ (drop+log if set-but-absent or unreachable)
```

**Tests (fakes; no live calls):**
- `test_panel_runs_all_candidates_order_stable` — fake clients per name → one entry each, sorted.
- `test_panel_panelist_error_degrades` — one client raises → that entry `refined_c=None,error`; others ok; no raise.
- `test_select_effort_none_when_agree_or_high_fidelity` / `..._max_when_all_low`.
- `test_judge_pick_parses` / `test_judge_merge_parses` / `test_judge_fallback_on_garbage`.
- `test_debate_function_end_to_end` — fake panelists+judge+score → chosen/fidelity/verdict/effort present.
- `test_load_roster_keyenv_degrade` — OPENROUTER panelist, key absent → dropped; locals kept; no literal key.
- `test_openai_client_reasoning_and_temp` — body includes `reasoning.effort` + temperature (no live call; monkeypatch the POST).

Commit: `feat(oracle): panel.py — debate panel + judge + adaptive effort + multi-model client`.

---

## Task 2: `memory.py` — the-dossier (team memory)

**Files:** Create `tools/oracle/memory.py`; Test `tools/oracle/test_oracle.py`.

```python
class TeamMemory:
    def __init__(self, path): ...                       # memory.jsonl
    def remember(self, *, run_id, fn, kind, text, tags=()): ...   # sync append {ts?,run_id,fn,kind,text,tags}
    def recall(self, query, k=5)->list[dict]: ...        # stdlib keyword/tag score over entries; top-k
    def inject(self, fn, query, k=5)->str: ...           # render recalled notes into a context block
```
(`ts` passed in by caller — no `Date.now()` determinism worry; coordinator stamps or omits.)
Optional `distill(...)` left as a documented stub (off by default; detached worker is 4a-out-of-scope, only the deterministic core ships).

**Tests:**
- `test_memory_remember_recall_roundtrip` — remember 3 → recall by keyword returns the matching note(s) top-ranked.
- `test_memory_recall_empty_safe` — recall on empty store → `[]`; `inject` → "".
- `test_memory_tags_boost` — tag match ranks above body-only match.

Commit: `feat(oracle): memory.py — the-dossier team memory (deterministic remember/recall)`.

---

## Task 3: `investigate.py` — Serena/clangd C++ provider

**Files:** Modify `tools/oracle/investigate.py`; Test `tools/oracle/test_oracle.py`.

Add `serena_query(query, *, source_root, serena="serena", runner=_run)` (invoke Serena's
symbol lookup over `source_root`; parse to the same observation shape `{query,provider:"serena",result}`).
Insert into `make_investigator` chain **between crabcc and binutils**: crabcc → serena → binutils → none.
Same graceful per-provider try/except (a serena failure falls through to binutils).

**Tests:**
- `test_investigate_serena_provider_parses` — fake runner returns serena JSON → `provider:"serena"`.
- `test_investigate_crabcc_then_serena_then_binutils_order` — crabcc miss + serena hit → serena; crabcc+serena miss + binary → binutils.

Commit: `feat(oracle): investigate.py — Serena/clangd C++ provider in the chain`.

---

## Task 4: `team.py` — the coordinator (brett-shaw)

**Files:** Create `tools/oracle/team.py`; Test `tools/oracle/test_oracle.py`.

```python
def run_team(*, functions, target, decompiler_meta, ledger_, decompile, panelists, judge_client,
             score=None, ground_truth=None, investigate=None, memory=None, run_id="run",
             budget_calls=60, control_path=None, max_workers=4)->dict:
```
Per fn: `decompile(fn)` → `ctx = (memory.inject(fn,fn) if memory else "")` + `investigate` →
`debate_function(...)` → ledger appends `{"kind":"candidate",fn,panelist,model,refined_sha,fidelity?}`
per candidate + `{"kind":"verdict",fn,mode,effort,drew_from,rationale}` → `memory.remember(...)`
(deterministic facts) → build `function_entry`. Budget = total model calls (panelists+judge);
exhaustion finalizes (remaining fns recorded skipped). `control_path {"stop":true}` halts.
Assemble + `schema.validate_finding` → finding (slice-2 ground unchanged).

**Tests:**
- `test_run_team_drives_and_records` — fake decompile + 2 panelists + judge + memory over 2 fns →
  finding `oracle_finding`; ledger has candidate×N + verdict×2 + finding; `ledger.verify()`; memory non-empty.
- `test_run_team_budget_calls_stops` — tiny `budget_calls` → finalize early; bounded.
- `test_run_team_uses_recall_context` — pre-seed memory; assert the recalled note reaches the panelist prompt (capture via fake client).

Commit: `feat(oracle): team.py — debate-panel coordinator (brett-shaw) + the-dossier wiring`.

---

## Task 5: CLI `oracle team` + roster

**Files:** Modify `tools/oracle/oracle.py`; Create `tools/oracle/panel.example.json`; Test.

`team` subcommand: `--target --funcs --panel <roster.json> [--source-dir] [--crabcc-root]
[--serena-root] [--budget-calls 60] [--max-workers 4] [--memory <memory.jsonl>] [--judge-effort auto|fixed:high]`.
`cmd_team` loads roster, wires decompile (slice-1) + investigate (crabcc/serena/binutils) +
ground_truth + `TeamMemory`, runs `run_team`, persists + prints per-fn chosen-model+confidence.
`panel.example.json` = the codename roster (spec §3).

**Test:** `test_parse_args_team_flags` — `team` parses `--panel`/`--budget-calls`/`--memory`.

Commit: `feat(oracle): CLI 'oracle team' + panel.example.json roster`.

---

## Task 6: docs + MCP fleet scaffold

- `docs/oracle/README.md` + `v0.md`: team mode (the debate panel, the-dossier, codenames).
- `.mcp.json`: add **Langfuse** (`langfuse.crabcc.app`) + **Serena** entries (env-var keys, documented prereqs); `docs/oracle/MCP-FLEET.md` notes reload + keys + Serena's canonical uvx install. (GhidraMCP not now; Frida-MCP → slice 5.)

Commit: `docs(oracle): team mode + MCP fleet scaffold (langfuse + serena)`.

---

## On-box acceptance (deferred/keyed)
Keyless-local panel first (infra-light qwen + static-armor llm4decompile + qwen judge on
`:8091`/`:8090`) — no secret. Full diverse panel (feketecs flash + anstetten pro) when
`OPENROUTER_API_KEY` provided. `oracle team --panel panel.json --target libllama.so.0 ...`.

## Verification
M3: `python3 tools/oracle/test_oracle.py` all green (52 + ~17 new ≈ 69). No `tools/ralph`/`eventd` edits.
