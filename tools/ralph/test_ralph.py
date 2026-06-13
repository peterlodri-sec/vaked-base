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
            with mock.patch.dict(os.environ, {"RALPH_CRITIQUE": "off"}), \
                 mock.patch.object(ralph, "openrouter_call", side_effect=lambda *a, **kw: next(calls)):
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


def test_decide_live_skip_on_degenerate_responses() -> None:
    """_decide_live returns 0.0 (no crash) on the realistic non-standard 200s:
    empty `choices` (content filtering) and `content: null` (thinking model that
    emitted only reasoning) — not an IndexError/TypeError traceback."""
    import importlib
    import tempfile
    import unittest.mock as mock

    ralph = importlib.import_module("ralph")
    from ralphcore import Repo

    repo = Repo(name="vaked-base", path="/tmp/fake", gh="peterlodri-sec/vaked-base")
    args = types.SimpleNamespace(
        repos=os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos.json"),
        stage1_model="qwen/qwen3-235b-a22b-thinking-2507",
        stage2_model="deepseek/deepseek-v4-flash",
        git_log_window=5, seed=42,
    )

    degenerate = [
        {"choices": [], "usage": {}},                                  # empty choices
        {"choices": [{"message": {"content": None}}], "usage": {}},    # null content
        {"usage": {}},                                                 # no choices key
    ]

    for resp in degenerate:
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_decisions = ralph.DECISIONS_DIR
            orig_gather = ralph.gather_context
            ralph.DECISIONS_DIR = tmpdir
            ralph.gather_context = lambda repo, window, compact: "FAKE"
            try:
                with mock.patch.object(ralph, "openrouter_call", return_value=resp):
                    cost = ralph._decide_live(args, repo,
                                              [{"role": "user", "content": "x"}],
                                              "fake-key")
            finally:
                ralph.DECISIONS_DIR = orig_decisions
                ralph.gather_context = orig_gather
            assert cost == 0.0, f"expected 0.0 on degenerate {resp}, got {cost}"


# ---------------------------------------------------------------------------
# Task 9 — status.json round-trip
# ---------------------------------------------------------------------------

def test_status_round_trip() -> None:
    import importlib, tempfile, os
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as d:
        orig = ralph.STATUS_PATH
        ralph.STATUS_PATH = os.path.join(d, "status.json")
        try:
            ralph.write_status({"running": True, "current": "crabcc", "iteration": 2,
                                "total_cost": 0.1, "budget_total": 2.0, "repos": {}, "recent": []})
            back = ralph.read_status()
        finally:
            ralph.STATUS_PATH = orig
        assert back["current"] == "crabcc" and back["iteration"] == 2


# ---------------------------------------------------------------------------
# Task 10 — run supervisor: budget 0 → zero iterations
# ---------------------------------------------------------------------------

def test_run_budget_zero_no_iterations() -> None:
    import subprocess, sys, os
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "ralph.py"), "run",
                        "--budget-total", "0", "--max-iters", "1"],
                       capture_output=True, text=True, cwd=here, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "budget" in (r.stdout + r.stderr).lower()


def test_resolve_base_url_precedence() -> None:
    """explicit arg > RALPH_BASE_URL env > OpenRouter default."""
    import importlib
    ralph = importlib.import_module("ralph")
    orig = os.environ.get("RALPH_BASE_URL")
    try:
        os.environ.pop("RALPH_BASE_URL", None)
        assert ralph._resolve_base_url(None) == ralph.OPENROUTER_URL
        os.environ["RALPH_BASE_URL"] = "http://host:8080/v1/chat/completions"
        assert ralph._resolve_base_url(None) == "http://host:8080/v1/chat/completions"
        assert ralph._resolve_base_url("http://explicit/x") == "http://explicit/x"
    finally:
        if orig is None:
            os.environ.pop("RALPH_BASE_URL", None)
        else:
            os.environ["RALPH_BASE_URL"] = orig


