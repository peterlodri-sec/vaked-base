# Outside-model prompt dogfeed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Surface every prompt the oracle sends to non-hosted (OpenRouter) models to one rolling GitHub issue — a transparency/cost audit — fire-and-forget, no key/response leak.

**Architecture:** An opt-in best-effort sink in `panel.OpenAIChatClient.__call__` appends a per-call JSONL record (outside-model only). A pure stdlib `dogfeed_prompts.py` summarizes the JSONL and (via an **injected `gh` runner**) find-or-creates one issue and appends a comment. CLI `oracle dogfeed` drives it; posting is a deliberate step, never in a run's hot path.

**Tech Stack:** Python 3 stdlib only (json, os, hashlib, subprocess, urllib). Tests = module-level `test_*` functions with plain `assert` (the `tools/oracle/test_oracle.py` convention — NOT unittest; a custom `globals()` runner collects `test_*`).

**Spec:** `docs/superpowers/specs/2026-06-16-vaked-oracle-outside-model-prompt-dogfeed-design.md`

**Constraints:** pure stdlib, M3-safe (no compile); never write/print the OpenRouter key; reuse the injected-runner + module-level-test patterns; `git add` only named files (no `-A`).

---

### Task 1: opt-in sink in `panel.OpenAIChatClient`

**Files:** Modify `tools/oracle/panel.py`; Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test** — append to `tools/oracle/test_oracle.py`:

```python
# ---- outside-model prompt dogfeed ----
def test_dogfeed_sink_outside_model_only_and_leakfree():
    import os, json, tempfile
    import urllib.request as U
    import panel
    class _Resp:
        def __init__(self, d): self._d = d
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self._d).encode()
    fake = {"choices": [{"message": {"content": "PONG"}}],
            "usage": {"completion_tokens": 7, "cost": 0.0009}}
    orig = U.urlopen
    U.urlopen = lambda req, timeout=None: _Resp(fake)
    log = tempfile.mktemp(suffix=".jsonl")
    os.environ["ORACLE_DOGFEED_LOG"] = log
    try:
        out = panel.OpenAIChatClient("https://openrouter.ai/x", "deepseek/deepseek-v4-pro",
                                     "sekret-key", reasoning_effort="high")
        assert out("Reverse-engineer fn foo\npseudo-c body") == "PONG"
        recs = [json.loads(l) for l in open(log) if l.strip()]
        assert len(recs) == 1
        r = recs[0]
        assert r["model"] == "deepseek/deepseek-v4-pro"
        assert r["completion_tokens"] == 7 and r["cost"] == 0.0009 and r["reasoning"] is True
        assert r["first_line"] == "Reverse-engineer fn foo"
        assert len(r["prompt_sha"]) == 64
        assert "sekret-key" not in json.dumps(r)          # key never recorded
        # keyless local client -> NOT logged
        os.remove(log)
        loc = panel.OpenAIChatClient("http://127.0.0.1:8091/x", "qwen", "")
        assert loc("hi there") == "PONG"
        assert (not os.path.exists(log)) or sum(1 for _ in open(log)) == 0
    finally:
        U.urlopen = orig
        os.environ.pop("ORACLE_DOGFEED_LOG", None)
        if os.path.exists(log): os.remove(log)


def test_dogfeed_sink_noop_when_env_unset():
    import os, json
    import urllib.request as U
    import panel
    class _Resp:
        def __init__(self, d): self._d = d
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(self._d).encode()
    orig = U.urlopen
    U.urlopen = lambda req, timeout=None: _Resp({"choices": [{"message": {"content": "X"}}], "usage": {}})
    os.environ.pop("ORACLE_DOGFEED_LOG", None)               # ensure unset
    try:
        c = panel.OpenAIChatClient("https://openrouter.ai/x", "m", "k")
        assert c("p") == "X"                                  # no env -> sink no-op, call still works
    finally:
        U.urlopen = orig
```

