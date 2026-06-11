#!/usr/bin/env python3
"""ralph — decision/strategy loop (decide / run / watch). Stdlib only."""
from __future__ import annotations
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ralphcore as C  # noqa: E402

REPO_HOME = os.path.abspath(os.path.join(HERE, "..", ".."))   # vaked-base
DECISIONS_DIR = os.path.join(REPO_HOME, "docs", "decisions")
STATE_DIR = os.path.join(HERE, "state")
STATUS_PATH = os.path.join(STATE_DIR, "status.json")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_S1 = "qwen/qwen3-235b-a22b-thinking-2507"
DEFAULT_S2 = "deepseek/deepseek-v4-flash"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def gather_context(repo: C.Repo, git_log_window: int, compact: bool) -> str:
    parts: list[str] = []

    # Open issues
    raw = _run(
        ["gh", "issue", "list", "--repo", repo.gh, "--state", "open",
         "--limit", "40", "--json", "number,title,body"],
        cwd=repo.path,
    )
    if raw:
        try:
            issues = json.loads(raw)
        except json.JSONDecodeError:
            issues = []
    else:
        issues = []

    if issues:
        if compact:
            lines = [f"#{i['number']} {i['title']}" for i in issues]
            parts.append("## Open issues\n" + "\n".join(lines))
        else:
            chunks = []
            for i in issues:
                body = (i.get("body") or "")[:4000]
                chunks.append(f"### #{i['number']} {i['title']}\n{body}")
            parts.append("## Open issues\n" + "\n\n".join(chunks))
    else:
        parts.append("## Open issues\n(unavailable)")

    # Git log
    log = _run(["git", "log", "--oneline", f"-n{git_log_window}"], cwd=repo.path)
    if log:
        parts.append("## Git log\n" + log.rstrip())

    # Key files
    for rel in ("README.md", "CLAUDE.md", "AGENTS.md"):
        fpath = os.path.join(repo.path, rel)
        if os.path.isfile(fpath):
            try:
                with open(fpath, encoding="utf-8") as f:
                    txt = f.read()
                if compact:
                    txt = txt[:1500]
                parts.append(f"## {rel}\n{txt}")
            except OSError:
                pass

    return "\n\n".join(parts)


def openrouter_call(
    model: str,
    messages: list[dict],
    *,
    api_key: str,
    temperature: float,
    max_tokens: int,
    reasoning: dict | None = None,
    response_format: dict | None = None,
    seed: int | None = None,
    retries: int = 3,
) -> dict:
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "max_tokens": max_tokens,
    }
    if reasoning is not None:
        body["reasoning"] = reasoning
    if response_format is not None:
        body["response_format"] = response_format
    if seed is not None:
        body["seed"] = seed

    data = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_exc = exc
            time.sleep(2 ** attempt)

    raise RuntimeError(f"openrouter_call failed after {retries} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------


def _log_path(repo_name: str) -> str:
    return os.path.join(DECISIONS_DIR, f"{repo_name}.ralph-log.md")


def _prior_titles(repo_name: str) -> list[str]:
    path = _log_path(repo_name)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    titles: list[str] = []
    for line in lines:
        if line.startswith("## ") and "Decision #" in line:
            # "## DATE — Decision #N: TITLE"
            if ":" in line:
                titles.append(line.split(":", 1)[1].strip())
            else:
                titles.append(line.strip())
    return titles


def _read_log(repo_name: str) -> str:
    path = _log_path(repo_name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(none)"


_LOG_HEADER = (
    "# Ralph decision log — {repo}\n\n"
    "> Machine-generated, ADVISORY. Each entry is one strategic decision surfaced by the ralph loop "
    "(qwen3-235b-thinking → deepseek-v4-flash). A human ratifies; entries are appended, never rewritten.\n\n"
)


def _append_log(repo_name: str, entry: str) -> None:
    os.makedirs(DECISIONS_DIR, exist_ok=True)
    path = _log_path(repo_name)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(_LOG_HEADER.format(repo=repo_name))
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


def _today() -> str:
    return datetime.date.today().isoformat()


def _open_issue_count(repo: C.Repo) -> int:
    raw = _run(
        ["gh", "issue", "list", "--repo", repo.gh, "--state", "open",
         "--limit", "200", "--json", "number"],
        cwd=repo.path,
    )
    if not raw:
        return 0
    try:
        return len(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Stage-1 schema
# ---------------------------------------------------------------------------

_STAGE1_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "candidates", "strict": True,
        "schema": {"type": "object", "properties": {"candidates": {"type": "array",
            "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "why_now": {"type": "string"},
                "urgency": {"type": "integer"}, "addressed": {"type": "boolean"}},
                "required": ["title", "why_now", "urgency", "addressed"]}}},
            "required": ["candidates"]}}}