def test_resolve_api_key_precedence() -> None:
    """RALPH_API_KEY > OPENROUTER_API_KEY > '' (self-hosted key wins)."""
    import importlib
    ralph = importlib.import_module("ralph")
    o1, o2 = os.environ.get("RALPH_API_KEY"), os.environ.get("OPENROUTER_API_KEY")
    try:
        os.environ.pop("RALPH_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
        assert ralph._resolve_api_key() == ""
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        assert ralph._resolve_api_key() == "or-key"
        os.environ["RALPH_API_KEY"] = "self-key"
        assert ralph._resolve_api_key() == "self-key"
    finally:
        for k, v in (("RALPH_API_KEY", o1), ("OPENROUTER_API_KEY", o2)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# M1 — hash-chained event log + live control state
# ---------------------------------------------------------------------------

def test_chain_verify_and_tamper() -> None:
    from ralphcore import make_entry, verify_chain, GENESIS_HASH, chain_hash
    e0 = make_entry(GENESIS_HASH, 0, {"step": "start"})
    e1 = make_entry(e0["hash"], 1, {"step": "decide", "repo": "crabcc"})
    e2 = make_entry(e1["hash"], 2, {"step": "decide", "repo": "vaked-base"})
    chain = [e0, e1, e2]
    assert verify_chain(chain), "clean chain must verify"
    # tamper a payload → hash no longer recomputes
    bad = [dict(e0), dict(e1), dict(e2)]
    bad[1] = dict(bad[1]); bad[1]["payload"] = {"step": "decide", "repo": "EVIL"}
    assert not verify_chain(bad), "tampered payload must fail"
    # reorder → prev-link breaks
    assert not verify_chain([e0, e2, e1]), "reordered chain must fail"
    # genesis link is enforced
    assert make_entry(GENESIS_HASH, 0, {"x": 1})["prev"] == GENESIS_HASH
    assert e1["hash"] == chain_hash(e0["hash"], e1["payload"])


def test_parse_control() -> None:
    from ralphcore import parse_control, Control
    assert parse_control(None) == Control()
    assert parse_control({}) == Control()
    assert parse_control({"paused": True}) == Control(paused=True)
    c = parse_control({"paused": False, "interval": 30, "step": True})
    assert c.interval == 30.0 and c.step is True and c.paused is False


# ---------------------------------------------------------------------------
# M1 — append_event / paused ticks
# ---------------------------------------------------------------------------

def test_event_log_chain_appends() -> None:
    """append_event 3× builds a valid hash-chained JSONL file."""
    import importlib, tempfile
    ralph = importlib.import_module("ralph")
    from ralphcore import verify_chain, GENESIS_HASH

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_events = ralph.EVENTS_PATH
        orig_state = ralph.STATE_DIR
        ralph.EVENTS_PATH = os.path.join(tmpdir, "events.jsonl")
        ralph.STATE_DIR = tmpdir
        try:
            ralph.append_event({"action": "a"})
            ralph.append_event({"action": "b"})
            ralph.append_event({"action": "c"})
        finally:
            ralph.EVENTS_PATH = orig_events
            ralph.STATE_DIR = orig_state

        with open(os.path.join(tmpdir, "events.jsonl"), encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]
        entries = [json.loads(l) for l in lines]
        assert len(entries) == 3, f"expected 3 entries, got {len(entries)}"
        assert [e["seq"] for e in entries] == [0, 1, 2], "seqs must be 0,1,2"
        assert verify_chain(entries), "chain must verify"


def test_run_paused_ticks_without_deciding() -> None:
    """--max-ticks 2 with paused=true exits rc=0 without any API call."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    from ralphcore import verify_chain

    with tempfile.TemporaryDirectory() as tmpdir:
        control = os.path.join(tmpdir, "control.json")
        with open(control, "w") as f:
            json.dump({"paused": True}, f)

        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "run",
             "--budget-total", "5", "--max-ticks", "2",
             "--interval", "0", "--state-dir", tmpdir],
            capture_output=True, text=True, cwd=here, timeout=30,
        )
        assert r.returncode == 0, f"non-zero rc: {r.stderr}"

        events_path = os.path.join(tmpdir, "events.jsonl")
        assert os.path.exists(events_path), "events.jsonl not created"
        with open(events_path, encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]
        entries = [json.loads(l) for l in lines]
        assert len(entries) == 2, f"expected 2 paused events, got {len(entries)}"
        assert all(e["payload"].get("event") == "paused" for e in entries), \
            "all events should be paused"
        assert verify_chain(entries), "chain must verify"


# ---------------------------------------------------------------------------
# M1 hardening — #57 flat-cost windowing / #58 O(1) append + fsync + boot verify
# ---------------------------------------------------------------------------

def test_window_log_caps_stage2_cost() -> None:
    """#57: window_log bounds the stage-2 'prior decisions' block — past
    keep_recent, growing the history must NOT grow the output (the PURPOSE.md
    near-flat-cost bet). Stage-2 used to inject the entire ever-growing log."""
    from ralphcore import window_log

    def make_log(n: int) -> str:
        # Fixed-size body (the index appears ONLY in the header, where windowing
        # needs it) so the only length variation between sizes is digit-count in
        # the kept headers + the elided span — isolating "O(1) in history".
        head = "# Ralph decision log — t\n\n> advisory\n\n"
        body = "".join(
            f"## 2026-06-13 — Decision #{i}: title\n"
            f"- **Track:** t · **Models:** stage1 m · stage2 m\n"
            f"fixed body line\nmore fixed body\n\n"
            for i in range(1, n + 1))
        return head + body

    # at or under the window → returned unchanged
    small = make_log(5)
    assert window_log(small, keep_recent=20) == small

    w_med = window_log(make_log(100), keep_recent=20)
    w_big = window_log(make_log(2000), keep_recent=20)
    # only the last 20 entries survive either way; size differs by at most a few
    # digits in the kept headers + the #lo–#hi span → O(1), not history-scaled.
    assert abs(len(w_big) - len(w_med)) < 128, (
        f"windowed size grew with history: {len(w_med)} vs {len(w_big)}")
    # and it is far smaller than the raw log it replaces (the bug it fixes)
    assert len(w_big) < len(make_log(2000)) // 10
    # the surviving tail is the RECENT decisions; the old prefix is summarized
    assert "Decision #2000:" in w_big and "Decision #1981:" in w_big
    assert "Decision #1:" not in w_big and "Decision #1980:" not in w_big
    assert "earlier decisions elided" in w_big

    # a markdown sub-header INSIDE a decision body must NOT be treated as a
    # decision boundary (guards the precise header regex vs a naive `^## ` split):
    # 25 real decisions, each body carrying a `## Subsection` line → exactly 5
    # elided, never miscounted by the 25 phantom sub-headers.
    sub = "# log\n\n" + "".join(
        f"## 2026-06-13 — Decision #{i}: t\n"
        f"body\n## Subsection in body {i}\nmore body\n\n"
        for i in range(1, 26))
    w_sub = window_log(sub, keep_recent=20)
    assert "[5 earlier decisions elided (#1–#5)]" in w_sub, w_sub
    assert "Decision #6: t" in w_sub and "Decision #5: t" not in w_sub


def _swap_state_dir(ralph, tmp):
    """Save the 4 state-path globals, point them at tmp, return the originals."""
    orig = (ralph.STATE_DIR, ralph.STATUS_PATH, ralph.CONTROL_PATH,
            ralph.EVENTS_PATH)
    ralph._apply_state_dir(tmp)
    return orig


def _restore_state_dir(ralph, orig):
    (ralph.STATE_DIR, ralph.STATUS_PATH, ralph.CONTROL_PATH,
     ralph.EVENTS_PATH) = orig
    ralph._reset_writer_cache()


def test_append_event_is_o1_no_rescan() -> None:
    """#58: append_event must not re-read the whole log on every call (that made
    a run of N appends O(N^2)). The single-writer head cache primes from one
    verified read, then advances in memory — the log file is read at most once
    across 50 appends (subsequent appends only stat it)."""
    import importlib
    ralph = importlib.import_module("ralph")
    from ralphcore import verify_chain

    with tempfile.TemporaryDirectory() as tmp:
        orig = _swap_state_dir(ralph, tmp)
        reads = {"n": 0}
        real_read = ralph._event_byte_lines

        def counting():
            reads["n"] += 1
            return real_read()

        ralph._event_byte_lines = counting
        try:
            for i in range(50):
                ralph.append_event({"i": i})
        finally:
            ralph._event_byte_lines = real_read
            entries = ralph.load_events()
            _restore_state_dir(ralph, orig)
        assert reads["n"] <= 1, f"re-read the log {reads['n']}x (should prime once)"
        assert len(entries) == 50, f"expected 50 entries, got {len(entries)}"
        assert [e["seq"] for e in entries] == list(range(50)), "seqs 0..49"
        assert verify_chain(entries), "chain must verify"


def test_append_refuses_broken_chain_on_prime() -> None:
    """#58: a stray append onto a tampered log (no boot gate first) must fail
    loudly — the head cache primes from a VERIFIED read, never chaining a new
    entry onto a broken/torn tail and silently forking the chain."""
    import importlib
    ralph = importlib.import_module("ralph")

    with tempfile.TemporaryDirectory() as tmp:
        orig = _swap_state_dir(ralph, tmp)
        try:
            ralph.append_event({"event": "decide", "i": 1})
            ralph.append_event({"event": "decide", "i": 2})
            lines = open(ralph.EVENTS_PATH, encoding="utf-8").read().splitlines()
            bad = json.loads(lines[0])
            bad["payload"]["i"] = 999          # tamper → stored hash now stale
            lines[0] = json.dumps(bad)
            with open(ralph.EVENTS_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            ralph._reset_writer_cache()
            raised = False
            try:
                ralph.append_event({"event": "decide", "i": 3})
            except ralph.EventLogTamper:
                raised = True
            assert raised, "append onto a tampered chain must raise EventLogTamper"
        finally:
            _restore_state_dir(ralph, orig)


def test_append_event_fsyncs() -> None:
    """#58: every append fsyncs (durability — a crash leaves at worst a torn
    final line, recoverable, never a lost acknowledged append)."""
    import importlib
    ralph = importlib.import_module("ralph")

    with tempfile.TemporaryDirectory() as tmp:
        orig = _swap_state_dir(ralph, tmp)
        fsyncs = {"n": 0}
        real_fsync = os.fsync

        def counting_fsync(fd):
            fsyncs["n"] += 1
            return real_fsync(fd)

        os.fsync = counting_fsync
        try:
            ralph.append_event({"a": 1})
            ralph.append_event({"a": 2})
        finally:
            os.fsync = real_fsync
            _restore_state_dir(ralph, orig)
        assert fsyncs["n"] >= 2, f"expected an fsync per append, got {fsyncs['n']}"


def test_boot_recover_truncates_torn_tail() -> None:
    """#58: a crash that tears the final write leaves an unparseable suffix;
    _boot_recover_events truncates it to the valid prefix + a log_repair entry
    so the chain verifies again (auto-recovery for a torn tail)."""
    import importlib
    ralph = importlib.import_module("ralph")
    from ralphcore import verify_chain

    with tempfile.TemporaryDirectory() as tmp:
        orig = _swap_state_dir(ralph, tmp)
        try:
            ralph.append_event({"event": "decide", "i": 1})
            ralph.append_event({"event": "decide", "i": 2})
            # simulate a torn final write: a partial, unparseable trailing line
            with open(ralph.EVENTS_PATH, "a", encoding="utf-8") as f:
                f.write('{"seq":2,"prev":"deadbeef","payl')   # no newline
            ralph._reset_writer_cache()
            ralph._boot_recover_events()
            entries = ralph.load_events()
            assert verify_chain(entries), "repaired chain must verify"
            assert len(entries) == 3, f"2 originals + repair, got {len(entries)}"
            assert entries[-1]["payload"]["event"] == "log_repair"
            assert entries[-1]["payload"]["dropped"] == 1
            # a subsequent append chains cleanly off the repaired tail
            e = ralph.append_event({"event": "decide", "i": 3})
            assert e["seq"] == 3
            assert verify_chain(ralph.load_events())
        finally:
            _restore_state_dir(ralph, orig)


def test_boot_refuses_tampered_log() -> None:
    """#58: a tamper (a well-formed entry whose payload was edited so its hash
    no longer matches) is NOT auto-healed — it raises EventLogTamper and the
    file is left untouched (the audit spine must stay intact)."""
    import importlib
    ralph = importlib.import_module("ralph")

    with tempfile.TemporaryDirectory() as tmp:
        orig = _swap_state_dir(ralph, tmp)
        try:
            ralph.append_event({"event": "decide", "i": 1})
            ralph.append_event({"event": "decide", "i": 2})
            ralph.append_event({"event": "decide", "i": 3})
            lines = open(ralph.EVENTS_PATH, encoding="utf-8").read().splitlines()
            mid = json.loads(lines[1])
            mid["payload"]["i"] = 999          # edits the canonical payload
            lines[1] = json.dumps(mid)
            with open(ralph.EVENTS_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            before = open(ralph.EVENTS_PATH, encoding="utf-8").read()
            ralph._reset_writer_cache()
            raised = False
            try:
                ralph._boot_recover_events()
            except ralph.EventLogTamper:
                raised = True
            assert raised, "tamper must raise EventLogTamper, not be healed"
            after = open(ralph.EVENTS_PATH, encoding="utf-8").read()
            assert before == after, "a tampered log must not be modified"
        finally:
            _restore_state_dir(ralph, orig)


def test_run_refuses_tampered_log_rc4() -> None:
    """#58 end-to-end: `ralph run` boot-verifies the chain and exits 4 on a
    tampered event log instead of chaining new entries onto it."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    from ralphcore import make_entry, GENESIS_HASH

    with tempfile.TemporaryDirectory() as tmp:
        events = os.path.join(tmp, "events.jsonl")
        e0 = make_entry(GENESIS_HASH, 0, {"event": "decide", "i": 1})
        e1 = make_entry(e0["hash"], 1, {"event": "decide", "i": 2})
        e0_bad = dict(e0)
        e0_bad["payload"] = {"event": "decide", "i": 999}   # hash now stale
        with open(events, "w", encoding="utf-8") as f:
            f.write(json.dumps(e0_bad) + "\n")
            f.write(json.dumps(e1) + "\n")
        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "run",
             "--budget-total", "5", "--max-ticks", "1", "--interval", "0",
             "--state-dir", tmp],
            capture_output=True, text=True, cwd=here, timeout=30)
        assert r.returncode == 4, f"expected rc=4, got {r.returncode}: {r.stderr}"
        assert "refusing to run" in r.stderr


def test_stage1_mission_preamble() -> None:
    from ralphcore import build_stage1_messages
    # no mission → system is just the stage-1 instruction
    plain = build_stage1_messages("crabcc", "STATE", [])
    assert "ratify" not in plain[0]["content"]
    # with mission → preamble prepended to system
    m = build_stage1_messages("crabcc", "STATE", [], mission="MISSION: ratify-rate is the metric.")
    assert m[0]["content"].startswith("MISSION: ratify-rate is the metric.")
    assert "candidates" in m[0]["content"]  # original instruction still present


def test_read_purpose_present() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    p = ralph.read_purpose()
    assert "ralph-loop" in p and "ratify" in p, "PURPOSE.md should be read"


# ---------------------------------------------------------------------------
# events subcommand — load_events, replay_events, cmd_events
# ---------------------------------------------------------------------------

def test_replay_events_fold() -> None:
    """replay_events folds a known chain into correct aggregate state."""
    import importlib
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")

    payloads = [
        {"tick": 0, "event": "decide", "repo": "a", "iteration": 1, "total_cost": 0.01},
        {"tick": 1, "event": "decide", "repo": "b", "iteration": 2, "total_cost": 0.03},
        {"tick": 2, "event": "paused"},
        {"tick": 3, "event": "decide", "repo": "a", "iteration": 3, "total_cost": 0.05},
    ]
    entries = []
    prev = GENESIS_HASH
    for i, p in enumerate(payloads):
        e = make_entry(prev, i, p)
        entries.append(e)
        prev = e["hash"]

    state = ralph.replay_events(entries)
    assert state["decisions"] == 3, f"decisions: {state['decisions']}"
    assert state["ticks"] == 4, f"ticks: {state['ticks']}"
    assert state["paused"] == 1, f"paused: {state['paused']}"
    assert abs(state["total_cost"] - 0.05) < 1e-9, f"total_cost: {state['total_cost']}"
    assert state["repos"]["a"]["decisions"] == 2, f"repos[a].decisions: {state['repos']['a']['decisions']}"
    assert state["repos"]["a"]["last_iteration"] == 3, f"repos[a].last_iteration: {state['repos']['a']['last_iteration']}"
    assert state["repos"]["b"]["decisions"] == 1, f"repos[b].decisions: {state['repos']['b']['decisions']}"


