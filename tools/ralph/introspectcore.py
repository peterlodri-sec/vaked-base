"""introspectcore — pure, offline-testable logic for `ralph introspect`.

The introspect loop mines the fleet's OWN Langfuse telemetry (+ ledgers + CI) over
the last ≤2 days, auto-detects the most salient finding, ideates ONE novel
solution, and reviews it before it speaks. This module holds everything that is
deterministic and unit-testable without a network or a model:

  * the telemetry-digest aggregation (Langfuse observations → per-bot stats),
  * the economy roll-up + non-optimistic day/week/month projection,
  * the strict json_schema response formats (detect / ideate / review),
  * the fail-closed adjudication gate,
  * prior-finding dedupe + the prompt builders.

Stdlib only — mirrors ralphcore's style so `ralph introspect` stays dependency-free.
"""
from __future__ import annotations

import datetime
import json

# Every CI bot that emits Langfuse spans — the introspection surface. Span names
# are matched by prefix so e.g. "ralph.deep-dive" and "pr-review my/repo#1" group
# to their bot.
BOT_PREFIXES = ("ralph", "pr-review", "optitron", "label-tagger", "swe-af", "provost")


def iso_window(window_days: float, now: datetime.datetime | None = None) -> tuple[str, str]:
    """(fromTimestamp, toTimestamp) ISO-8601/Z for the last `window_days`."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    start = now - datetime.timedelta(days=window_days)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), now.strftime(fmt)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


def _obs_tokens(o: dict) -> tuple[int, int]:
    """(prompt, completion) tokens from the reliable top-level fields, falling
    back to the usage/usageDetails objects."""
    pin = o.get("promptTokens")
    pout = o.get("completionTokens")
    if pin is None or pout is None:
        u = o.get("usage") or o.get("usageDetails") or {}
        pin = u.get("input", u.get("prompt_tokens", 0)) if pin is None else pin
        pout = u.get("output", u.get("completion_tokens", 0)) if pout is None else pout
    return int(_num(pin)), int(_num(pout))


def aggregate_observations(observations: list[dict], cost_fn=None) -> dict:
    """Group Langfuse GENERATION observations by **model** → stats.

    Real (self-hosted, OTel) observations name the span `gen_ai.generate`, so the
    `model` is the reliable grouping key; the per-bot span signal is captured
    separately by `span_counts`. Server-side cost is often absent, so cost is
    computed client-side from tokens via `cost_fn(model, prompt, completion)`.
    Errors: `level == "ERROR"` or a non-empty `statusMessage`. Truncation:
    `finishReason == "length"` when present.
    """
    by_model: dict[str, dict] = {}
    for o in observations:
        model = o.get("model") or "unknown"
        s = by_model.setdefault(model, {"calls": 0, "errors": 0, "truncated": 0,
                                        "cost": 0.0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "_lat": []})
        s["calls"] += 1
        if str(o.get("level", "")).upper() == "ERROR" or o.get("statusMessage"):
            s["errors"] += 1
        if str(o.get("finishReason") or o.get("finish_reason") or "").lower() == "length":
            s["truncated"] += 1
        pin, pout = _obs_tokens(o)
        s["prompt_tokens"] += pin
        s["completion_tokens"] += pout
        srv = _num(o.get("calculatedTotalCost") or o.get("totalCost") or o.get("totalPrice"))
        s["cost"] += srv if srv > 0 else (cost_fn(model, pin, pout) if cost_fn else 0.0)
        lat = o.get("latency")
        if lat is not None:
            s["_lat"].append(_num(lat))
    for s in by_model.values():
        lat = s.pop("_lat", [])
        s["latency_p50"] = round(_percentile(lat, 50), 3)
        s["latency_p95"] = round(_percentile(lat, 95), 3)
        s["cost"] = round(s["cost"], 4)
    return by_model


def span_counts(observations: list[dict]) -> dict:
    """Per-span-name call counts — the coarse per-bot signal (ralph.rank,
    gen_ai.generate, pr_review, optitron …)."""
    counts: dict[str, int] = {}
    for o in observations:
        n = o.get("name") or "?"
        counts[n] = counts.get(n, 0) + 1
    return counts


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def economy_projection(window_cost: float, window_days: float) -> dict:
    """Normal, non-optimistic spend projection anchored to measured window cost.

    Linear from the observed per-day rate: /day, /week (×7), /month (×30.4).
    """
    per_day = (window_cost / window_days) if window_days > 0 else 0.0
    return {
        "window_days": window_days,
        "window_cost": round(window_cost, 4),
        "per_day": round(per_day, 4),
        "per_week": round(per_day * 7, 2),
        "per_month": round(per_day * 30.4, 2),
    }


def build_digest(by_model: dict, spans: dict, ledger_stats: dict, ci_stats: dict,
                 window_days: float) -> tuple[str, dict]:
    """Render the compact telemetry digest text + the economy roll-up.

    Returns (digest_markdown, economy_dict). The economy is computed from the
    summed per-model Langfuse cost over the window — real, not guessed.
    """
    total_cost = sum(s.get("cost", 0.0) for s in by_model.values())
    econ = economy_projection(total_cost, window_days)

    lines = [f"# Fleet telemetry digest — last {window_days:g}d", ""]
    if by_model:
        lines.append("## Langfuse (per model)")
        lines.append("| model | calls | err | trunc | p50s | p95s | cost$ | tok(in/out) |")
        lines.append("|-------|------:|----:|------:|-----:|-----:|------:|-------------|")
        for model in sorted(by_model, key=lambda m: -by_model[m]["calls"]):
            s = by_model[model]
            lines.append(
                f"| {model} | {s['calls']} | {s['errors']} | {s['truncated']} | "
                f"{s['latency_p50']} | {s['latency_p95']} | {s['cost']:.4f} | "
                f"{s['prompt_tokens']}/{s['completion_tokens']} |")
        if spans:
            top = sorted(spans.items(), key=lambda kv: -kv[1])[:12]
            lines += ["", "spans: " + ", ".join(f"{n}×{c}" for n, c in top)]
    else:
        lines.append("## Langfuse: (no observations / keys absent)")
    lines += ["", "## Ledgers", "```json", json.dumps(ledger_stats, indent=2), "```"]
    if ci_stats:
        lines += ["", "## CI (recent runs)", "```json", json.dumps(ci_stats, indent=2), "```"]
    lines += ["", "## Economy (normal, non-optimistic — from measured window cost)",
              f"- window: ${econ['window_cost']:.4f} over {window_days:g}d",
              f"- **/day ${econ['per_day']:.4f} · /week ${econ['per_week']:.2f} · "
              f"/month ${econ['per_month']:.2f}**"]
    return "\n".join(lines), econ


# ---------------------------------------------------------------------------
# Strict json_schema response formats (OpenRouter). Every field required so a
# lenient provider can't omit one and slip past the gate.
# ---------------------------------------------------------------------------

def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": required, "properties": props}


def _schema(name: str, root: dict) -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": root}}


DETECT_SCHEMA = _schema("introspect_detect", _obj({
    "finding": {"type": "string"},          # the single most salient finding
    "bot": {"type": "string"},              # which bot/area it concerns
    "evidence": {"type": "string"},         # exact digest numbers backing it
    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
    "rationale": {"type": "string"},
}, ["finding", "bot", "evidence", "severity", "rationale"]))


IDEATE_SCHEMA = _schema("introspect_idea", _obj({
    "title": {"type": "string"},
    "mechanism": {"type": "string"},        # how the idea works, concretely
    "novelty_rationale": {"type": "string"},
    "target_files": {"type": "array", "items": {"type": "string"}},
    "expected_effect": {"type": "string"},
    "evidence": {"type": "string"},         # the telemetry numbers it is grounded in
    "signature": {"type": "string"},        # grep-able marker if already applied
    "confidence": {"type": "number"},       # 0..1
}, ["title", "mechanism", "novelty_rationale", "target_files",
    "expected_effect", "evidence", "signature", "confidence"]))


REVIEW_SCHEMA = _schema("introspect_review", _obj({
    "approved": {"type": "boolean"},
    "novel": {"type": "boolean"},
    "grounded": {"type": "boolean"},        # cites real digest numbers, not invented
    "actionable": {"type": "boolean"},
    "confidence": {"type": "number"},
    "critique": {"type": "string"},
}, ["approved", "novel", "grounded", "actionable", "confidence", "critique"]))


def passes_gate(review: dict, min_confidence: float) -> tuple[bool, str]:
    """Fail-closed review gate. Returns (passed, reason-if-rejected)."""
    if not review.get("approved"):
        return False, "not-approved"
    if not review.get("novel"):
        return False, "not-novel"
    if not review.get("grounded"):
        return False, "not-grounded-in-telemetry"
    if not review.get("actionable"):
        return False, "not-actionable"
    if _num(review.get("confidence")) < min_confidence:
        return False, "below-confidence-threshold"
    return True, ""


# ---------------------------------------------------------------------------
# Dedupe — prior introspect findings (read from the shared ralph ledger).
# ---------------------------------------------------------------------------

def prior_introspect_titles(events: list[dict]) -> list[str]:
    """Titles of every prior introspect found/rejected event (novelty memory)."""
    out: list[str] = []
    for e in events:
        p = e.get("payload", {})
        if p.get("event") in ("introspect_found", "introspect_rejected") and p.get("title"):
            out.append(p["title"])
    return out


# ---------------------------------------------------------------------------
# Prompt builders. The system message is the introspect mission preamble.
# ---------------------------------------------------------------------------

def build_detect_messages(purpose: str, digest: str, focus: str) -> list[dict]:
    user = (
        "Below is the fleet's own telemetry digest (Langfuse traces + ledgers + CI) "
        "for the recent window. Identify the SINGLE most salient finding worth "
        "improving — an error spike, latency/cost outlier, retry storm, truncation, "
        "low ratify-rate, or a repeated failure. Ground it in EXACT numbers from the "
        "digest; do not invent any. Output one finding.\n\n"
    )
    if focus.strip():
        user += f"OPERATOR FOCUS (prioritise this if the digest supports it): {focus}\n\n"
    user += "DIGEST:\n" + digest
    return [{"role": "system", "content": purpose}, {"role": "user", "content": user}]


def build_ideate_messages(purpose: str, finding: dict, digest: str) -> list[dict]:
    user = (
        "Design ONE novel, concrete solution/idea for the finding below. It must be "
        "actionable in THIS repo (name target files), grounded in the telemetry "
        "numbers (quote them in `evidence`), and genuinely novel — not already common "
        "practice or already applied here. Provide a grep-able `signature` that would "
        "appear in a codebase that ALREADY does it (for a novelty check). Be honest "
        "about `confidence`.\n\nFINDING:\n" + json.dumps(finding, indent=2) +
        "\n\nDIGEST (for grounding):\n" + digest
    )
    return [{"role": "system", "content": purpose}, {"role": "user", "content": user}]


def build_review_messages(purpose: str, finding: dict, idea: dict, digest: str) -> list[dict]:
    user = (
        "Adversarially REVIEW this proposed idea before it is filed. Decide: is it "
        "`novel` (not already in the repo/ledger, not generic advice), `grounded` (its "
        "evidence cites REAL numbers present in the digest, not hallucinated), and "
        "`actionable` (concrete, scoped, names plausible target files)? Set `approved` "
        "only if all hold. Be skeptical — a plausible-sounding but ungrounded idea is a "
        "hallucination and must be rejected.\n\nFINDING:\n" + json.dumps(finding, indent=2) +
        "\n\nIDEA:\n" + json.dumps(idea, indent=2) +
        "\n\nDIGEST (the ground truth):\n" + digest
    )
    return [{"role": "system", "content": purpose}, {"role": "user", "content": user}]
