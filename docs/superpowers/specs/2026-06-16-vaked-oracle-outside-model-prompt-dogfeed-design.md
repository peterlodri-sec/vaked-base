# vaked-oracle — outside-model prompt dogfeed (design)

**Date:** 2026-06-16
**Status:** approved (brainstorm) — ready for plan
**Base:** `origin/main` @ `df9b59b`

## One-liner

Surface every prompt the oracle sends to **non-hosted** (OpenRouter) models to **one rolling
GitHub issue** — a transparency/cost audit of third-party spend. Fire-and-forget, never leaks
the key or the full prompt/response.

## Why

The oracle team (slice 4a/4b) sends prompts to OpenRouter models (`feketecs` deepseek-flash,
`anstetten` deepseek-pro). Today those calls are invisible — no record of what we ship to a
third party or what it costs. A single rolling issue, appended one comment per run, makes the
outside-model surface auditable with zero infra. Complements (does not replace) the heavier
Langfuse SDK push.

## Decisions (locked in brainstorm)

- **One rolling issue**, find-or-create, **one comment per run**, max 1 issue.
- **Outside-model only** — gated on `self.key` (key_env-gated clients); local keyless clients
  (qwen/llm4d) are never logged.
- **Per-call record:** `model`, `prompt_sha`, `first_line` (≤120 chars), `completion_tokens`,
  `cost`, `reasoning` (bool). **No full prompt, no response, no key.**
- **Transport:** the `gh` runner is **injected** (module is transport-agnostic + testable);
  default = direct `gh` (authed on M3). Posting is a **separate, deliberate step** (CLI/Task),
  never in a run's hot path. (Staging-file+CI is a later deployment option, not v1.)
- Pure Python stdlib; tests in the existing module-level `test_*` style.

## Architecture

```
panel.OpenAIChatClient.__call__  --(opt-in sink: ORACLE_DOGFEED_LOG set AND self.key)-->  JSONL
   (one record per outside-model call; best-effort; no-op otherwise)                         |
                                                                                             v
oracle dogfeed --log <jsonl> --repo <r>  -->  dogfeed_prompts.load_records / build_comment / post
                                                  |                                  |
                                          find_or_create_issue(gh)          gh issue comment
                                          (max 1, by exact title)           (the run's summary)
```

## Components / files

### `tools/oracle/panel.py` (MODIFY — the sink)

Refactor `__call__` to capture the full response, then sink before returning:
```python
    def __call__(self, prompt, *, reasoning_effort=None):
        eff = reasoning_effort if reasoning_effort is not None else self.reasoning_effort
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        headers.update(self.extra_headers)
        req = urllib.request.Request(self.endpoint, data=json.dumps(self._build_body(prompt, eff)).encode(),
                                     method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
            d = json.load(r)
        self._dogfeed(prompt, d, eff)
        return d["choices"][0]["message"]["content"]

    def _dogfeed(self, prompt, resp, eff):
        """Opt-in, best-effort: append one JSONL record for an OUTSIDE-model call.
        No-op unless self.key (key_env-gated) AND ORACLE_DOGFEED_LOG is set. Never
        raises (must not break the model call); never writes the key or the response."""
        if not self.key:
            return
        path = os.environ.get("ORACLE_DOGFEED_LOG")
        if not path:
            return
        try:
            usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
            stripped = (prompt or "").strip()
            rec = {"model": self.model,
                   "prompt_sha": hashlib.sha256((prompt or "").encode()).hexdigest(),
                   "first_line": (stripped.splitlines()[0][:120] if stripped else ""),
                   "completion_tokens": usage.get("completion_tokens"),
                   "cost": usage.get("cost"),
                   "reasoning": bool(eff)}
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:  # noqa: BLE001 — sink must never break the call
            pass
```
Add `import hashlib` to panel.py (`os`, `json` already imported). The sink is **off by
default** (no env → no-op); keyless local clients return early. This is the only change to the
hot path and it cannot raise.

### `tools/oracle/dogfeed_prompts.py` (NEW — pure stdlib)