def test_replay_events_track_subjects() -> None:
    """Track-only decide events (keyed on `track`) populate the per-subject view."""
    import importlib
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")

    payloads = [
        {"event": "decide", "track": "graph-concept", "iteration": 1, "cost": 0.01, "total_cost": 0.01},
        {"event": "decide", "track": "hcp-litany", "iteration": 1, "cost": 0.02, "total_cost": 0.03},
        {"event": "decide", "track": "graph-concept", "iteration": 2, "cost": 0.02, "total_cost": 0.05},
    ]
    entries = []
    prev = GENESIS_HASH
    for i, p in enumerate(payloads):
        e = make_entry(prev, i, p)
        entries.append(e)
        prev = e["hash"]

    state = ralph.replay_events(entries)
    assert state["decisions"] == 3
    assert abs(state["total_cost"] - 0.05) < 1e-9, state["total_cost"]
    assert state["subjects"]["graph-concept"]["decisions"] == 2
    assert state["subjects"]["graph-concept"]["last_iteration"] == 2
    assert state["subjects"]["hcp-litany"]["decisions"] == 1
    assert state["repos"] is state["subjects"]   # back-compat alias


def test_events_verify_cli_ok_and_tamper() -> None:
    """ralph.py events --state-dir: rc=0 + 'chain OK' for valid chain; rc=1 + 'INVALID' for tampered."""
    import subprocess
    import tempfile
    from ralphcore import make_entry, GENESIS_HASH

    here = os.path.dirname(os.path.abspath(__file__))

    with tempfile.TemporaryDirectory() as tmpdir:
        # Build a valid chain of 3 entries and write events.jsonl
        events_path = os.path.join(tmpdir, "events.jsonl")
        payloads = [
            {"tick": 0, "event": "paused"},
            {"tick": 1, "event": "decide", "repo": "x", "iteration": 1, "total_cost": 0.01},
            {"tick": 2, "event": "paused"},
        ]
        entries = []
        prev = GENESIS_HASH
        for i, p in enumerate(payloads):
            e = make_entry(prev, i, p)
            entries.append(e)
            prev = e["hash"]
        with open(events_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "events", "--state-dir", tmpdir],
            capture_output=True, text=True, cwd=here, timeout=30,
        )
        assert r.returncode == 0, f"expected rc=0, got {r.returncode}; stderr={r.stderr}"
        assert "chain OK" in r.stdout, f"'chain OK' not in stdout: {r.stdout!r}"

        # Tamper: overwrite one line's payload with wrong data
        tampered_entry = dict(entries[1])
        tampered_entry = {**tampered_entry, "payload": {"tick": 1, "event": "decide", "repo": "EVIL", "iteration": 1, "total_cost": 999.0}}
        lines = []
        lines.append(json.dumps(entries[0]))
        lines.append(json.dumps(tampered_entry))
        lines.append(json.dumps(entries[2]))
        with open(events_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        r2 = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "events", "--state-dir", tmpdir],
            capture_output=True, text=True, cwd=here, timeout=30,
        )
        assert r2.returncode == 1, f"expected rc=1 for tampered chain, got {r2.returncode}"
        assert "INVALID" in r2.stdout, f"'INVALID' not in stdout: {r2.stdout!r}"


def test_events_replay_cli() -> None:
    """ralph.py events --replay --state-dir: rc=0, stdout is valid JSON with expected decisions count."""
    import subprocess
    import tempfile
    from ralphcore import make_entry, GENESIS_HASH

    here = os.path.dirname(os.path.abspath(__file__))

    with tempfile.TemporaryDirectory() as tmpdir:
        events_path = os.path.join(tmpdir, "events.jsonl")
        payloads = [
            {"tick": 0, "event": "decide", "repo": "r", "iteration": 1, "total_cost": 0.01},
            {"tick": 1, "event": "paused"},
            {"tick": 2, "event": "decide", "repo": "r", "iteration": 2, "total_cost": 0.02},
        ]
        prev = GENESIS_HASH
        with open(events_path, "w", encoding="utf-8") as f:
            for i, p in enumerate(payloads):
                e = make_entry(prev, i, p)
                f.write(json.dumps(e) + "\n")
                prev = e["hash"]

        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "events", "--replay", "--state-dir", tmpdir],
            capture_output=True, text=True, cwd=here, timeout=30,
        )
        assert r.returncode == 0, f"expected rc=0, got {r.returncode}; stderr={r.stderr}"
        parsed = json.loads(r.stdout)
        assert parsed["decisions"] == 2, f"decisions: {parsed['decisions']}"


# ---------------------------------------------------------------------------
# Phase 1 — tracks (config + pure core)
# ---------------------------------------------------------------------------

