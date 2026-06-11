"""Standalone test runner for ralphcore + ralph."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pass(name: str) -> None:
    print(f"PASS  {name}")


def _fail(name: str, exc: BaseException) -> None:
    print(f"FAIL  {name}: {exc}")


# ---------------------------------------------------------------------------
# Task 1 — Config: repos.json + loader
# ---------------------------------------------------------------------------

def test_load_repos_expands_paths() -> None:
    from ralphcore import load_repos, Repo

    data = {"repos": [{"name": "r", "path": "~/x", "gh": "o/r"}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp = f.name
    try:
        repos = load_repos(tmp)
        assert len(repos) == 1, f"expected 1 repo, got {len(repos)}"
        r = repos[0]
        assert r.name == "r", f"name mismatch: {r.name}"
        assert r.gh == "o/r", f"gh mismatch: {r.gh}"
        assert not r.path.startswith("~"), f"path not expanded: {r.path}"
        # must be absolute
        assert os.path.isabs(r.path), f"path not absolute: {r.path}"
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Task 2 — Cost math
# ---------------------------------------------------------------------------

def test_cost_usd() -> None:
    from ralphcore import cost_usd, Price

    usage = {"prompt_tokens": 10_000, "completion_tokens": 2_000}
    price = Price(prompt_per_m=0.10, completion_per_m=0.10)
    result = cost_usd(usage, price)
    expected = 0.0012
    assert abs(result - expected) < 1e-9, f"cost_usd={result}, expected {expected}"


# ---------------------------------------------------------------------------
# Task 3 — Candidate selection
# ---------------------------------------------------------------------------

def test_select_candidate_highest_urgency_unaddressed() -> None:
    from ralphcore import select_candidate

    candidates = [
        {"title": "A", "urgency": 3, "addressed": False},
        {"title": "B", "urgency": 5, "addressed": True},
        {"title": "C", "urgency": 4, "addressed": False},
    ]
    result = select_candidate(candidates)
    assert result is not None
    assert result["title"] == "C", f"expected C, got {result['title']}"


def test_select_candidate_all_addressed() -> None:
    from ralphcore import select_candidate

    candidates = [
        {"title": "A", "urgency": 3, "addressed": True},
        {"title": "B", "urgency": 5, "addressed": True},
    ]
    result = select_candidate(candidates)
    assert result is not None
    assert result["title"] == "B", f"expected B (highest urgency), got {result['title']}"


def test_select_candidate_empty() -> None:
    from ralphcore import select_candidate

    result = select_candidate([])
    assert result is None, f"expected None, got {result}"


# ---------------------------------------------------------------------------
# Task 4 — Round-robin
# ---------------------------------------------------------------------------

def test_next_repo_basic() -> None:
    from ralphcore import next_repo

    names = ["a", "b", "c"]
    assert next_repo(names, "a", set()) == "b", "a -> b"
    assert next_repo(names, "c", set()) == "a", "c wraps to a"
    assert next_repo(names, None, set()) == "a", "None -> first"


def test_next_repo_skip_unavailable() -> None:
    from ralphcore import next_repo

    names = ["a", "b", "c"]
    assert next_repo(names, "a", {"b"}) == "c", "skip b -> c"
    assert next_repo(names, "a", {"b", "c"}) == "a", "all others unavailable -> wrap to a"
    assert next_repo(names, "a", {"a", "b", "c"}) is None, "all unavailable -> None"


# ---------------------------------------------------------------------------
# Task 5 — Prompt + entry formatting
# ---------------------------------------------------------------------------

def test_build_stage1_messages() -> None:
    from ralphcore import build_stage1_messages

    msgs = build_stage1_messages("crabcc", "ISSUES…\nGITLOG…", ["Prior: X"])
    dumped = json.dumps(msgs)
    assert "crabcc" in dumped, "repo name missing"
    assert "Prior: X" in dumped, "prior title missing"
    assert "candidates" in dumped, "'candidates' schema hint missing"


def test_build_stage2_messages() -> None:
    from ralphcore import build_stage2_messages

    candidate = {"title": "Adopt Zoekt", "why_now": "fast", "urgency": 5}
    msgs = build_stage2_messages("crabcc", "FULL CONTEXT", candidate)
    dumped = json.dumps(msgs)
    assert "Adopt Zoekt" in dumped, "candidate title missing"
    assert "FULL CONTEXT" in dumped, "full context missing"


def test_format_entry() -> None:
    from ralphcore import format_entry

    result = format_entry(
        n=7,
        date="2026-06-11",
        repo="crabcc",
        head="abc123",
        open_issues=4,
        body="Decision body text",
        s1="qwen",
        s2="deepseek",
    )
    assert result.startswith("## 2026-06-11 — Decision #7: "), f"bad header: {result[:60]}"
    assert "**Repo:** crabcc" in result, "repo label missing"
    assert "HEAD abc123" in result, "HEAD missing"
    assert "4 open issues" in result, "open_issues missing"
    assert "Decision body text" in result, "body missing"
    assert result.endswith("\n"), "must end with newline"


# ---------------------------------------------------------------------------
# Task 6 — Dashboard rendering
# ---------------------------------------------------------------------------

def test_render_dashboard_running_and_stale() -> None:
    from ralphcore import render_dashboard

    status = {
        "running": True,
        "current": "crabcc",
        "iteration": 3,
        "total_cost": 0.42,
        "budget_total": 2.00,
        "repos": {
            "vaked-base": {"entries": 2, "last_title": "Merge cohort", "cost": 0.20},
            "crabcc": {"entries": 1, "last_title": "Adopt Zoekt", "cost": 0.22},
        },
        "recent": [{"repo": "crabcc", "date": "2026-06-11", "title": "Adopt Zoekt"}],
    }
    out = render_dashboard(status, now_epoch=1000, last_step_epoch=970)
    assert "crabcc" in out, "current repo missing"
    assert "Adopt Zoekt" in out, "recent title missing"
    assert "0.42" in out, "total cost missing"
    assert "2.00" in out, "budget missing"
    assert "30s" in out, "elapsed seconds missing"


def test_render_dashboard_no_supervisor() -> None:
    from ralphcore import render_dashboard

    out = render_dashboard(None, 0, 0)
    assert "no supervisor" in out.lower(), f"'no supervisor' missing: {out}"


# ---------------------------------------------------------------------------
# Task 7 — dry-run smoke test (no network, no API key)
# ---------------------------------------------------------------------------

def test_decide_dry_run_writes_nothing() -> None:
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    r = subprocess.run(
        [sys.executable, os.path.join(here, "ralph.py"), "decide",
         "--repo", "vaked-base", "--dry-run"],
        capture_output=True, text=True, env=env, cwd=here,
    )
    assert r.returncode == 0, r.stderr
    assert "stage 1" in r.stdout.lower() and "estimate" in r.stdout.lower()


# ---------------------------------------------------------------------------
# Task 8 — _decide_live unit tests (mocked, no network)
# ---------------------------------------------------------------------------

def test_decide_live_returns_cost() -> None:
    """_decide_live returns float USD cost and writes an entry to a temp log."""
    import importlib
    import tempfile
    import unittest.mock as mock

    ralph = importlib.import_module("ralph")
    from ralphcore import Repo, Price

    repo = Repo(name="vaked-base",
                path="/tmp/fake-vaked-base",
                gh="peterlodri-sec/vaked-base")

    s1_content = json.dumps({"candidates": [
        {"title": "Ship it", "why_now": "now", "urgency": 5, "addressed": False}
    ]})
    s1_response = {
        "choices": [{"message": {"content": s1_content}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
    }
    s2_response = {
        "choices": [{"message": {"content": "**Decision / question:** Ship it now\n**Options:** A\n**Recommendation:** A"}}],
        "usage": {"prompt_tokens": 800, "completion_tokens": 300},
    }
    calls = iter([s1_response, s2_response])

    args = types.SimpleNamespace(
        repos=os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos.json"),
        stage1_model="qwen/qwen3-235b-a22b-thinking-2507",
        stage2_model="deepseek/deepseek-v4-flash",
        git_log_window=5,
        seed=42,
    )

    from ralphcore import cost_usd, FALLBACK_PRICES
    p1 = FALLBACK_PRICES["qwen/qwen3-235b-a22b-thinking-2507"]
    p2 = FALLBACK_PRICES["deepseek/deepseek-v4-flash"]
    expected = cost_usd(s1_response["usage"], p1) + cost_usd(s2_response["usage"], p2)

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_decisions = ralph.DECISIONS_DIR
        orig_gather = ralph.gather_context
        ralph.DECISIONS_DIR = tmpdir
        ralph.gather_context = lambda repo, window, compact: "FAKE CONTEXT"

        try:
            with mock.patch.object(ralph, "openrouter_call", side_effect=lambda *a, **kw: next(calls)):
                s1_msgs = [{"role": "user", "content": "stub"}]
                cost = ralph._decide_live(args, repo, s1_msgs, "fake-key")
        finally:
            ralph.DECISIONS_DIR = orig_decisions
            ralph.gather_context = orig_gather

        assert abs(cost - expected) < 1e-9, f"cost mismatch: {cost} vs {expected}"
        log_path = os.path.join(tmpdir, "vaked-base.ralph-log.md")
        assert os.path.exists(log_path), "log file not created"
        content = open(log_path).read()
        assert "Decision #1" in content, "no decision entry in log"


def test_decide_live_skip_on_bad_json() -> None:
    """_decide_live returns 0.0 when stage-1 returns non-JSON content."""
    import importlib
    import tempfile
    import unittest.mock as mock

    ralph = importlib.import_module("ralph")
    from ralphcore import Repo

    repo = Repo(name="vaked-base", path="/tmp/fake", gh="peterlodri-sec/vaked-base")

    s1_bad = {
        "choices": [{"message": {"content": "not json at all"}}],
        "usage": {},
    }

    args = types.SimpleNamespace(
        repos=os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos.json"),
        stage1_model="qwen/qwen3-235b-a22b-thinking-2507",
        stage2_model="deepseek/deepseek-v4-flash",
        git_log_window=5,
        seed=42,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_decisions = ralph.DECISIONS_DIR
        orig_gather = ralph.gather_context
        ralph.DECISIONS_DIR = tmpdir
        ralph.gather_context = lambda repo, window, compact: "FAKE"

        try:
            with mock.patch.object(ralph, "openrouter_call", return_value=s1_bad):
                s1_msgs = [{"role": "user", "content": "stub"}]
                cost = ralph._decide_live(args, repo, s1_msgs, "fake-key")
        finally:
            ralph.DECISIONS_DIR = orig_decisions
            ralph.gather_context = orig_gather

    assert cost == 0.0, f"expected 0.0 on bad JSON, got {cost}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_load_repos_expands_paths,
        test_cost_usd,
        test_select_candidate_highest_urgency_unaddressed,
        test_select_candidate_all_addressed,
        test_select_candidate_empty,
        test_next_repo_basic,
        test_next_repo_skip_unavailable,
        test_build_stage1_messages,
        test_build_stage2_messages,
        test_format_entry,
        test_render_dashboard_running_and_stale,
        test_render_dashboard_no_supervisor,
        test_decide_dry_run_writes_nothing,
        test_decide_live_returns_cost,
        test_decide_live_skip_on_bad_json,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            _pass(t.__name__)
            passed += 1
        except Exception as exc:
            _fail(t.__name__, exc)
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