- [ ] **Step 2: Run to verify it fails** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -6` → the new sink test FAILS (no record written; `_dogfeed` absent → currently `__call__` returns content without sinking, so `recs` is empty / file missing).

- [ ] **Step 3: Implement** — in `tools/oracle/panel.py`: add `import hashlib` near the other stdlib imports; replace the `__call__` body's `with ...: return json.load(r)[...]` to capture the response + sink, and add the `_dogfeed` method:

```python
    def __call__(self, prompt, *, reasoning_effort=None):
        eff = reasoning_effort if reasoning_effort is not None else self.reasoning_effort
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        headers.update(self.extra_headers)
        req = urllib.request.Request(self.endpoint, data=json.dumps(self._build_body(prompt, eff)).encode(),
                                     method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (operator-configured endpoints)
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
        except Exception:  # noqa: BLE001 — the sink must never break the model call
            pass
```

- [ ] **Step 4: Run to verify it passes** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -3` → all pass (2 new + 82 prior = 84).

- [ ] **Step 5: Commit**
```bash
git add tools/oracle/panel.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): opt-in dogfeed sink in OpenAIChatClient (outside-model only, leak-free)"
```

---

### Task 2: `dogfeed_prompts.py` — summarize + comment + find-or-create + post

**Files:** Create `tools/oracle/dogfeed_prompts.py`; Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test** — append to `tools/oracle/test_oracle.py`:

```python
def test_dogfeed_load_records_skips_corrupt():
    import dogfeed_prompts as dp, tempfile, os
    p = tempfile.mktemp(suffix=".jsonl")
    open(p, "w").write('{"model":"a"}\nNOT JSON\n\n{"model":"b"}\n')
    recs = dp.load_records(p)
    assert [r["model"] for r in recs] == ["a", "b"]
    os.remove(p)


def test_dogfeed_summarize_math():
    import dogfeed_prompts as dp
    recs = [{"model": "a", "completion_tokens": 10, "cost": 0.001},
            {"model": "a", "completion_tokens": 5, "cost": 0.002},
            {"model": "b", "completion_tokens": 3, "cost": None}]
    s = dp.summarize(recs)
    assert s["n"] == 3
    assert s["by_model"]["a"] == {"calls": 2, "tokens": 15, "cost": 0.003}
    assert s["by_model"]["b"]["tokens"] == 3
    assert abs(s["total_cost"] - 0.003) < 1e-9


def test_dogfeed_build_comment_cap_and_leakfree():
    import dogfeed_prompts as dp
    recs = [{"model": "deepseek/deepseek-v4-pro", "prompt_sha": "a" * 64,
             "first_line": "Reverse-engineer fn x", "completion_tokens": 100,
             "cost": 0.002, "reasoning": True} for _ in range(3)]
    c = dp.build_comment(recs, run_id="r1", cap=2)
    assert "deepseek/deepseek-v4-pro" in c
    assert "| 3 |" in c                       # 3 calls in the table
    assert "more (capped)" in c               # 3 > cap 2
    assert "Bearer" not in c and "sekret" not in c


def test_dogfeed_find_or_create_returns_existing():
    import dogfeed_prompts as dp, json
    calls = []
    def fake_gh(args):
        calls.append(args)
        if args[1] == "list":
            return json.dumps([{"number": 42, "title": dp.ISSUE_TITLE}])
        raise AssertionError("must not create when issue exists")
    assert dp.find_or_create_issue(dp.ISSUE_TITLE, repo="o/r", gh=fake_gh) == 42
    assert all(a[1] != "create" for a in calls)


def test_dogfeed_find_or_create_creates_when_absent():
    import dogfeed_prompts as dp
    def fake_gh(args):
        if args[1] == "list": return "[]"
        if args[1] == "create": return "https://github.com/o/r/issues/77\n"
        raise AssertionError
    assert dp.find_or_create_issue(dp.ISSUE_TITLE, repo="o/r", gh=fake_gh) == 77


def test_dogfeed_post_appends_comment():
    import dogfeed_prompts as dp, json
    calls = []
    def fake_gh(args):
        calls.append(args)
        if args[1] == "list": return json.dumps([{"number": 5, "title": dp.ISSUE_TITLE}])
        return ""
    n = dp.post([{"model": "m", "completion_tokens": 1, "cost": 0.0,
                  "prompt_sha": "x" * 64, "first_line": "hi"}],
                repo="o/r", run_id="r", gh=fake_gh)
    assert n == 5
    assert any(a[0] == "issue" and a[1] == "comment" and a[2] == "5" for a in calls)
```

- [ ] **Step 2: Run to verify it fails** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -6` → FAIL: `ModuleNotFoundError: No module named 'dogfeed_prompts'`.

- [ ] **Step 3: Implement** — create `tools/oracle/dogfeed_prompts.py`:

```python
"""dogfeed_prompts — surface outside-model prompts to one rolling GitHub issue.

Reads the JSONL the panel sink writes (ORACLE_DOGFEED_LOG), summarizes the
non-hosted (OpenRouter) model calls, and appends ONE comment to a single rolling
issue (find-or-create by exact title, max 1). Transparency / cost audit — no full
prompts, no responses, no key. The `gh` runner is INJECTED (default: subprocess
`gh`) so the module is transport-agnostic and testable with a fake. Pure stdlib.
"""
from __future__ import annotations

import json
import subprocess

ISSUE_TITLE = "oracle: outside-model prompt dogfeed"


def load_records(path):
    """Records from a JSONL file; skips corrupt/partial lines (crash-safe)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def summarize(records):
    by = {}
    for r in records:
        m = r.get("model", "?")
        s = by.setdefault(m, {"calls": 0, "tokens": 0, "cost": 0.0})
        s["calls"] += 1
        s["tokens"] += r.get("completion_tokens") or 0
        s["cost"] = round(s["cost"] + (r.get("cost") or 0.0), 6)
    total = round(sum(s["cost"] for s in by.values()), 6)
    return {"by_model": by, "total_cost": total, "n": len(records)}


def build_comment(records, *, run_id, cap=50):
    """Markdown comment: summary table + a capped per-call list. No prompt/response/key."""
    s = summarize(records)
    lines = ["### oracle outside-model dogfeed — run `%s`" % run_id, "",
             "%d non-hosted call(s) · total cost $%.6f" % (s["n"], s["total_cost"]), "",
             "| model | calls | completion_tokens | cost |", "|---|---|---|---|"]
    for m, v in sorted(s["by_model"].items()):
        lines.append("| `%s` | %d | %d | $%.6f |" % (m, v["calls"], v["tokens"], round(v["cost"], 6)))
    lines += ["", "<details><summary>per-call (prompt sha · first line)</summary>", ""]
    for r in records[:cap]:
        lines.append("- `%s` · %s · %stok · $%.6f · %s" % (
            (r.get("prompt_sha") or "")[:12], r.get("model"),
            r.get("completion_tokens"), (r.get("cost") or 0.0), r.get("first_line", "")))
    if len(records) > cap:
        lines.append("- … +%d more (capped)" % (len(records) - cap))
    lines.append("</details>")
    return "\n".join(lines)


def find_or_create_issue(title, *, repo, gh):
    """Issue number for `title` in `repo`; create it (max 1) if no exact-title match."""
    raw = gh(["issue", "list", "--repo", repo, "--search", title,
              "--state", "all", "--json", "number,title", "--limit", "20"])
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        items = []
    for it in items:
        if it.get("title") == title:
            return int(it["number"])
    url = gh(["issue", "create", "--repo", repo, "--title", title,
              "--body", "Rolling log of prompts the oracle sends to non-hosted models. "
                        "One comment per run (tools/oracle/dogfeed_prompts.py)."])
    return int(url.strip().rstrip("/").split("/")[-1])


def post(records, *, repo, run_id, gh, title=ISSUE_TITLE):
    """Find-or-create the rolling issue and append this run's summary comment."""
    num = find_or_create_issue(title, repo=repo, gh=gh)
    gh(["issue", "comment", str(num), "--repo", repo,
        "--body", build_comment(records, run_id=run_id)])
    return num


def _gh(args):
    """Default runner: the `gh` CLI (authed wherever this runs, e.g. M3)."""
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout
```

- [ ] **Step 4: Run to verify it passes** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -3` → all pass (6 new + 84 prior = 90).

- [ ] **Step 5: Commit**
```bash
git add tools/oracle/dogfeed_prompts.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): dogfeed_prompts — summarize outside-model calls + find-or-create rolling issue (injected gh)"
```

---

### Task 3: CLI `oracle dogfeed`

**Files:** Modify `tools/oracle/oracle.py`; Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test** — append to `tools/oracle/test_oracle.py`:

```python
def test_dogfeed_cli_args_and_dryrun():
    import oracle, tempfile, json, os
    p = tempfile.mktemp(suffix=".jsonl")
    open(p, "w").write(json.dumps({"model": "deepseek/deepseek-v4-pro", "completion_tokens": 9,
                                   "cost": 0.001, "prompt_sha": "z" * 64, "first_line": "hi"}) + "\n")
    ns = oracle.parse_args(["dogfeed", "--log", p, "--repo", "o/r", "--dry-run"])
    assert ns.log == p and ns.repo == "o/r" and ns.dry_run is True
    assert oracle.cmd_dogfeed(ns) == 0          # dry-run prints the comment, posts nothing
    os.remove(p)
```

- [ ] **Step 2: Run to verify it fails** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -6` → FAIL (no `dogfeed` subcommand / `cmd_dogfeed`).

- [ ] **Step 3: Implement** — in `tools/oracle/oracle.py`:
  (a) add a `dogfeed` subparser (alongside the others in `parse_args`):
```python
    d = sub.add_parser("dogfeed", help="post outside-model prompt records to the rolling GitHub issue")
    d.add_argument("--log", required=True, help="JSONL written by the panel sink (ORACLE_DOGFEED_LOG)")
    d.add_argument("--repo", required=True, help="owner/name for the rolling issue")
    d.add_argument("--run-id", dest="run_id", default="run")
    d.add_argument("--dry-run", dest="dry_run", action="store_true", help="print the comment; post nothing")
```
  (b) add `cmd_dogfeed`:
```python
def cmd_dogfeed(ns: argparse.Namespace) -> int:
    import dogfeed_prompts as dfp
    records = dfp.load_records(ns.log)
    if ns.dry_run:
        print(dfp.build_comment(records, run_id=ns.run_id))
        return 0
    num = dfp.post(records, repo=ns.repo, run_id=ns.run_id, gh=dfp._gh)
    print("dogfeed: posted %d record(s) to %s issue #%d" % (len(records), ns.repo, num))
    return 0
```
  (c) dispatch in `main`: add `if ns.cmd == "dogfeed": return cmd_dogfeed(ns)`.

- [ ] **Step 4: Run to verify it passes** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -3` → all pass (1 new + 90 prior = 91).

- [ ] **Step 5: Commit**
```bash
git add tools/oracle/oracle.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): oracle dogfeed CLI — post/dry-run the outside-model rolling issue"
```

---

### Task 4: Taskfile target + docs

**Files:** Modify `tools/oracle/Taskfile.yml`, `docs/oracle/MCP-FLEET.md`, `.DEV.TODO`

- [ ] **Step 1: Add the Taskfile target** — append to `tools/oracle/Taskfile.yml` (2-space indent under `tasks:`):
```yaml
  dogfeed:
    desc: "post outside-model prompt records (ORACLE_DOGFEED_LOG) to the rolling GitHub issue (run where gh is authed, e.g. M3). DRY=1 to preview"
    cmds:
      - |
        python3 tools/oracle/oracle.py dogfeed \
          --log "${ORACLE_DOGFEED_LOG:-$HOME/oracle/dogfeed.jsonl}" \
          --repo "${ORACLE_REPO:-peterlodri-sec/vaked-base}" \
          --run-id "${RUN_ID:-run}" \
          {{if eq .DRY "1"}}--dry-run{{end}}
    vars:
      DRY: '{{.DRY | default ""}}'
```
Verify YAML parses: `python3 -c "import yaml; yaml.safe_load(open('tools/oracle/Taskfile.yml')); print('YAML OK')"`.

- [ ] **Step 2: Document** — add a section to `docs/oracle/MCP-FLEET.md` under the Langfuse/observability area (or end):
```markdown
## Outside-model prompt dogfeed (zero-infra transparency)

The oracle's non-hosted (OpenRouter) calls are surfaced to ONE rolling GitHub issue
("oracle: outside-model prompt dogfeed") — a human-visible cost/prompt audit that complements
the Langfuse SDK push. A team run with `ORACLE_DOGFEED_LOG=<path>` set makes the panel sink
(`panel.OpenAIChatClient._dogfeed`) append one JSONL record per outside-model call (model,
prompt sha + first line, completion tokens, cost — **no full prompt/response, no key**; keyless
local models are never logged). Then, from where `gh` is authed (M3): `task -d tools/oracle
dogfeed` (or `DRY=1 ... dogfeed` to preview) find-or-creates the issue and appends the run's
summary. Posting is a deliberate step, never in a run's hot path.
```
And append to `.DEV.TODO`:
```markdown
### Outside-model prompt dogfeed — DONE (branch feat/oracle-dogfeed-prompts)
Opt-in sink in OpenAIChatClient (ORACLE_DOGFEED_LOG, outside-model only, leak-free) +
dogfeed_prompts.py (summarize + find-or-create rolling issue, injected gh) + `oracle dogfeed`
CLI + `task dogfeed`. Direct-gh-from-M3 transport. Follow-ups: staging-file+CI auto-post; Langfuse SDK.
```

- [ ] **Step 3: Verify the suite is still green** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -1` → "91 passed, 0 failed" (no Python changed in this task).

- [ ] **Step 4: Commit**
```bash
git add tools/oracle/Taskfile.yml docs/oracle/MCP-FLEET.md .DEV.TODO
git commit -m "chore(oracle): dogfeed Taskfile target + docs (MCP-FLEET, .DEV.TODO)"
```

---

## Final verification
- [ ] Full suite green: `python3 tools/oracle/test_oracle.py` → 91 passed.
- [ ] Dispatch a final whole-branch code review (subagent-driven-development final reviewer), focus: the sink never breaks/leaks; find-or-create is idempotent; the comment is leak-free.

## Out of scope (follow-ups)
Staging-file + CI auto-post · auto-post at end of a team run · Langfuse SDK instrumentation.