def test_load_tracks_parses_fields() -> None:
    from ralphcore import load_tracks

    cfg = {"tracks": [{"name": "t", "topic": "T", "model": "x/y",
                       "label": "track:t",
                       "context": {"docs": ["a/**"], "paths": ["a/"]}}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(cfg, fh)
        p = fh.name
    try:
        tracks = load_tracks(p)
        assert len(tracks) == 1, f"expected 1 track, got {len(tracks)}"
        t = tracks[0]
        assert t.name == "t" and t.model == "x/y" and t.label == "track:t"
        assert t.topic == "T"
        assert t.context.docs == ["a/**"] and t.context.paths == ["a/"]
    finally:
        os.unlink(p)


def test_next_track_advances_wraps_skips() -> None:
    from ralphcore import next_track

    names = ["a", "b", "c"]
    assert next_track(names, "a", set()) == "b"
    assert next_track(names, "c", set()) == "a"        # wrap
    assert next_track(names, None, set()) == "a"        # first run
    assert next_track(names, "a", {"b"}) == "c"         # skip unavailable
    assert next_track(names, "a", {"a", "b", "c"}) is None


def test_stage1_subject_keyed() -> None:
    from ralphcore import build_stage1_messages

    msgs = build_stage1_messages("the Vaked grammar", "STATE", ["Prior X"])
    blob = json.dumps(msgs)
    assert "the Vaked grammar" in blob, "subject missing"
    assert "Prior X" in blob and "candidates" in blob


def test_decide_dry_run_track_writes_nothing() -> None:
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("RALPH_API_KEY", None)
    r = subprocess.run(
        [sys.executable, os.path.join(here, "ralph.py"), "decide",
         "--track", "base-language-spec", "--dry-run"],
        capture_output=True, text=True, env=env, cwd=here, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "stage 1" in r.stdout.lower() and "estimate" in r.stdout.lower()
    # the track model should head the prompt banner
    assert "qwen/qwen3-235b-a22b-thinking-2507" in r.stdout


def test_decide_track_uses_track_model_both_stages() -> None:
    """_decide_track calls the model with track.model for BOTH stages."""
    import importlib
    import tempfile
    import unittest.mock as mock

    ralph = importlib.import_module("ralph")
    from ralphcore import Track, TrackContext

    track = Track(name="t", topic="topic T", model="vendor/m1",
                  label="track:t", context=TrackContext(docs=[], paths=[]))

    s1 = {"choices": [{"message": {"content":
          json.dumps({"candidates": [{"title": "X", "why_now": "n",
                                      "urgency": 5, "addressed": False}]})}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    s2 = {"choices": [{"message": {"content": "**Decision / question:** X"}}],
          "usage": {"prompt_tokens": 80, "completion_tokens": 40}}
    calls = iter([s1, s2])
    seen_models: list[str] = []

    def fake_call(model, *a, **kw):
        seen_models.append(model)
        return next(calls)

    args = types.SimpleNamespace(git_log_window=5, seed=42)

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = ralph.DECISIONS_DIR
        orig_ctx = ralph.gather_track_context
        orig_events = ralph.EVENTS_PATH
        orig_state = ralph.STATE_DIR
        ralph.DECISIONS_DIR = tmpdir
        ralph.gather_track_context = lambda tr, w, compact: "FAKE"
        ralph.EVENTS_PATH = os.path.join(tmpdir, "events.jsonl")
        ralph.STATE_DIR = tmpdir
        try:
            with mock.patch.dict(os.environ, {"RALPH_CRITIQUE": "off"}), \
                 mock.patch.object(ralph, "openrouter_call", side_effect=fake_call):
                cost = ralph._decide_track(args, track, "key")
            # the decide event must be logged so --next-track can rotate
            last = ralph._last_decided_track()
            # replay must reconstruct spend from the event's total_cost
            replayed = ralph.replay_events(ralph.load_events())
        finally:
            ralph.DECISIONS_DIR = orig_dir
            ralph.gather_track_context = orig_ctx
            ralph.EVENTS_PATH = orig_events
            ralph.STATE_DIR = orig_state

        assert seen_models == ["vendor/m1", "vendor/m1"], seen_models
        assert cost > 0.0
        assert last == "t", f"rotation pointer not recorded: {last}"
        assert abs(replayed["total_cost"] - cost) < 1e-9, replayed["total_cost"]
        log_path = os.path.join(tmpdir, "t.ralph-log.md")
        assert os.path.exists(log_path)
        content = open(log_path).read()
        assert "Decision #1" in content and "**Track:** t" in content


def test_track_issues_empty_scope_no_fallback() -> None:
    """A label with zero open issues stays scoped (no all-open fallback); only a
    gh failure (empty output) triggers the fallback."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")

    # labeled query returns an empty JSON array (success) → keep empty, no note
    with mock.patch.object(ralph, "_run", return_value="[]"):
        issues, note = ralph._track_issues("track:mlir")
    assert issues == [] and note == "", (issues, note)

    # gh failure (empty string) on the label query → fall back to all-open
    seq = iter(["", json.dumps([{"number": 1, "title": "X"}])])
    with mock.patch.object(ralph, "_run", side_effect=lambda *a, **k: next(seq)):
        issues, note = ralph._track_issues("track:mlir")
    assert len(issues) == 1 and "all open" in note, (issues, note)


def test_issues_for_labels_union_dedup() -> None:
    """The OR-union scope queries each label and unions by issue number: a
    deduped set, newest-first, with no all-open fallback while any label query
    succeeds."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")

    # `language` → #24, #10 ; `bug` → #25, #10 (overlap on #10) → union {24,25,10}
    per_label = {
        "language": json.dumps([{"number": 24, "title": "memory"},
                                {"number": 10, "title": "shared"}]),
        "bug": json.dumps([{"number": 25, "title": "name-collision"},
                           {"number": 10, "title": "shared"}]),
    }

    def fake_run(args, *a, **k):
        # the label value follows the "--label" flag in the gh argv
        lab = args[args.index("--label") + 1]
        return per_label[lab]

    with mock.patch.object(ralph, "_run", side_effect=fake_run):
        issues, note = ralph._issues_for_labels(["language", "bug"])
    nums = [i["number"] for i in issues]
    assert nums == [25, 24, 10], nums          # deduped + sorted newest-first
    assert note == "", note                    # scoped, no fallback

    # every label query fails (gh unusable) → fall back to all-open with a note
    seq = iter(["", "", json.dumps([{"number": 1, "title": "X"}])])
    with mock.patch.object(ralph, "_run", side_effect=lambda *a, **k: next(seq)):
        issues, note = ralph._issues_for_labels(["language", "bug"])
    assert [i["number"] for i in issues] == [1] and "all open" in note, (issues, note)


def test_load_tracks_issue_labels_default() -> None:
    """`issue_labels` is read from config; when omitted it defaults to [label]
    so older single-label configs keep scoping."""
    import importlib
    import tempfile
    import os
    ralphcore = importlib.import_module("ralphcore")
    cfg = {
        "tracks": [
            {"name": "a", "topic": "A", "model": "m", "label": "track:x",
             "issue_labels": ["language", "bug"], "context": {}},
            {"name": "b", "topic": "B", "model": "m", "label": "track:y",
             "context": {}},
        ]
    }
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tracks.json")
        with open(p, "w") as f:
            json.dump(cfg, f)
        tracks = ralphcore.load_tracks(p)
    by = {t.name: t for t in tracks}
    assert by["a"].issue_labels == ["language", "bug"], by["a"].issue_labels
    assert by["b"].issue_labels == ["track:y"], by["b"].issue_labels  # default to [label]


def test_track_skip_advances_rotation() -> None:
    """A track whose model returns no usable candidates still logs a skip event,
    so --next-track moves on instead of re-selecting the same failing track."""
    import importlib
    import tempfile
    import unittest.mock as mock

    ralph = importlib.import_module("ralph")
    from ralphcore import Track, TrackContext

    track = Track(name="flaky", topic="T", model="vendor/m",
                  label="track:flaky", context=TrackContext(docs=[], paths=[]))
    # stage-1 returns no usable candidates → _run_stages returns None (skip)
    degenerate = {"choices": [], "usage": {}}
    args = types.SimpleNamespace(git_log_window=5, seed=42)

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir, orig_ctx = ralph.DECISIONS_DIR, ralph.gather_track_context
        orig_events, orig_state = ralph.EVENTS_PATH, ralph.STATE_DIR
        ralph.DECISIONS_DIR = tmpdir
        ralph.gather_track_context = lambda tr, w, compact: "FAKE"
        ralph.EVENTS_PATH = os.path.join(tmpdir, "events.jsonl")
        ralph.STATE_DIR = tmpdir
        try:
            with mock.patch.object(ralph, "openrouter_call", return_value=degenerate):
                cost = ralph._decide_track(args, track, "key")
            last = ralph._last_decided_track()
            events = ralph.load_events()
        finally:
            ralph.DECISIONS_DIR, ralph.gather_track_context = orig_dir, orig_ctx
            ralph.EVENTS_PATH, ralph.STATE_DIR = orig_events, orig_state

        assert cost == 0.0
        assert last == "flaky", f"skip must advance rotation pointer: {last}"
        assert events[-1]["payload"]["event"] == "skip"
        # no decision log written on a skip
        assert not os.path.exists(os.path.join(tmpdir, "flaky.ralph-log.md"))


def test_supervised_decide_track_folds_cost() -> None:
    """_supervised_decide_track folds the iteration cost + model into status."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    from ralphcore import Track, TrackContext

    track = Track(name="t", topic="T", model="vendor/m", label="track:t",
                  context=TrackContext(docs=[], paths=[]))
    status = {"total_cost": 0.0, "subjects": {}, "recent": []}
    args = types.SimpleNamespace()

    with mock.patch.object(ralph, "_resolve_api_key", return_value="k"), \
         mock.patch.object(ralph, "_decide_track", return_value=0.25), \
         mock.patch.object(ralph, "_prior_titles", return_value=[]):
        ralph._supervised_decide_track(args, track, status)

    assert abs(status["total_cost"] - 0.25) < 1e-9
    assert status["subjects"]["t"]["model"] == "vendor/m"
    assert abs(status["subjects"]["t"]["cost"] - 0.25) < 1e-9


def test_render_dashboard_tracks_model_column() -> None:
    """Track status renders a model column and uses the 'track' label."""
    from ralphcore import render_dashboard
    status = {
        "running": True, "current": "graph-concept", "iteration": 2,
        "total_cost": 0.01, "budget_total": 2.0,
        "subjects": {"graph-concept": {"entries": 1, "last_title": "LPG split",
                                       "cost": 0.01,
                                       "model": "deepseek/deepseek-v4-flash"}},
        "recent": [{"subject": "graph-concept", "date": "2026-06-12", "title": "LPG split"}],
    }
    out = render_dashboard(status, 100, 100)
    assert "track" in out and "graph-concept" in out
    assert "deepseek/deepseek-v4-flash" in out and "LPG split" in out


def test_run_tracks_budget_zero_no_iterations() -> None:
    """`run` (default = tracks) with budget 0 makes no API call and exits clean."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "ralph.py"), "run",
                        "--budget-total", "0", "--max-iters", "1"],
                       capture_output=True, text=True, cwd=here, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "budget" in (r.stdout + r.stderr).lower()


def test_run_tracks_seeds_total_cost_from_ledger() -> None:
    """A fresh status.json must seed cumulative spend from the committed event
    ledger, so a stateless restart respects the budget already spent."""
    import subprocess
    from ralphcore import make_entry, GENESIS_HASH
    here = os.path.dirname(os.path.abspath(__file__))

    with tempfile.TemporaryDirectory() as tmpdir:
        # ledger already records $0.50 of spend on a track decide
        e = make_entry(GENESIS_HASH, 0,
                       {"event": "decide", "track": "graph-concept",
                        "iteration": 1, "cost": 0.5, "total_cost": 0.5})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        # budget below recorded spend → must stop immediately, no API call
        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "run",
             "--budget-total", "0.10", "--state-dir", tmpdir, "--max-iters", "1"],
            capture_output=True, text=True, cwd=here, timeout=30)
        assert r.returncode == 0, r.stderr
        assert "budget" in (r.stdout + r.stderr).lower(), r.stdout


def test_run_tracks_reconciles_stale_status() -> None:
    """When status.json is stale-low but the ledger records more spend, the
    budget check must use the ledger total (reconciled on start), not the cache."""
    import subprocess
    from ralphcore import make_entry, GENESIS_HASH
    here = os.path.dirname(os.path.abspath(__file__))

    with tempfile.TemporaryDirectory() as tmpdir:
        # stale cache says $0 spent...
        with open(os.path.join(tmpdir, "status.json"), "w", encoding="utf-8") as f:
            json.dump({"running": False, "current": None, "total_cost": 0.0,
                       "budget_total": 2.0, "subjects": {}, "recent": [],
                       "last_step_epoch": 0}, f)
        # ...but the ledger records $0.50
        e = make_entry(GENESIS_HASH, 0,
                       {"event": "decide", "track": "graph-concept",
                        "iteration": 1, "cost": 0.5, "total_cost": 0.5})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "run",
             "--budget-total", "0.10", "--state-dir", tmpdir, "--max-iters", "1"],
            capture_output=True, text=True, cwd=here, timeout=30)
        assert r.returncode == 0, r.stderr
        assert "budget" in (r.stdout + r.stderr).lower(), r.stdout


