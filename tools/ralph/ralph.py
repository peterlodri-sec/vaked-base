#!/usr/bin/env python3
"""ralph — decision/strategy loop (decide / run / watch). Stdlib only."""
from __future__ import annotations
import argparse
import datetime
import glob
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
CONTROL_PATH = os.path.join(STATE_DIR, "control.json")
EVENTS_PATH = os.path.join(STATE_DIR, "events.jsonl")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PURPOSE_PATH = os.path.join(HERE, "PURPOSE.md")
DEFAULT_S1 = "qwen/qwen3-235b-a22b-thinking-2507"
DEFAULT_S2 = "deepseek/deepseek-v4-flash"
HOME_GH = "peterlodri-sec/vaked-base"   # tracks read issues from the home repo


def read_purpose() -> str:
    """The PURPOSE.md mission preamble injected into every stage-1 call. Empty
    string if absent (the loop still works, just without the goal preamble)."""
    try:
        with open(PURPOSE_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# Endpoint + key resolution (OpenRouter by default; override to a self-hosted,
# trust-boundary endpoint — e.g. agentfield-inference-host — to avoid sending
# private-repo content to a third party).  Precedence: explicit arg > env > default.
def _resolve_base_url(explicit: "str | None" = None) -> str:
    return explicit or os.environ.get("RALPH_BASE_URL") or OPENROUTER_URL


def _resolve_api_key() -> str:
    return os.environ.get("RALPH_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""


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


# ---------------------------------------------------------------------------
# Per-track context (read-only, all inside the home repo / vaked-base)
# ---------------------------------------------------------------------------


def _expand_doc_globs(patterns: list[str]) -> list[str]:
    """Resolve track doc globs against REPO_HOME. `recursive=True` is required
    so `**` descends (else protocol/** + vaked/examples/** drop nested files);
    keep only files, de-duped and sorted for determinism."""
    seen: set[str] = set()
    out: list[str] = []
    for pat in patterns:
        for fp in sorted(glob.glob(os.path.join(REPO_HOME, pat), recursive=True)):
            if os.path.isfile(fp) and fp not in seen:
                seen.add(fp)
                out.append(fp)
    return out


def _track_issues(label: str) -> "tuple[list[dict], str]":
    """Open issues in the home repo filtered by `label`. Falls back to all-open
    (with a note) ONLY when the label filter itself fails (gh unavailable / the
    label is unusable) — a successful-but-empty scoped result is preserved, so a
    freshly-triaged label with zero issues stays scoped instead of pulling in
    unrelated work. Returns (issues, note)."""
    def _query(extra: list[str]) -> "list[dict] | None":
        # None ⇒ gh unavailable / error; [] ⇒ a successful but empty result.
        raw = _run(["gh", "issue", "list", "--repo", HOME_GH, "--state", "open",
                    "--limit", "40", "--json", "number,title,body"] + extra,
                   cwd=REPO_HOME)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    if label:
        issues = _query(["--label", label])
        if issues is not None:
            return issues, ""   # scoped result (even if empty) — keep it
        return (_query([]) or []), f" (no usable {label} filter; showing all open)"
    return (_query([]) or []), ""


def gather_track_context(track: C.Track, git_log_window: int, compact: bool) -> str:
    """Read-only project state scoped to a track, all inside REPO_HOME:
    label-filtered home-repo issues, the track's doc globs, and a path-scoped
    git log. compact=True trims for stage 1; full text for stage 2."""
    parts: list[str] = []

    issues, note = _track_issues(track.label)
    if issues:
        if compact:
            lines = [f"#{i['number']} {i['title']}" for i in issues]
            parts.append(f"## Open issues{note}\n" + "\n".join(lines))
        else:
            chunks = [f"### #{i['number']} {i['title']}\n{(i.get('body') or '')[:4000]}"
                      for i in issues]
            parts.append(f"## Open issues{note}\n" + "\n\n".join(chunks))
    else:
        parts.append("## Open issues\n(unavailable)")

    for fpath in _expand_doc_globs(track.context.docs):
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            continue
        rel = os.path.relpath(fpath, REPO_HOME)
        parts.append(f"## {rel}\n{txt[:1500] if compact else txt}")

    cmd = ["git", "log", "--oneline", f"-n{git_log_window}"]
    if track.context.paths:
        cmd += ["--", *track.context.paths]
    log = _run(cmd, cwd=REPO_HOME)
    if log:
        parts.append("## Git log\n" + log.rstrip())

    return "\n\n".join(parts)


def _open_track_issue_count(track: C.Track) -> int:
    cmd = ["gh", "issue", "list", "--repo", HOME_GH, "--state", "open",
           "--limit", "200", "--json", "number"]
    if track.label:
        cmd += ["--label", track.label]
    raw = _run(cmd, cwd=REPO_HOME)
    if not raw:
        return 0
    try:
        return len(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return 0


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
    base_url: str | None = None,
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
            req = urllib.request.Request(_resolve_base_url(base_url), data=data, headers=headers)
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


def _run_stages(subject, s1_msgs, full_context_builder, stage1_model,
                stage2_model, api_key, base_url, seed):
    """Run both LLM stages and return ``(cost, body)`` or ``None`` to skip the
    iteration. `subject` keys the stage-2 prompt; `full_context_builder()` is
    called only once stage 1 yields a candidate (so we don't gather the full
    context for a skipped iteration). Shared by repo and track decide paths."""
    s1 = openrouter_call(stage1_model, s1_msgs, api_key=api_key,
                         temperature=0.4, max_tokens=2000,
                         reasoning={"enabled": True, "effort": "medium"},
                         response_format=_STAGE1_SCHEMA, seed=seed,
                         base_url=base_url)
    s1_text = _message_content(s1)
    try:
        cands = json.loads(s1_text).get("candidates", []) if s1_text else []
    except json.JSONDecodeError:
        cands = []
    if not cands:
        print("stage-1 returned no usable candidates; skipping iteration",
              file=sys.stderr)
        return None
    chosen = C.select_candidate(cands)
    if chosen is None:
        print("no candidates; skipping", file=sys.stderr)
        return None
    full = full_context_builder()
    s2_msgs = C.build_stage2_messages(subject, full, chosen)
    s2 = openrouter_call(stage2_model, s2_msgs, api_key=api_key,
                         temperature=0.3, max_tokens=1800, base_url=base_url)
    body = _message_content(s2)
    if not body:
        print("stage-2 returned no usable content; skipping iteration",
              file=sys.stderr)
        return None
    p1 = C.FALLBACK_PRICES.get(stage1_model, C.Price(0.10, 0.10))
    p2 = C.FALLBACK_PRICES.get(stage2_model, C.Price(0.10, 0.20))
    cost = C.cost_usd(s1.get("usage", {}), p1) + C.cost_usd(s2.get("usage", {}), p2)
    return cost, body


def _decide_live(args, repo: C.Repo, s1_msgs: list[dict], api_key: str) -> float:
    """Deprecated repo-mode iteration: two-stage, two-model (stage1/stage2)."""
    base_url = getattr(args, "base_url", None)

    def full_ctx() -> str:
        return (gather_context(repo, args.git_log_window, compact=False)
                + "\n\n## Full prior decisions\n" + _read_log(repo.name))

    result = _run_stages(repo.name, s1_msgs, full_ctx, args.stage1_model,
                         args.stage2_model, api_key, base_url, args.seed)
    if result is None:
        return 0.0
    cost, body = result
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


def _decide_track(args, track: C.Track, api_key: str) -> float:
    """Track-mode iteration: two-stage, ONE model (track.model) for both
    stages. Writes to docs/decisions/<track>.ralph-log.md."""
    base_url = getattr(args, "base_url", None)
    compact = gather_track_context(track, args.git_log_window, compact=True)
    s1_msgs = C.build_stage1_messages(track.topic, compact,
                                      _prior_titles(track.name),
                                      mission=read_purpose())

    def full_ctx() -> str:
        return (gather_track_context(track, args.git_log_window, compact=False)
                + "\n\n## Full prior decisions\n" + _read_log(track.name))

    result = _run_stages(track.topic, s1_msgs, full_ctx, track.model,
                         track.model, api_key, base_url, args.seed)
    if result is None:
        # No decision this tick (model skipped). Still advance the rotation
        # pointer with a skip event, or one flaky track would starve the rest.
        append_event({"event": "skip", "track": track.name})
        return 0.0
    cost, body = result
    head = _run(["git", "rev-parse", "--short", "HEAD"], REPO_HOME).strip() or "?"
    n = len(_prior_titles(track.name)) + 1
    model_short = track.model.split("/")[-1]
    entry = C.format_entry(n=n, date=_today(), repo=track.name, head=head,
                           open_issues=_open_track_issue_count(track), body=body,
                           s1=model_short, s2=model_short, subject_label="Track")
    _append_log(track.name, entry)
    # Emit the rotation event so --next-track advances and CI persists it.
    # The track decision-maker logs its own decide event (unlike repo-mode,
    # where cmd_run appends); a future track supervisor must not double-append.
    # `total_cost` is cumulative (prior ledger spend + this cost) so
    # `events --replay` reconstructs total spend across stateless CI runs.
    append_event({"event": "decide", "track": track.name, "iteration": n,
                  "cost": cost, "total_cost": _events_total_cost() + cost})
    print("decided #%d for %s (cost $%.4f): %s" % (n, track.name, cost,
                                                   entry.splitlines()[0]))
    return cost


def _last_decided_track() -> "str | None":
    """The most recently *attempted* track (rotation pointer for --next-track).
    Counts both `decide` and `skip` events — a skip must still advance rotation
    so one flaky track can't starve the others. None if none attempted yet."""
    for e in reversed(load_events()):
        payload = e.get("payload", {})
        if payload.get("track") and payload.get("event") in ("decide", "skip"):
            return payload["track"]
    return None


def _events_total_cost() -> float:
    """Cumulative spend recorded across decide events (the max `total_cost` seen,
    which the supervisor and track decide both write monotonically)."""
    total = 0.0
    for e in load_events():
        payload = e.get("payload", {})
        if payload.get("event") == "decide":
            total = max(total, float(payload.get("total_cost", 0.0) or 0.0))
    return total


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_decide(args) -> int:
    # Track mode is primary; --repo is the deprecated path.
    if getattr(args, "track", None) or getattr(args, "next_track", False):
        return _cmd_decide_track(args)
    if not getattr(args, "repo", None):
        print("one of --track / --next-track / --repo is required", file=sys.stderr)
        return 2
    print("note: --repo mode is deprecated; prefer --track", file=sys.stderr)

    repos_list = C.load_repos(args.repos)
    repo_map = {r.name: r for r in repos_list}
    if args.repo not in repo_map:
        print(f"unknown repo: {args.repo!r}", file=sys.stderr)
        return 2

    repo = repo_map[args.repo]
    compact_ctx = gather_context(repo, args.git_log_window, compact=True)
    prior_titles = _prior_titles(repo.name)
    s1_msgs = C.build_stage1_messages(repo.name, compact_ctx, prior_titles, mission=read_purpose())

    if args.dry_run:
        model = args.stage1_model
        approx_tokens = sum(len(m["content"]) // 4 for m in s1_msgs)
        print(f"=== stage 1 prompt ({model}) ===")
        print(json.dumps(s1_msgs, indent=2)[:2000])
        print(f"=== cost estimate ===")
        print(f"approximate token estimate: ~{approx_tokens} prompt tokens")
        return 0

    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    _decide_live(args, repo, s1_msgs, api_key)
    return 0


def _cmd_decide_track(args) -> int:
    tracks = C.load_tracks(args.tracks)
    tmap = {t.name: t for t in tracks}
    if getattr(args, "next_track", False):
        nxt = C.next_track([t.name for t in tracks], _last_decided_track(), set())
        if nxt is None:
            print("no tracks available", file=sys.stderr)
            return 2
        track = tmap[nxt]
    else:
        if args.track not in tmap:
            print(f"unknown track: {args.track!r}", file=sys.stderr)
            return 2
        track = tmap[args.track]

    compact_ctx = gather_track_context(track, args.git_log_window, compact=True)
    s1_msgs = C.build_stage1_messages(track.topic, compact_ctx,
                                      _prior_titles(track.name),
                                      mission=read_purpose())

    if args.dry_run:
        approx_tokens = sum(len(m["content"]) // 4 for m in s1_msgs)
        print(f"=== stage 1 prompt ({track.model}) ===")
        print(json.dumps(s1_msgs, indent=2)[:2000])
        print("=== cost estimate ===")
        print(f"approximate token estimate: ~{approx_tokens} prompt tokens")
        return 0

    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    _decide_track(args, track, api_key)
    return 0


def read_status() -> "dict | None":
    if not os.path.exists(STATUS_PATH):
        return None
    try:
        return json.load(open(STATUS_PATH, encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_status(status: dict) -> None:
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2)
    os.replace(tmp, STATUS_PATH)


def read_control() -> C.Control:
    """Read CONTROL_PATH and parse it. Missing or malformed -> defaults."""
    try:
        with open(CONTROL_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return C.parse_control(d)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return C.parse_control(None)


def _clear_step() -> None:
    """Reset the one-shot `step` flag after a stepped iteration, keeping
    paused/interval intact. No-op if control.json is missing/unset."""
    try:
        with open(CONTROL_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if d.get("step"):
        d["step"] = False
        tmp = CONTROL_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, CONTROL_PATH)


def _events_tail_hash() -> str:
    """Return the `hash` of the last entry in EVENTS_PATH, or GENESIS_HASH."""
    try:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            last = None
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if last is None:
            return C.GENESIS_HASH
        return json.loads(last)["hash"]
    except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError):
        return C.GENESIS_HASH


def _events_count() -> int:
    """Number of entries in EVENTS_PATH (= next seq)."""
    try:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except (FileNotFoundError, OSError):
        return 0


def append_event(payload: dict) -> dict:
    """Build and append one hash-chained entry to EVENTS_PATH. Return the entry."""
    prev = _events_tail_hash()
    seq = _events_count()
    entry = C.make_entry(prev, seq, payload)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _supervised_decide(args, repo: C.Repo, status: dict) -> None:
    """One decide iteration; fold cost + result into status. Contained --
    a failure here never crashes the supervisor."""
    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY — cannot decide",
              file=sys.stderr)
        return
    try:
        compact = gather_context(repo, args.git_log_window, compact=True)
        s1_msgs = C.build_stage1_messages(repo.name, compact, _prior_titles(repo.name), mission=read_purpose())
        before = len(_prior_titles(repo.name))
        cost = _decide_live(args, repo, s1_msgs, api_key)
        status["total_cost"] = status.get("total_cost", 0.0) + cost
        after = _prior_titles(repo.name)
        rep = status["repos"].setdefault(repo.name,
                                         {"entries": 0, "last_title": "-", "cost": 0.0})
        rep["cost"] = rep.get("cost", 0.0) + cost
        if len(after) > before:
            rep["entries"] = len(after)
            rep["last_title"] = after[-1]
            status["recent"].insert(0, {"repo": repo.name, "date": _today(),
                                        "title": after[-1]})
            status["recent"] = status["recent"][:10]
    except Exception as e:
        print("iteration failed for %s: %s" % (repo.name, e), file=sys.stderr)


def _apply_state_dir(d: str) -> None:
    """Redirect all state-file globals to an alternate directory."""
    global STATE_DIR, STATUS_PATH, CONTROL_PATH, EVENTS_PATH
    STATE_DIR = d
    STATUS_PATH = os.path.join(d, "status.json")
    CONTROL_PATH = os.path.join(d, "control.json")
    EVENTS_PATH = os.path.join(d, "events.jsonl")


def _supervised_decide_track(args, track: C.Track, status: dict) -> None:
    """One track decide iteration; fold cost + result into status. Contained --
    a failure here never crashes the supervisor. `_decide_track` appends its own
    decide/skip event, so the track supervisor must NOT double-append."""
    api_key = _resolve_api_key()
    if not api_key:
        print("no API key — set RALPH_API_KEY or OPENROUTER_API_KEY — cannot decide",
              file=sys.stderr)
        return
    try:
        before = len(_prior_titles(track.name))
        cost = _decide_track(args, track, api_key)
        status["total_cost"] = status.get("total_cost", 0.0) + cost
        after = _prior_titles(track.name)
        subjects = status.setdefault("subjects", {})
        rec = subjects.setdefault(track.name,
                                  {"entries": 0, "last_title": "-", "cost": 0.0,
                                   "model": track.model})
        rec["model"] = track.model
        rec["cost"] = rec.get("cost", 0.0) + cost
        if len(after) > before:
            rec["entries"] = len(after)
            rec["last_title"] = after[-1]
            status.setdefault("recent", []).insert(
                0, {"subject": track.name, "date": _today(), "title": after[-1]})
            status["recent"] = status["recent"][:10]
    except Exception as e:
        print("iteration failed for %s: %s" % (track.name, e), file=sys.stderr)


def cmd_run(args) -> int:
    if getattr(args, "state_dir", None):
        _apply_state_dir(args.state_dir)
    if getattr(args, "repo_mode", False):
        return _run_repos(args)
    return _run_tracks(args)


def _run_tracks(args) -> int:
    """Supervisor over concept tracks (the primary mode): round-robin tracks,
    one model each, budget-capped. Each iteration's decide/skip event is logged
    by _decide_track itself."""
    tracks = C.load_tracks(args.tracks)
    names = [t.name for t in tracks]
    by_name = {t.name: t for t in tracks}
    status = read_status()
    if status is None:
        # status.json is a derived cache (gitignored); the committed event
        # ledger is the state-of-record. Seed rotation + spend from it so a
        # stateless restart resumes instead of re-running track #1 / re-spending.
        status = {
            "running": True, "current": _last_decided_track(), "iteration": 0,
            "total_cost": _events_total_cost(), "budget_total": args.budget_total,
            "subjects": {t.name: {"entries": 0, "last_title": "-", "cost": 0.0,
                                  "model": t.model} for t in tracks},
            "recent": [], "last_step_epoch": 0, "mode": "tracks",
        }
    status["running"] = True
    status["budget_total"] = args.budget_total
    status.setdefault("subjects", {})
    iters = 0
    ticks = 0
    try:
        while True:
            if args.max_ticks and ticks >= args.max_ticks:
                break
            ctrl = read_control()
            if status["total_cost"] >= args.budget_total:
                print("budget cap reached ($%.2f) — stopping" % args.budget_total)
                break
            if args.max_iters and iters >= args.max_iters:
                print("max-iters reached — stopping")
                break
            interval = ctrl.interval if ctrl.interval is not None else args.interval
            if ctrl.paused and not ctrl.step:
                append_event({"tick": ticks, "event": "paused"})
                ticks += 1
                write_status(status)
                time.sleep(min(interval, 2.0))
                continue
            nxt = C.next_track(names, status["current"], set())
            if nxt is None:
                print("no tracks available — stopping", file=sys.stderr)
                break
            status["current"] = nxt
            status["iteration"] += 1
            iters += 1
            _supervised_decide_track(args, by_name[nxt], status)
            status["last_step_epoch"] = int(time.time())
            if ctrl.step:                 # one-shot consumed → back to paused
                _clear_step()
            ticks += 1
            write_status(status)
            if args.max_iters and iters >= args.max_iters:
                continue
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSIGINT — shutting down")
    finally:
        status["running"] = False
        write_status(status)
    return 0


def _run_repos(args) -> int:
    """DEPRECATED supervisor over whole repos (the original round-robin)."""
    repos = C.load_repos(args.repos)
    names = [r.name for r in repos]
    by_name = {r.name: r for r in repos}
    status = read_status() or {
        "running": True, "current": None, "iteration": 0,
        "total_cost": 0.0, "budget_total": args.budget_total,
        "repos": {n: {"entries": 0, "last_title": "-", "cost": 0.0} for n in names},
        "recent": [], "last_step_epoch": 0,
    }
    status["running"] = True
    status["budget_total"] = args.budget_total
    iters = 0
    ticks = 0
    try:
        while True:
            if args.max_ticks and ticks >= args.max_ticks:
                break
            ctrl = read_control()
            if status["total_cost"] >= args.budget_total:
                print("budget cap reached ($%.2f) — stopping" % args.budget_total)
                break
            if args.max_iters and iters >= args.max_iters:
                print("max-iters reached — stopping")
                break
            interval = ctrl.interval if ctrl.interval is not None else args.interval
            if ctrl.paused and not ctrl.step:
                append_event({"tick": ticks, "event": "paused"})
                ticks += 1
                write_status(status)
                time.sleep(min(interval, 2.0))
                continue
            unavailable = {r.name for r in repos if not os.path.isdir(r.path)}
            nxt = C.next_repo(names, status["current"], unavailable)
            if nxt is None:
                print("no available repos — stopping", file=sys.stderr)
                break
            status["current"] = nxt
            status["iteration"] += 1
            iters += 1
            _supervised_decide(args, by_name[nxt], status)
            status["last_step_epoch"] = int(time.time())
            append_event({"tick": ticks, "event": "decide", "repo": nxt,
                          "iteration": status["iteration"],
                          "total_cost": status["total_cost"]})
            if ctrl.step:                 # one-shot consumed → back to paused
                _clear_step()
            ticks += 1
            write_status(status)
            if args.max_iters and iters >= args.max_iters:
                continue
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSIGINT — shutting down")
    finally:
        status["running"] = False
        write_status(status)
    return 0


def load_events() -> list[dict]:
    """Read EVENTS_PATH and return a list of JSON entries (empty if file missing)."""
    try:
        with open(EVENTS_PATH, encoding="utf-8") as f:
            entries = []
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
            return entries
    except (FileNotFoundError, OSError):
        return []


def replay_events(entries: list[dict]) -> dict:
    """Pure fold over entries → reconstructed view. entries must already be verified."""
    state: dict = {
        "decisions": 0,
        "ticks": len(entries),
        "total_cost": 0.0,
        "subjects": {},
        "paused": 0,
    }
    for e in entries:
        p = e.get("payload", {})
        event = p.get("event")
        if event == "decide":
            state["decisions"] += 1
            cost = p.get("total_cost", 0.0)
            if cost > state["total_cost"]:
                state["total_cost"] = cost
            # repo-mode events key on "repo"; track-mode on "track". Bucket
            # either so per-subject (per-track/per-model) audit stays populated.
            subject = p.get("repo") or p.get("track")
            if subject is not None:
                rec = state["subjects"].setdefault(subject, {"decisions": 0, "last_iteration": None})
                rec["decisions"] += 1
                rec["last_iteration"] = p.get("iteration")
        elif event == "paused":
            state["paused"] += 1
    # Back-compat alias: callers/tests that read the old "repos" key still work.
    state["repos"] = state["subjects"]
    return state


def cmd_events(args) -> int:
    if getattr(args, "state_dir", None):
        _apply_state_dir(args.state_dir)
    entries = load_events()
    ok = C.verify_chain(entries)
    if not ok:
        print(f"events: chain INVALID at {len(entries)} entries")
        return 1
    if getattr(args, "replay", False):
        state = replay_events(entries)
        print(json.dumps(state, indent=2))
    else:
        print(f"events: {len(entries)} entries, chain OK")
    return 0


def cmd_watch(args) -> int:
    try:
        while True:
            status = read_status()
            last = status.get("last_step_epoch", 0) if status else 0
            out = C.render_dashboard(status, int(time.time()), last)
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.write(out)
            sys.stdout.flush()
            time.sleep(args.refresh)
    except KeyboardInterrupt:
        return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repos", default=os.path.join(HERE, "repos.json"))
    common.add_argument("--stage1-model", default=DEFAULT_S1)
    common.add_argument("--stage2-model", default=DEFAULT_S2)
    common.add_argument("--git-log-window", type=int, default=30)
    common.add_argument("--base-url", default=None,
                        help="OpenAI-compatible endpoint (default OpenRouter; or "
                             "set RALPH_BASE_URL — point at a self-hosted, "
                             "trust-boundary endpoint to keep private content local)")

    parser = argparse.ArgumentParser(prog="ralph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_decide = sub.add_parser("decide", parents=[common])
    p_decide.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_decide.add_argument("--track", help="concept track from tracks.json (primary)")
    p_decide.add_argument("--next-track", action="store_true",
                          help="pick the next track via the event-log rotation pointer")
    p_decide.add_argument("--repo", help="DEPRECATED: repo mode (prefer --track)")
    p_decide.add_argument("--seed", type=int, default=42)
    p_decide.add_argument("--dry-run", action="store_true")
    p_decide.set_defaults(func=cmd_decide)

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--tracks", default=os.path.join(HERE, "tracks.json"))
    p_run.add_argument("--repo-mode", action="store_true",
                       help="DEPRECATED: round-robin whole repos instead of tracks")
    p_run.add_argument("--interval", type=int, default=900)
    p_run.add_argument("--budget-total", type=float, default=2.00)
    p_run.add_argument("--max-iters", type=int, default=0)
    p_run.add_argument("--max-ticks", type=int, default=0,
                       help="stop after this many control polls (0 = unbounded)")
    p_run.add_argument("--state-dir", default=None,
                       help="override state directory (default: tools/ralph/state/)")
    p_run.add_argument("--seed", type=int, default=42)
    p_run.set_defaults(func=cmd_run)

    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--refresh", type=int, default=3)
    p_watch.set_defaults(func=cmd_watch)

    p_events = sub.add_parser("events")
    p_events.add_argument("--replay", action="store_true",
                          help="verify then print reconstructed state as JSON")
    p_events.add_argument("--state-dir", default=None,
                          help="override state directory (default: tools/ralph/state/)")
    p_events.set_defaults(func=cmd_events)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