- `ISSUE_TITLE = "oracle: outside-model prompt dogfeed"`
- `load_records(path)` → list of dicts; **skips corrupt/partial lines** (try/except per line).
- `summarize(records)` → `{by_model: {model: {calls, tokens, cost}}, total_cost, n}`
  (tokens/cost sum with `or 0` guards).
- `build_comment(records, *, run_id, cap=50)` → markdown: a header line (n calls · total cost),
  a `model | calls | completion_tokens | cost` table, and a capped `<details>` per-call list
  (`sha12 · model · Ntok · $cost · first_line`), with a `… +N more (capped)` line when over
  `cap`. **Contains no full prompt, no response, no key.**
- `find_or_create_issue(title, *, repo, gh)` → int issue number. `gh(["issue","list","--repo",
  repo,"--search",title,"--state","all","--json","number,title","--limit","20"])`; return the
  number of the item whose `title` matches **exactly**; else `gh(["issue","create",...])` and
  parse the trailing number from the printed URL. (Exact-title match avoids creating duplicates.)
- `post(records, *, repo, run_id, gh, title=ISSUE_TITLE)` → int; find-or-create then
  `gh(["issue","comment",str(num),"--repo",repo,"--body",build_comment(...)])`.
- `_gh(args)` default runner: `subprocess.run(["gh", *args], capture_output=True, text=True,
  check=True).stdout`. **Injected** everywhere above so tests pass a fake.

### `tools/oracle/oracle.py` (MODIFY — CLI)

New `dogfeed` subparser: `--log <jsonl>` (required), `--repo <owner/name>` (required),
`--run-id` (default `"run"`), `--dry-run`. `cmd_dogfeed`: `records = load_records(ns.log)`;
if `--dry-run` → `print(build_comment(records, run_id=ns.run_id))`; else
`num = post(records, repo=ns.repo, run_id=ns.run_id, gh=dogfeed_prompts._gh)` and print the
issue number. Dispatch in `main`.

### `tools/oracle/Taskfile.yml` (MODIFY)

`dogfeed` target: `oracle.py dogfeed --log "${ORACLE_DOGFEED_LOG:-$HOME/oracle/dogfeed.jsonl}"
--repo "${ORACLE_REPO:-peterlodri-sec/vaked-base}" --run-id "${RUN_ID:-run}"`. Documents that
a team run with `ORACLE_DOGFEED_LOG` set produces the JSONL the dogfeed posts.

### Tests — `tools/oracle/test_oracle.py` (module-level `test_*`, plain `assert`)

- `load_records` skips a corrupt/partial line.
- `summarize` math (calls/tokens/cost per model + total).
- `build_comment`: table rows present; cap honored (`>cap` → "more (capped)"); **leak-free**
  (assert the rendered comment contains no `"Bearer"`, no fake key, no response text).
- `find_or_create_issue`: fake gh returns an item with the exact title → returns its number,
  **no create call**; fake gh returns `[]` → a create call is issued and the URL-tail number
  parsed. (The fake gh records the argv it was called with.)
- `post`: fake gh → an `issue comment <num>` call is made with the built body.
- **sink:** monkeypatch `urllib.request.urlopen` to return a fake response (with `usage`); set
  `ORACLE_DOGFEED_LOG` to a tmp file; an **outside** client (key set) appends exactly one
  record with the expected fields and **no key**; a **keyless** client appends nothing; with
  the env unset, nothing is written.

## Error handling

- Sink: best-effort `try/except`, never raises, no-op when off / keyless.
- `load_records`: per-line try/except → skip corrupt lines (partial writes from a crash).
- `find_or_create_issue`: exact-title match prevents duplicate issues; a `gh` failure
  surfaces as a non-zero CLI exit (posting is a deliberate step, not the run's hot path).
- No secret ever enters a record, a comment, or a log line.

## Out of scope (follow-ups)
- Staging-file + CI auto-post (box-run fire-and-forget) — a later deployment layer.
- Auto-post at the end of a team run.
- Langfuse SDK instrumentation (separate, heavier observability).

## Constraints
Pure stdlib · never print/echo the OpenRouter key · reuse existing patterns (module-level
`test_*`, injected runners like slice-4a's panel) · Snyk OFF · M3-safe (no compile).