def test_run_tracks_max_ticks_stops_promptly() -> None:
    """`run --max-ticks 1` with a long interval must NOT sleep the interval after
    the final tick (it should exit promptly). No API key → decide is a no-op."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("RALPH_API_KEY", None)
    with tempfile.TemporaryDirectory() as tmpdir:
        # timeout well under the 900s interval: if the fix regresses, this hangs
        r = subprocess.run(
            [sys.executable, os.path.join(here, "ralph.py"), "run",
             "--max-ticks", "1", "--interval", "900", "--budget-total", "5",
             "--state-dir", tmpdir],
            capture_output=True, text=True, cwd=here, env=env, timeout=20)
        assert r.returncode == 0, r.stderr


def test_clear_step_resets_flag() -> None:
    """_clear_step turns off the one-shot step flag, leaving paused intact."""
    import importlib
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        orig = ralph.CONTROL_PATH
        ralph.CONTROL_PATH = os.path.join(tmpdir, "control.json")
        try:
            with open(ralph.CONTROL_PATH, "w") as f:
                json.dump({"paused": True, "step": True, "interval": 5}, f)
            ralph._clear_step()
            with open(ralph.CONTROL_PATH) as f:
                d = json.load(f)
        finally:
            ralph.CONTROL_PATH = orig
        assert d["step"] is False
        assert d["paused"] is True and d["interval"] == 5


def test_langfuse_disabled_without_config() -> None:
    """The loop's Langfuse layer is a no-op unless LANGFUSE_PUBLIC_KEY is set —
    the zero-dep / zero-config invariant. _flush_langfuse must never raise."""
    import importlib
    ralph = importlib.import_module("ralph")
    orig = os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
    ralph._LF_INIT = False
    ralph._LF_CLIENT = None
    try:
        assert ralph._langfuse() is None
        ralph._flush_langfuse()              # must be a safe no-op
        # _trace_generation with no span is also a no-op
        ralph._trace_generation(None, "x/y", {"usage": {}}, {"track": "t"}, 0.1)
    finally:
        ralph._LF_INIT = False
        ralph._LF_CLIENT = None
        if orig is not None:
            os.environ["LANGFUSE_PUBLIC_KEY"] = orig


def test_parse_ratify_line() -> None:
    from ralphcore import parse_ratify_line
    r = parse_ratify_line(
        "- graph-concept#3 — **override** — wrong layering — @pl 2026-06-12")
    assert r == {"id": "graph-concept#3", "verdict": "override",
                 "reason": "wrong layering", "score": 0}, r
    # ratify → score 1
    r2 = parse_ratify_line("- hcp-litany#1 — **ratify** — sound — @x 2026-06-12")
    assert r2["score"] == 1 and r2["verdict"] == "ratify"
    # defer → score 0
    assert parse_ratify_line("- a#2 — **defer** — later — @x 2026-06-12")["score"] == 0
    # malformed / non-ratify lines → None
    assert parse_ratify_line("not a ratify line") is None
    assert parse_ratify_line("- a#2 — **maybe** — x — @x 2026-06-12") is None


def test_ratify_rate() -> None:
    from ralphcore import ratify_rate
    # defer excluded from the denominator
    assert ratify_rate(["ratify", "ratify", "override", "defer"]) == 2 / 3
    assert ratify_rate(["ratify", "ratify"]) == 1.0
    assert ratify_rate([]) is None
    assert ratify_rate(["defer", "defer"]) is None   # nothing acted


def test_build_stage1_injects_overrides() -> None:
    from ralphcore import build_stage1_messages
    msgs = build_stage1_messages("the graph", "STATE", ["Prior X"],
                                 overrides=["graph#1: wrong layer"])
    user = msgs[1]["content"]
    assert "Human overrides" in user and "graph#1: wrong layer" in user
    # without overrides the section is absent (backward compatible)
    plain = build_stage1_messages("the graph", "STATE", ["Prior X"])
    assert "Human overrides" not in plain[1]["content"]


def test_recent_overrides_reads_log() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        try:
            with open(os.path.join(tmpdir, "graph-concept.ratify-log.md"), "w",
                      encoding="utf-8") as f:
                f.write("# header\n")
                f.write("- graph-concept#1 — **ratify** — good — @x 2026-06-12\n")
                f.write("- graph-concept#2 — **override** — wrong layer — @x 2026-06-12\n")
            overrides = ralph._recent_overrides("graph-concept")
        finally:
            ralph.DECISIONS_DIR = orig
        assert overrides == ["graph-concept#2: wrong layer"], overrides


def test_cmd_ratify_summary() -> None:
    """`ralph ratify` prints a per-track summary + overall ratify-rate."""
    import importlib
    ralph = importlib.import_module("ralph")
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as tmpdir:
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        try:
            # one decision + a ratify verdict for a real track name
            with open(os.path.join(tmpdir, "graph-concept.ralph-log.md"), "w",
                      encoding="utf-8") as f:
                f.write("## 2026-06-12 — Decision #1: Split the LPG\nbody\n")
            with open(os.path.join(tmpdir, "graph-concept.ratify-log.md"), "w",
                      encoding="utf-8") as f:
                f.write("- graph-concept#1 — **ratify** — sound — @x 2026-06-12\n")
            args = types.SimpleNamespace(tracks=os.path.join(here, "tracks.json"))
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ralph.cmd_ratify(args)
            out = buf.getvalue()
        finally:
            ralph.DECISIONS_DIR = orig
        assert rc == 0
        assert "graph-concept" in out and "ratify-rate" in out
        assert "100%" in out   # 1 ratify / (1 ratify + 0 override)


def test_generate_toot_fallback_limit_and_hashtags() -> None:
    """Without an API key, the toot uses the deterministic fallback, always
    carries hashtags, and is <= MASTODON_MAX_CHARS even for a long title."""
    import importlib
    ralph = importlib.import_module("ralph")
    long_title = "Adopt " + "Zoekt " * 200  # way over the limit
    toot = ralph._generate_toot("graph-concept", 7, long_title, "deepseek/x",
                                0.004, api_key="", base_url=None)
    assert len(toot) <= ralph.MASTODON_MAX_CHARS, len(toot)
    assert toot.rstrip().endswith("#graphconcept")
    assert "#vaked" in toot and "#ralph" in toot


def test_generate_toot_uses_gpt_oss_model() -> None:
    """With a key, the generator calls the gpt-oss model and wraps its body."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    seen = {}

    def fake_call(model, messages, **kw):
        seen["model"] = model
        return {"choices": [{"message": {"content": "graph split good. ship it."}}],
                "usage": {}}

    with mock.patch.object(ralph, "openrouter_call", side_effect=fake_call):
        toot = ralph._generate_toot("graph-concept", 3, "Split LPG", "deepseek/x",
                                    0.004, api_key="k", base_url=None)
    assert seen["model"] == ralph.ANNOUNCE_MODEL
    assert "graph split good" in toot and "#graphconcept" in toot
    assert len(toot) <= ralph.MASTODON_MAX_CHARS


def test_cmd_announce_noop_without_token() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    orig = os.environ.pop("MASTODON_ACCESS_TOKEN", None)
    try:
        args = types.SimpleNamespace(state_dir=None,
                                     tracks=os.path.join(os.path.dirname(
                                         os.path.abspath(__file__)), "tracks.json"))
        assert ralph.cmd_announce(args) == 0
    finally:
        if orig is not None:
            os.environ["MASTODON_ACCESS_TOKEN"] = orig


def _announce_args(tmpdir):
    here = os.path.dirname(os.path.abspath(__file__))
    return types.SimpleNamespace(state_dir=tmpdir, base_url=None,
                                 tracks=os.path.join(here, "tracks.json"))


def test_cmd_announce_posts_and_logs_event() -> None:
    """A fresh decision → generate + post + an `announced` event appended."""
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")

    with tempfile.TemporaryDirectory() as tmpdir:
        e = make_entry(GENESIS_HASH, 0, {"event": "decide", "track": "graph-concept",
                                         "iteration": 1, "cost": 0.01, "total_cost": 0.01})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        orig_dec = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        with open(os.path.join(tmpdir, "graph-concept.ralph-log.md"), "w",
                  encoding="utf-8") as f:
            f.write("## 2026-06-13 — Decision #1: Split the LPG\nbody\n")
        try:
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_TOOT_IMAGE": "off"}), \
                 mock.patch.object(ralph, "_generate_toot", return_value="toot #ralph"), \
                 mock.patch.object(ralph, "_run", return_value="[]"), \
                 mock.patch.object(ralph, "_post_toot",
                                   return_value={"id": "99", "url": "https://m/99"}):
                rc = ralph.cmd_announce(_announce_args(tmpdir))
            events = ralph.load_events()
        finally:
            ralph.DECISIONS_DIR = orig_dec
        assert rc == 0
        assert any(e["payload"].get("event") == "announced"
                   and e["payload"].get("id") == "graph-concept#1" for e in events)


def test_cmd_announce_dry_run_does_not_post() -> None:
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        e = make_entry(GENESIS_HASH, 0, {"event": "decide", "track": "graph-concept",
                                         "iteration": 1, "cost": 0.01, "total_cost": 0.01})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        args = _announce_args(tmpdir)
        args.dry_run = True
        orig_dec = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        try:
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_TOOT_IMAGE": "off"}), \
                 mock.patch.object(ralph, "_generate_toot", return_value="toot #ralph"), \
                 mock.patch.object(ralph, "_post_toot") as post:
                rc = ralph.cmd_announce(args)
        finally:
            ralph.DECISIONS_DIR = orig_dec
        assert rc == 0
        post.assert_not_called()


def test_cmd_announce_dedup_skips_when_already_announced() -> None:
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        prev = GENESIS_HASH
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            for i, p in enumerate([
                {"event": "decide", "track": "graph-concept", "iteration": 1,
                 "cost": 0.01, "total_cost": 0.01},
                {"event": "announced", "id": "graph-concept#1", "track": "graph-concept",
                 "iteration": 1, "status_id": "1"}]):
                en = make_entry(prev, i, p)
                f.write(json.dumps(en) + "\n")
                prev = en["hash"]
        with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_TOOT_IMAGE": "off"}), \
             mock.patch.object(ralph, "_post_toot") as post:
            rc = ralph.cmd_announce(_announce_args(tmpdir))
        assert rc == 0
        post.assert_not_called()


def test_cmd_announce_failure_reports_and_opens_issue() -> None:
    """A post failure → exit 1 and a (deduped) `gh issue create` attempt."""
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        e = make_entry(GENESIS_HASH, 0, {"event": "decide", "track": "graph-concept",
                                         "iteration": 1, "cost": 0.01, "total_cost": 0.01})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        gh_calls = []

        def fake_run(cmd, cwd=None, timeout=30):
            gh_calls.append(cmd)
            return "[]" if "list" in cmd else ""   # no existing issue → create

        with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_TOOT_IMAGE": "off"}), \
             mock.patch.object(ralph, "_generate_toot", return_value="toot #ralph"), \
             mock.patch.object(ralph, "_post_toot", side_effect=RuntimeError("503")), \
             mock.patch.object(ralph, "_run", side_effect=fake_run):
            rc = ralph.cmd_announce(_announce_args(tmpdir))
        assert rc == 1
        assert any("create" in c for c in gh_calls), gh_calls


def test_generate_toot_has_id_and_link() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    toot = ralph._generate_toot("graph-concept", 7, "Adopt Zoekt", "deepseek/x",
                                0.0, api_key="", base_url=None)
    assert "[graph-concept#7]" in toot
    assert "docs/decisions/graph-concept.ralph-log.md" in toot
    assert len(toot) <= ralph.MASTODON_MAX_CHARS


