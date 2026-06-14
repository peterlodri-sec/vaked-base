"""Standalone test runner for introspectcore (the ralph-introspect pure logic).

Offline, stdlib-only — no Langfuse, no model calls. Mirrors test_ralph.py's
auto-discovering runner.
"""
from __future__ import annotations

import sys

import introspectcore as I


def _approx(a: float, b: float, eps: float = 1e-6) -> bool:
    return abs(a - b) <= eps


def test_iso_window_shape() -> None:
    frm, to = I.iso_window(2.0)
    assert frm.endswith("Z") and to.endswith("Z"), (frm, to)
    assert frm < to, (frm, to)


def test_aggregate_groups_by_model_and_costs_from_tokens() -> None:
    obs = [
        {"model": "deepseek/deepseek-v4-flash", "promptTokens": 1000, "completionTokens": 500,
         "latency": 1.0, "level": "DEFAULT"},
        {"model": "deepseek/deepseek-v4-flash", "promptTokens": 1000, "completionTokens": 500,
         "latency": 3.0, "statusMessage": "boom"},  # error via statusMessage
        {"model": "anthropic/claude-opus-4.8", "usage": {"input": 2000, "output": 1000},
         "latency": 2.0, "finishReason": "length"},  # truncated; tokens via usage fallback
    ]
    # cost_fn: $1/Mtok in, $2/Mtok out
    cf = lambda m, pin, pout: pin / 1e6 * 1.0 + pout / 1e6 * 2.0  # noqa: E731
    by_model = I.aggregate_observations(obs, cost_fn=cf)
    ds = by_model["deepseek/deepseek-v4-flash"]
    assert ds["calls"] == 2, ds
    assert ds["errors"] == 1, ds                       # the statusMessage one
    assert ds["prompt_tokens"] == 2000 and ds["completion_tokens"] == 1000, ds
    # cost = 2*(1000/1e6*1) + 2*(500/1e6*2) = 0.002 + 0.002 = 0.004
    assert _approx(ds["cost"], 0.004), ds["cost"]
    op = by_model["anthropic/claude-opus-4.8"]
    assert op["truncated"] == 1 and op["prompt_tokens"] == 2000, op


def test_span_counts() -> None:
    obs = [{"name": "gen_ai.generate"}, {"name": "gen_ai.generate"}, {"name": "pr_review"}]
    c = I.span_counts(obs)
    assert c == {"gen_ai.generate": 2, "pr_review": 1}, c


def test_economy_projection_linear() -> None:
    e = I.economy_projection(0.34, 2.0)
    assert _approx(e["per_day"], 0.17), e
    assert _approx(e["per_week"], round(0.17 * 7, 2)), e
    assert _approx(e["per_month"], round(0.17 * 30.4, 2)), e


def test_build_digest_economy_matches() -> None:
    by_model = {"m": {"calls": 1, "errors": 0, "truncated": 0, "cost": 1.0,
                      "prompt_tokens": 10, "completion_tokens": 5,
                      "latency_p50": 1.0, "latency_p95": 1.0}}
    md, econ = I.build_digest(by_model, {"m": 1}, {"ralph": {"events": 0}}, {}, 2.0)
    assert "per model" in md and "Economy" in md, md[:200]
    assert _approx(econ["window_cost"], 1.0) and _approx(econ["per_day"], 0.5), econ


def test_passes_gate_all_paths() -> None:
    ok = {"approved": True, "novel": True, "grounded": True, "actionable": True, "confidence": 0.9}
    passed, reason = I.passes_gate(ok, 0.75)
    assert passed and reason == "", (passed, reason)
    for bad, want in (
        ({**ok, "approved": False}, "not-approved"),
        ({**ok, "novel": False}, "not-novel"),
        ({**ok, "grounded": False}, "not-grounded-in-telemetry"),
        ({**ok, "actionable": False}, "not-actionable"),
        ({**ok, "confidence": 0.5}, "below-confidence-threshold"),
    ):
        p, r = I.passes_gate(bad, 0.75)
        assert not p and r == want, (bad, p, r)


def test_prior_introspect_titles_dedupe() -> None:
    events = [
        {"payload": {"event": "introspect_found", "title": "A"}},
        {"payload": {"event": "introspect_rejected", "title": "B"}},
        {"payload": {"event": "decide", "title": "C"}},     # not an introspect event
        {"payload": {"event": "introspect_none"}},          # no title
    ]
    assert I.prior_introspect_titles(events) == ["A", "B"], I.prior_introspect_titles(events)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:                            # noqa: BLE001
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
