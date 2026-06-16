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