def test_strip_md_and_clean_title() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    assert ralph._strip_md("**bold** `code`") == "bold code"
    assert "#" not in ralph._strip_md("# Heading\ntext").split("\n")[0]
    # inline # (issue refs / would-be hashtags) is preserved
    assert "#17" in ralph._strip_md("land Epic #17 now")
    assert ralph._clean_title(
        "Decision / question: **Epic #17 sequencing**") == "Epic #17 sequencing"


def test_generate_toot_strips_markdown() -> None:
    """A markdown-laden title/body never leaks `**` into the toot."""
    import importlib
    ralph = importlib.import_module("ralph")
    md_title = "Decision / question: **Adopt `Zoekt` for search**"
    # fallback path
    toot = ralph._generate_toot("graph-concept", 1, md_title, "x", 0.0,
                                api_key="", base_url=None)
    assert "**" not in toot and "`" not in toot
    assert "Decision / question" not in toot
    assert len(toot) <= ralph.MASTODON_MAX_CHARS

    # model-content path: markdown in the gpt-oss output is also stripped
    import unittest.mock as mock
    resp = {"choices": [{"message": {"content": "**graph** split `now`. ship it."}}]}
    with mock.patch.object(ralph, "openrouter_call", return_value=resp):
        toot2 = ralph._generate_toot("graph-concept", 1, md_title, "x", 0.0,
                                     api_key="k", base_url=None)
    assert "**" not in toot2 and "`" not in toot2
    assert "graph split now" in toot2 and len(toot2) <= ralph.MASTODON_MAX_CHARS


def test_parse_json_obj_tolerant() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    obj = '{"recap": "hi", "rnd": ["a", "b"]}'
    assert ralph._parse_json_obj(obj) == {"recap": "hi", "rnd": ["a", "b"]}
    assert ralph._parse_json_obj("```json\n" + obj + "\n```") == {"recap": "hi", "rnd": ["a", "b"]}
    assert ralph._parse_json_obj("prose " + obj + " more")["recap"] == "hi"
    assert ralph._parse_json_obj("no json") == {}
    assert ralph._parse_json_obj(None) == {}


def test_is_sensitive() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    assert ralph._is_sensitive("must rotate the secret key")
    assert ralph._is_sensitive("an RCE in the parser")
    assert ralph._is_sensitive("Recommendation: ...\n- **Confidence:** low")
    assert not ralph._is_sensitive("Adopt Zoekt. Confidence: high")
    assert not ralph._is_sensitive("")
    # ReDoS guard: a long whitespace run after "confidence" must resolve fast
    import time as _t
    t0 = _t.time()
    assert not ralph._is_sensitive("confidence" + " " * 60000)
    assert _t.time() - t0 < 1.0, "ReDoS: _is_sensitive too slow"


def test_post_toot_language_and_spoiler() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def fake(req, timeout=None):
        captured["body"] = req.data.decode()
        return _Resp()

    with mock.patch.object(ralph.urllib.request, "urlopen", side_effect=fake):
        ralph._post_toot("https://m", "tok", "hi", "unlisted", "x",
                         spoiler_text="cw")
    assert "language=en" in captured["body"]
    assert "spoiler_text=cw" in captured["body"]


def test_post_toot_retries_on_429() -> None:
    """A 429 is retried (honoring the wait) up to 3 times, then succeeds."""
    import importlib
    import unittest.mock as mock
    import urllib.error
    ralph = importlib.import_module("ralph")

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"id":"1"}'

    err = urllib.error.HTTPError("u", 429, "Too Many", {"Retry-After": "0"}, None)
    seq = [err, err, _Resp()]
    state = {"i": 0}

    def fake(req, timeout=None):
        v = seq[state["i"]]
        state["i"] += 1
        if isinstance(v, Exception):
            raise v
        return v

    with mock.patch.object(ralph.urllib.request, "urlopen", side_effect=fake), \
         mock.patch.object(ralph.time, "sleep"):
        out = ralph._post_toot("https://m", "tok", "hi", "unlisted", "x")
    assert out == {"id": "1"} and state["i"] == 3


def test_post_toot_no_retry_on_4xx() -> None:
    """A 4xx (bad request/auth) is NOT retried — raised immediately."""
    import importlib
    import unittest.mock as mock
    import urllib.error
    ralph = importlib.import_module("ralph")
    err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    state = {"i": 0}

    def fake(req, timeout=None):
        state["i"] += 1
        raise err

    with mock.patch.object(ralph.urllib.request, "urlopen", side_effect=fake), \
         mock.patch.object(ralph.time, "sleep"):
        try:
            ralph._post_toot("https://m", "tok", "hi", "unlisted", "x")
            assert False, "should have raised"
        except urllib.error.HTTPError:
            pass
    assert state["i"] == 1


def test_cmd_announce_retry_older_unannounced() -> None:
    """Two un-announced decisions → the OLDER one is announced first (retry)."""
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        prev = GENESIS_HASH
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            for i, n in enumerate((1, 2)):
                e = make_entry(prev, i, {"event": "decide", "track": "graph-concept",
                                         "iteration": n, "cost": 0.01, "total_cost": 0.01})
                f.write(json.dumps(e) + "\n")
                prev = e["hash"]
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        try:
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_TOOT_IMAGE": "off"}), \
                 mock.patch.object(ralph, "_generate_toot", return_value="t #ralph"), \
                 mock.patch.object(ralph, "_run", return_value="[]"), \
                 mock.patch.object(ralph, "_post_toot", return_value={"id": "1"}):
                rc = ralph.cmd_announce(_announce_args(tmpdir))
            events = ralph.load_events()
        finally:
            ralph.DECISIONS_DIR = orig
        assert rc == 0
        announced = [e["payload"]["id"] for e in events
                     if e["payload"].get("event") == "announced"]
        assert announced == ["graph-concept#1"], announced   # older first


def test_cmd_announce_spoiler_for_sensitive_decision() -> None:
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        e = make_entry(GENESIS_HASH, 0, {"event": "decide", "track": "graph-concept",
                                         "iteration": 1, "cost": 0.01, "total_cost": 0.01})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        with open(os.path.join(tmpdir, "graph-concept.ralph-log.md"), "w",
                  encoding="utf-8") as f:
            f.write("## 2026-06-13 — Decision #1: Rotate the secret key\n"
                    "- **Recommendation:** rotate now\n")
        captured = {}

        def fake_post(host, token, text, vis, did, **kw):
            captured.update(kw)
            return {"id": "1"}

        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        try:
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_TOOT_IMAGE": "off"}), \
                 mock.patch.object(ralph, "_generate_toot", return_value="t #ralph"), \
                 mock.patch.object(ralph, "_run", return_value="[]"), \
                 mock.patch.object(ralph, "_post_toot", side_effect=fake_post):
                ralph.cmd_announce(_announce_args(tmpdir))
        finally:
            ralph.DECISIONS_DIR = orig
        assert captured.get("spoiler_text"), captured


def test_cmd_digest_self_gates_per_day() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as tmpdir:
        args = types.SimpleNamespace(state_dir=tmpdir, base_url=None,
                                     tracks=os.path.join(here, "tracks.json"))
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        try:
            # RALPH_DIGEST_HOUR=0 bypasses the end-of-day hour gate in tests
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "RALPH_DIGEST_HOUR": "0"}), \
                 mock.patch.object(ralph, "_post_toot", return_value={"id": "d1"}) as post:
                rc1 = ralph.cmd_digest(args)
                rc2 = ralph.cmd_digest(args)   # same day → must skip
        finally:
            ralph.DECISIONS_DIR = orig
        assert rc1 == 0 and rc2 == 0
        assert post.call_count == 1, post.call_count
        assert any(e["payload"].get("event") == "digest" for e in ralph.load_events())


def test_mastodon_len_counts_urls_as_23() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    url = "https://arxiv.org/search/?searchtype=all&query=effect+systems+in+pl"
    assert len(url) > 23
    assert ralph._mastodon_len("abc " + url) == len("abc ") + 23


def test_cmd_digest_recap_has_rnd_links() -> None:
    """The recap toot carries 3 R&D arXiv links + #recap and fits Mastodon."""
    import importlib
    import io
    import contextlib
    ralph = importlib.import_module("ralph")
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as tmpdir:
        args = types.SimpleNamespace(state_dir=tmpdir, base_url=None, dry_run=True,
                                     tracks=os.path.join(here, "tracks.json"))
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = ralph.cmd_digest(args)   # dry-run, no key → fallback recap
        finally:
            ralph.DECISIONS_DIR = orig
        out = buf.getvalue()
        assert rc == 0
        assert out.count("https://arxiv.org/search") == 3
        assert "#recap" in out


def test_cmd_digest_oversized_rnd_fits_budget() -> None:
    """Pathologically long gpt-oss R&D topics must not push the toot over 470."""
    import importlib
    import io
    import contextlib
    import re as _re
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    here = os.path.dirname(os.path.abspath(__file__))
    huge = ["x" * 300, "y" * 300, "z" * 300]
    with tempfile.TemporaryDirectory() as tmpdir:
        args = types.SimpleNamespace(state_dir=tmpdir, base_url=None, dry_run=True,
                                     tracks=os.path.join(here, "tracks.json"))
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        buf = io.StringIO()
        try:
            with mock.patch.object(ralph, "_generate_recap",
                                   return_value=("a" * 400, huge)), \
                 contextlib.redirect_stdout(buf):
                ralph.cmd_digest(args)
        finally:
            ralph.DECISIONS_DIR = orig
        # the printed body line: "[digest] body |<toot>|"
        m = _re.search(r"\[digest\] body \|(.*)\|", buf.getvalue(), _re.S)
        assert m, buf.getvalue()
        assert ralph._mastodon_len(m.group(1)) <= ralph.MASTODON_MAX_CHARS


def test_parse_candidates_tolerant() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    raw = '{"candidates": [{"title": "A", "urgency": 5}]}'
    fenced = "```json\n" + raw + "\n```"
    prose = "Sure, here are the candidates:\n" + raw + "\nHope that helps!"
    want = [{"title": "A", "urgency": 5}]
    for t in (raw, fenced, prose):
        assert ralph._parse_candidates(t) == want, t
    assert ralph._parse_candidates("no json here") == []
    assert ralph._parse_candidates(None) == []
    assert ralph._parse_candidates("") == []