# ---------------------------------------------------------------------------
# Live decide path (Task 8)
# ---------------------------------------------------------------------------


def _message_content(resp: dict) -> "str | None":
    """The assistant message text of an OpenRouter response, or None if the
    response has no usable content. Guards the realistic non-standard 200s:
    empty ``choices`` (content filtering) and ``content: null`` (a thinking
    model that emitted only reasoning) — so callers skip rather than crash."""
    try:
        choices = resp.get("choices") or []
        if not choices:
            return None
        return choices[0].get("message", {}).get("content")
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _decide_live(args, repo: C.Repo, s1_msgs: list[dict], api_key: str) -> float:
    s1 = openrouter_call(args.stage1_model, s1_msgs, api_key=api_key,
                         temperature=0.4, max_tokens=2000,
                         reasoning={"enabled": True, "effort": "medium"},
                         response_format=_STAGE1_SCHEMA, seed=args.seed)
    s1_text = _message_content(s1)
    try:
        cands = json.loads(s1_text).get("candidates", []) if s1_text else []
    except json.JSONDecodeError:
        cands = []
    if not cands:
        print("stage-1 returned no usable candidates; skipping iteration",
              file=sys.stderr)
        return 0.0
    chosen = C.select_candidate(cands)
    if chosen is None:
        print("no candidates; skipping", file=sys.stderr)
        return 0.0
    full = gather_context(repo, args.git_log_window, compact=False)
    full += "\n\n## Full prior decisions\n" + _read_log(repo.name)
    s2_msgs = C.build_stage2_messages(repo.name, full, chosen)
    s2 = openrouter_call(args.stage2_model, s2_msgs, api_key=api_key,
                         temperature=0.3, max_tokens=1800)
    body = _message_content(s2)
    if not body:
        print("stage-2 returned no usable content; skipping iteration",
              file=sys.stderr)
        return 0.0
    p1 = C.FALLBACK_PRICES.get(args.stage1_model, C.Price(0.10, 0.10))
    p2 = C.FALLBACK_PRICES.get(args.stage2_model, C.Price(0.10, 0.20))
    cost = C.cost_usd(s1.get("usage", {}), p1) + C.cost_usd(s2.get("usage", {}), p2)
    head = _run(["git", "rev-parse", "--short", "HEAD"], repo.path).strip() or "?"
    n = len(_prior_titles(repo.name)) + 1
    entry = C.format_entry(n=n, date=_today(), repo=repo.name, head=head,
                           open_issues=_open_issue_count(repo), body=body,
                           s1=args.stage1_model.split("/")[-1],
                           s2=args.stage2_model.split("/")[-1])
    _append_log(repo.name, entry)
    print("decided #%d for %s (cost $%.4f): %s" % (n, repo.name, cost,
                                                    entry.splitlines()[0]))
    return cost


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_decide(args) -> int:
    repos_list = C.load_repos(args.repos)
    repo_map = {r.name: r for r in repos_list}
    if args.repo not in repo_map:
        print(f"unknown repo: {args.repo!r}", file=sys.stderr)
        return 2

    repo = repo_map[args.repo]
    compact_ctx = gather_context(repo, args.git_log_window, compact=True)
    prior_titles = _prior_titles(repo.name)
    s1_msgs = C.build_stage1_messages(repo.name, compact_ctx, prior_titles)

    if args.dry_run:
        model = args.stage1_model
        approx_tokens = sum(len(m["content"]) // 4 for m in s1_msgs)
        print(f"=== stage 1 prompt ({model}) ===")
        print(json.dumps(s1_msgs, indent=2)[:2000])
        print(f"=== cost estimate ===")
        print(f"approximate token estimate: ~{approx_tokens} prompt tokens")
        return 0

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        return 1

    _decide_live(args, repo, s1_msgs, api_key)
    return 0


def cmd_run(args) -> int:
    raise NotImplementedError


def cmd_watch(args) -> int:
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repos", default=os.path.join(HERE, "repos.json"))
    common.add_argument("--stage1-model", default=DEFAULT_S1)
    common.add_argument("--stage2-model", default=DEFAULT_S2)
    common.add_argument("--git-log-window", type=int, default=30)

    parser = argparse.ArgumentParser(prog="ralph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_decide = sub.add_parser("decide", parents=[common])
    p_decide.add_argument("--repo", required=True)
    p_decide.add_argument("--seed", type=int, default=42)
    p_decide.add_argument("--dry-run", action="store_true")
    p_decide.set_defaults(func=cmd_decide)

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--interval", type=int, default=900)
    p_run.add_argument("--budget-total", type=float, default=2.00)
    p_run.add_argument("--max-iters", type=int, default=0)
    p_run.set_defaults(func=cmd_run)

    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--refresh", type=int, default=3)
    p_watch.set_defaults(func=cmd_watch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