def test_run_stages_falls_back_to_reasoning() -> None:
    """A thinking model with content=null but JSON in `reasoning` still yields
    candidates (no skip)."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    s1 = {"choices": [{"message": {"content": None, "reasoning":
            'thinking… ```json\n{"candidates":[{"title":"X","why_now":"n",'
            '"urgency":5,"addressed":false}]}\n```'},
            "finish_reason": "stop"}], "usage": {}}
    s2 = {"choices": [{"message": {"content": "**Decision / question:** X"}}],
          "usage": {}}
    calls = iter([s1, s2])
    with mock.patch.dict(os.environ, {"RALPH_CRITIQUE": "off"}), \
         mock.patch.object(ralph, "openrouter_call",
                           side_effect=lambda *a, **k: next(calls)):
        res = ralph._run_stages("subj", [{"role": "user", "content": "x"}],
                                lambda: "CTX", "m1", "m2", "key", None, 42)
    assert res is not None
    _, body, writer_used = res
    assert "Decision" in body
    assert writer_used == "m2"          # no override → the (track) stage-2 model


def test_run_stages_critique_and_writer_override() -> None:
    """RALPH_WRITER_MODEL drives stage-2 + stage-3; critique rewrite replaces the
    draft; cost sums all three calls."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    s1 = {"choices": [{"message": {"content":
            '{"candidates":[{"title":"X","why_now":"n","urgency":5,"addressed":false}]}'}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    s2 = {"choices": [{"message": {"content":
            "**Decision / question:** draft\n**Recommendation:** A\n**Next actions:** open PR"}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    s3 = {"choices": [{"message": {"content":
            "**Decision / question:** improved & grounded entry per docs/0011\n"
            "**Recommendation:** A\n**Next actions:** open PR #9"}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    seen = []

    def fake(model, *a, **k):
        seen.append(model)
        return {0: s1, 1: s2, 2: s3}[len(seen) - 1]

    with mock.patch.dict(os.environ, {"RALPH_WRITER_MODEL": "vendor/writer",
                                      "RALPH_CRITIQUE": "on"}), \
         mock.patch.object(ralph, "openrouter_call", side_effect=fake):
        res = ralph._run_stages("subj", [{"role": "user", "content": "x"}],
                                lambda: "CTX", "m1/rank", "m2/track", "key", None, 42)
    assert res is not None
    cost, body, writer_used = res
    assert seen == ["m1/rank", "vendor/writer", "vendor/writer"], seen   # stage1 rank, then writer x2
    assert "improved" in body and "draft" not in body                    # critique rewrite won
    assert writer_used == "vendor/writer"                                # label reflects the writer
    assert cost > 0


def test_run_stages_critique_failure_keeps_draft() -> None:
    """A critique-call failure (after a usable stage-2 draft) must NOT abort the
    tick — it keeps the stage-2 body and still returns the stage-1+2 cost."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    s1 = {"choices": [{"message": {"content":
            '{"candidates":[{"title":"X","why_now":"n","urgency":5,"addressed":false}]}'}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    s2 = {"choices": [{"message": {"content": "**Decision / question:** the stage-2 draft body"}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    calls = {"n": 0}

    def fake(model, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return s1
        if calls["n"] == 2:
            return s2
        raise RuntimeError("transient 5xx during critique")

    # No RALPH_WRITER_MODEL → writer == track model, so the critique call has no
    # fallback net and raises straight out of _writer_call.
    with mock.patch.dict(os.environ, {"RALPH_CRITIQUE": "on"}, clear=False), \
         mock.patch.object(ralph, "openrouter_call", side_effect=fake):
        os.environ.pop("RALPH_WRITER_MODEL", None)
        res = ralph._run_stages("subj", [{"role": "user", "content": "x"}],
                                lambda: "CTX", "m1/rank", "m2/track", "key", None, 42)
    assert res is not None, "critique failure must not abort the decision"
    cost, body, writer_used = res
    assert "stage-2 draft" in body              # kept the draft
    assert calls["n"] == 3                       # stage1, stage2, then the failing critique
    assert writer_used == "m2/track"            # fell back to the track stage-2 model
    assert cost > 0


def test_looks_like_entry_accepts_real_entry_rejects_notes() -> None:
    from ralphcore import looks_like_entry
    good = ("**Decision / question:** Prioritize hcpbin\n"
            "**Options:** A, B\n**Recommendation:** A per RFC 0002 §6\n"
            "**Risks:** edge cases\n**Next actions:** open PR\n**Confidence:** high")
    assert looks_like_entry(good) is True
    assert looks_like_entry("## Decision / question\nfoo\nRecommendation: A\nNext actions: PR") is True
    # The real leak from the live run — review notes, not an entry.
    notes = ("We need to improve the draft strategic decision entry. Let's first "
             "identify the issues:\n- The draft claims... We'll keep. "
             "Recommendation: Option A. Next actions: open a PR.")
    assert looks_like_entry(notes) is False        # leads with "We need to"
    assert looks_like_entry("") is False
    assert looks_like_entry("**Decision:** stub") is False   # missing structure


def test_run_stages_critique_notes_keep_draft() -> None:
    """If stage-3 returns review NOTES instead of a rewritten entry, the clean
    stage-2 draft is kept (the live-run regression)."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    s1 = {"choices": [{"message": {"content":
            '{"candidates":[{"title":"X","why_now":"n","urgency":5,"addressed":false}]}'}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    s2 = {"choices": [{"message": {"content":
            "**Decision / question:** ship hcpbin\n**Recommendation:** A\n**Next actions:** PR"}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    s3 = {"choices": [{"message": {"content":
            "We need to improve the draft. Let's identify issues: the Recommendation "
            "and Next actions could be sharper. We'll keep option A."}}],
          "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
    calls = iter([s1, s2, s3])
    with mock.patch.dict(os.environ, {"RALPH_CRITIQUE": "on"}, clear=False), \
         mock.patch.object(ralph, "openrouter_call", side_effect=lambda *a, **k: next(calls)):
        os.environ.pop("RALPH_WRITER_MODEL", None)
        res = ralph._run_stages("subj", [{"role": "user", "content": "x"}],
                                lambda: "CTX", "m1", "m2", "key", None, 42)
    assert res is not None
    cost, body, _ = res
    assert "ship hcpbin" in body and "We need to improve" not in body   # kept the draft
    assert cost > 0                                                     # s3 still billed


def test_run_stages_critique_truncates_long_context() -> None:
    """The critique pass caps the grounding context it sends (cost control)."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    s1 = {"choices": [{"message": {"content":
            '{"candidates":[{"title":"X","why_now":"n","urgency":5,"addressed":false}]}'}}],
          "usage": {}}
    s2 = {"choices": [{"message": {"content":
            "**Decision / question:** d\n**Recommendation:** A\n**Next actions:** PR"}}], "usage": {}}
    s3 = {"choices": [{"message": {"content":
            "**Decision / question:** d2\n**Recommendation:** A\n**Next actions:** PR #1"}}], "usage": {}}
    calls = iter([s1, s2, s3])
    seen_user = []

    def fake(model, messages, *a, **k):
        if any("Grounding context" in m.get("content", "") for m in messages):
            seen_user.append(messages[-1]["content"])
        return next(calls)

    big = "Z" * (ralph.CRITIQUE_CONTEXT_CHARS + 5000)
    with mock.patch.dict(os.environ, {"RALPH_CRITIQUE": "on"}, clear=False), \
         mock.patch.object(ralph, "openrouter_call", side_effect=fake):
        os.environ.pop("RALPH_WRITER_MODEL", None)
        ralph._run_stages("subj", [{"role": "user", "content": "x"}],
                          lambda: big, "m1", "m2", "key", None, 42)
    assert seen_user, "critique user message not seen"
    assert "[context truncated for critique]" in seen_user[0]
    assert len(seen_user[0]) < len(big)


def test_writer_call_falls_back_to_track_model() -> None:
    """A failing writer model degrades to the track model (no crash)."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    ok = {"choices": [{"message": {"content": "ok"}}], "usage": {}}

    def fake(model, *a, **k):
        if model == "bad/writer":
            raise RuntimeError("no such model")
        return ok

    with mock.patch.object(ralph, "openrouter_call", side_effect=fake):
        resp, used = ralph._writer_call("bad/writer", "good/track",
                                        [{"role": "user", "content": "x"}],
                                        api_key="k", base_url=None,
                                        temperature=0.3, max_tokens=100,
                                        span_name="x", span_meta={})
    assert used == "good/track" and ralph._message_content(resp) == "ok"


def test_every_track_model_has_price() -> None:
    from ralphcore import load_tracks, FALLBACK_PRICES, Price

    here = os.path.dirname(os.path.abspath(__file__))
    tracks = load_tracks(os.path.join(here, "tracks.json"))
    assert tracks, "tracks.json should define at least one track"
    for t in tracks:
        price = FALLBACK_PRICES.get(t.model)
        assert isinstance(price, Price), f"add a FALLBACK_PRICES entry for {t.model}"


# ---------------------------------------------------------------------------
# Toot image (OpenRouter image gen → Mastodon media)
# ---------------------------------------------------------------------------


def test_toot_image_on_default_and_kill_switch() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("RALPH_TOOT_IMAGE", None)
        assert ralph._toot_image_on() is True
    for off in ("off", "0", "false", "no", "OFF"):
        with mock.patch.dict(os.environ, {"RALPH_TOOT_IMAGE": off}):
            assert ralph._toot_image_on() is False


def test_first_image_url_extracts_documented_path() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    resp = {"choices": [{"message": {"images": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAB"}}]}}]}
    assert ralph._first_image_url(resp) == "data:image/png;base64,AAAB"
    assert ralph._first_image_url({"choices": [{"message": {}}]}) is None
    assert ralph._first_image_url({}) is None


def test_decode_data_url_roundtrip_and_reject() -> None:
    import base64
    import importlib
    ralph = importlib.import_module("ralph")
    raw = b"\x89PNG\r\n\x1a\nhello-bytes"
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    decoded = ralph._decode_data_url(url)
    assert decoded == (raw, "image/png")
    assert ralph._decode_data_url("https://example.com/x.png") is None
    assert ralph._decode_data_url("data:image/png;base64,") is None


def test_multipart_body_shape() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    body, ctype = ralph._multipart({"description": "alt text"}, "file",
                                   "ralph.png", "image/png", b"\x00\x01\x02")
    assert ctype.startswith("multipart/form-data; boundary=----ralph")
    boundary = ctype.split("boundary=", 1)[1]
    assert boundary.encode() in body
    assert b'name="description"' in body and b"alt text" in body
    assert b'name="file"; filename="ralph.png"' in body
    assert b"Content-Type: image/png" in body
    assert b"\x00\x01\x02" in body


def test_generate_image_none_without_key() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    assert ralph._generate_image("title", "vendor/img", "", None) is None


def test_generate_image_decodes_model_output() -> None:
    import base64
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    raw = b"PNGDATA"
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    resp = {"choices": [{"message": {"images": [
        {"type": "image_url", "image_url": {"url": url}}]}}]}
    with mock.patch.object(ralph, "openrouter_call", return_value=resp) as call:
        out = ralph._generate_image("Adopt Zoekt", "vendor/img", "key", None)
    assert out == (raw, "image/png")
    # image generation must request the image modality
    assert call.call_args.kwargs.get("modalities") == ["image", "text"]


def test_generate_image_swallows_errors() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    with mock.patch.object(ralph, "openrouter_call", side_effect=RuntimeError("503")):
        assert ralph._generate_image("t", "vendor/img", "key", None) is None


def test_upload_media_returns_id_sync() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"id":"42","url":"https://m/media/42"}'

    captured = {}

    def fake(req, timeout=None):
        captured["url"] = req.full_url
        captured["ctype"] = req.headers.get("Content-type")
        return _Resp()

    with mock.patch.object(ralph.urllib.request, "urlopen", side_effect=fake):
        mid = ralph._upload_media("https://m", "tok", b"\x00img", "image/png", "alt")
    assert mid == "42"
    assert captured["url"].endswith("/api/v2/media")
    assert captured["ctype"].startswith("multipart/form-data")


def test_upload_media_polls_when_processing() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")

    class _Post:
        status = 202
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"id":"7"}'

    class _Ready:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"id":"7","url":"https://m/7"}'

    seq = [_Post(), _Ready()]
    state = {"i": 0}

    def fake(req, timeout=None):
        v = seq[state["i"]]
        state["i"] += 1
        return v

    with mock.patch.object(ralph.urllib.request, "urlopen", side_effect=fake), \
         mock.patch.object(ralph.time, "sleep"):
        mid = ralph._upload_media("https://m", "tok", b"img", "image/png", "alt")
    assert mid == "7" and state["i"] == 2


def test_upload_media_none_on_error() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    with mock.patch.object(ralph.urllib.request, "urlopen",
                           side_effect=RuntimeError("boom")):
        assert ralph._upload_media("https://m", "tok", b"img", "image/png", "a") is None


def test_post_toot_includes_media_ids() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"id":"1"}'

    def fake(req, timeout=None):
        captured["body"] = req.data.decode()
        return _Resp()

    with mock.patch.object(ralph.urllib.request, "urlopen", side_effect=fake):
        ralph._post_toot("https://m", "tok", "hi", "unlisted", "x",
                         media_ids=["11", "22"])
    assert "media_ids%5B%5D=11" in captured["body"]   # media_ids[]=11 url-encoded
    assert "media_ids%5B%5D=22" in captured["body"]


def test_cmd_announce_attaches_generated_image() -> None:
    """End-to-end: a generated image is uploaded and its id is passed to the post."""
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        e = make_entry(GENESIS_HASH, 0, {"event": "decide", "track": "graph-concept",
                                         "iteration": 1, "cost": 0.01, "total_cost": 0.01})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        with open(os.path.join(tmpdir, "graph-concept.ralph-log.md"), "w",
                  encoding="utf-8") as f:
            f.write("## 2026-06-13 — Decision #1: Split the LPG\nbody\n")
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        captured = {}
        try:
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "OPENROUTER_API_KEY": "key"}), \
                 mock.patch.object(ralph, "_generate_toot", return_value="toot #ralph"), \
                 mock.patch.object(ralph, "_run", return_value="[]"), \
                 mock.patch.object(ralph, "_generate_image",
                                   return_value=(b"img", "image/png")), \
                 mock.patch.object(ralph, "_upload_media", return_value="55"), \
                 mock.patch.object(ralph, "_post_toot",
                                   side_effect=lambda *a, **k: captured.update(k) or {"id": "9"}):
                rc = ralph.cmd_announce(_announce_args(tmpdir))
        finally:
            ralph.DECISIONS_DIR = orig
        assert rc == 0
        assert captured.get("media_ids") == ["55"]


def test_cmd_announce_text_only_when_image_fails() -> None:
    """If image generation yields nothing, the toot still posts (no media_ids)."""
    import importlib
    import unittest.mock as mock
    from ralphcore import make_entry, GENESIS_HASH
    ralph = importlib.import_module("ralph")
    with tempfile.TemporaryDirectory() as tmpdir:
        e = make_entry(GENESIS_HASH, 0, {"event": "decide", "track": "graph-concept",
                                         "iteration": 1, "cost": 0.01, "total_cost": 0.01})
        with open(os.path.join(tmpdir, "events.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(e) + "\n")
        with open(os.path.join(tmpdir, "graph-concept.ralph-log.md"), "w",
                  encoding="utf-8") as f:
            f.write("## 2026-06-13 — Decision #1: Split the LPG\nbody\n")
        orig = ralph.DECISIONS_DIR
        ralph.DECISIONS_DIR = tmpdir
        captured = {}
        try:
            with mock.patch.dict(os.environ, {"MASTODON_ACCESS_TOKEN": "tok",
                                              "OPENROUTER_API_KEY": "key"}), \
                 mock.patch.object(ralph, "_generate_toot", return_value="toot #ralph"), \
                 mock.patch.object(ralph, "_run", return_value="[]"), \
                 mock.patch.object(ralph, "_generate_image", return_value=None), \
                 mock.patch.object(ralph, "_post_toot",
                                   side_effect=lambda *a, **k: captured.update(k) or {"id": "9"}):
                rc = ralph.cmd_announce(_announce_args(tmpdir))
        finally:
            ralph.DECISIONS_DIR = orig
        assert rc == 0
        assert captured.get("media_ids") in (None, [])


# ---------------------------------------------------------------------------
# orjson parse shim, image compression, richer/cache-friendly context
# ---------------------------------------------------------------------------


def test_loads_parses_str_and_bytes() -> None:
    import importlib
    ralph = importlib.import_module("ralph")
    import ralphcore as core
    for loads in (ralph._loads, core._loads):
        assert loads('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}
        assert loads(b'{"a": 1}') == {"a": 1}


def test_loads_raises_jsondecodeerror_on_garbage() -> None:
    """Existing `except json.JSONDecodeError` handlers must still catch bad input
    whether stdlib or orjson backs `_loads` (orjson subclasses it)."""
    import importlib
    import json
    ralph = importlib.import_module("ralph")
    try:
        ralph._loads("{not json")
        assert False, "should have raised"
    except json.JSONDecodeError:
        pass


def test_compress_image_fallback_returns_raw_without_pillow() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    with mock.patch.object(ralph, "_PILImage", None):
        out = ralph._compress_image(b"\x89PNG rawbytes", "image/png")
    assert out == (b"\x89PNG rawbytes", "image/png")


def test_compress_image_shrinks_when_pillow_present() -> None:
    """If Pillow is installed, a big PNG is downscaled + re-encoded smaller JPEG."""
    import importlib
    ralph = importlib.import_module("ralph")
    if ralph._PILImage is None:
        return  # Pillow not installed in this env — fallback path covered above
    import io
    img = ralph._PILImage.new("RGB", (3000, 2000), (40, 30, 80))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()
    out, mime = ralph._compress_image(raw, "image/png")
    assert mime == "image/jpeg" and len(out) < len(raw)
    with ralph._PILImage.open(io.BytesIO(out)) as got:
        assert max(got.size) <= ralph.TOOT_IMAGE_MAX_EDGE


def test_repo_tree_groups_by_top_dir() -> None:
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    listing = "README.md\ntools/a.py\ntools/b.py\ndocs/x.md\n"
    with mock.patch.object(ralph, "_run", return_value=listing):
        tree = ralph._repo_tree("/whatever")
    assert "README.md" in tree            # top-level file, no slash/count
    assert "tools/ (2)" in tree           # dir with count
    assert "docs/ (1)" in tree


def test_gather_context_is_rich_and_cache_friendly() -> None:
    """Key files lead (stable prefix for prompt caching), git log trails, and the
    output now includes the repo tree + open PRs."""
    import importlib
    import unittest.mock as mock
    ralph = importlib.import_module("ralph")
    import ralphcore as core
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Title\nthe readme body")

        def fake_run(cmd, cwd, timeout=30):
            if cmd[:2] == ["git", "rev-parse"]:
                return "headsha\n"
            if cmd[:2] == ["git", "ls-files"]:
                return "README.md\ntools/a.py\ntools/b.py\n"
            if cmd[:2] == ["git", "log"]:
                return "headsha most recent commit\n"
            if cmd[:1] == ["gh"] and "issue" in cmd:
                return '[{"number":1,"title":"An issue","body":"x"}]'
            if cmd[:1] == ["gh"] and "pr" in cmd:
                return '[{"number":2,"title":"A PR"}]'
            return ""

        repo = core.Repo(name="r", path=d, gh="o/r")
        with mock.patch.object(ralph, "_run", side_effect=fake_run):
            out = ralph.gather_context(repo, 20, compact=False)
    assert "the readme body" in out
    assert "Repo layout" in out and "tools/ (2)" in out
    assert "## Open pull requests\n#2 A PR" in out
    assert "#1 An issue" in out
    # stable (key files) before volatile (git log)
    assert out.index("README.md") < out.index("## Git log")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Auto-discover every test_* function in this module (sorted for stable
    # order), so newly-added tests are never silently skipped.
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]

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
