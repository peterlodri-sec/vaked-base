#!/usr/bin/env python3
"""vaked_dash — Langfuse fleet dashboard for Vaked: query, debug, export.

Reads from self-hosted Langfuse over its public REST API (no langfuse SDK
required — pure stdlib HTTP). Scopes all trace queries to the Vaked fleet via
the 'vaked' tag; model leaderboard uses the observations/GENERATION endpoint
(same as tools/optitron/internal/introspect/langfuse.go).

Usage:
    python3 tools/langfuse-dash/vaked_dash.py [OPTIONS]

Options:
    --days N            Lookback window in days (default: 7)
    --agent NAME        Filter to a trace name prefix
                        (e.g. vakedc.check, vakedc.lower, pr-review)
    --errors-only       Show only ERROR/WARNING traces or traces with diag_count>0
    --summary           Fleet summary + model leaderboard (default)
    --traces            One-line-per-trace table with deep-link URLs
    --export {json,csv} Export all trace data to a dated file

Required env:
    LANGFUSE_HOST          Self-hosted Langfuse base URL
    LANGFUSE_PUBLIC_KEY    Project public key
    LANGFUSE_SECRET_KEY    Project secret key

Optional env:
    LANGFUSE_PROJECT_ID    Project ID (enables trace deep-link URLs in --traces)
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── env resolution ─────────────────────────────────────────────────────────

def _env_first(*keys: str) -> str:
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _base_url() -> str:
    return _env_first("LANGFUSE_HOST", "LANGFUSE_BASE_URL", "LANGFUSE_URL").rstrip("/")


def _auth_token() -> str:
    pk = _env_first("LANGFUSE_PUBLIC_KEY")
    sk = _env_first("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        sys.exit("vaked_dash: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required")
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()


def _project_id() -> str:
    return _env_first("LANGFUSE_PROJECT_ID")


# ── API client ─────────────────────────────────────────────────────────────

def _api_get(
    path: str,
    params: dict[str, str],
    token: str,
    base: str,
    max_pages: int = 20,
) -> list[dict]:
    """Paginate a Langfuse list endpoint and return the merged data array.

    Mirrors the pagination loop in tools/optitron/internal/introspect/langfuse.go.
    """
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        q = dict(params)
        q["page"] = str(page)
        q["limit"] = "100"
        url = f"{base}{path}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as e:
            if page == 1:
                print(
                    f"vaked_dash: {path} HTTP {e.code} — "
                    "check LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY",
                    file=sys.stderr,
                )
            break
        except Exception as e:
            print(f"vaked_dash: {path} page {page}: {e}", file=sys.stderr)
            break
        data = body.get("data", [])
        out.extend(data)
        meta = body.get("meta", {})
        total_pages = meta.get("totalPages") or meta.get("total_pages") or 1
        if not data or page >= int(total_pages):
            break
    return out


# ── data fetching ──────────────────────────────────────────────────────────

def _from_ts(days: int) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_traces(
    token: str,
    base: str,
    days: int,
    agent: str | None,
    errors_only: bool,
) -> list[dict]:
    params: dict[str, str] = {
        "fromTimestamp": _from_ts(days),
        "tags": "vaked",
    }
    if agent:
        params["name"] = agent
    traces = _api_get("/api/public/traces", params, token, base)
    if errors_only:
        traces = [
            t for t in traces
            if t.get("level") in ("ERROR", "WARNING")
            or int((t.get("metadata") or {}).get("diag_count") or 0) > 0
        ]
    return traces


def fetch_observations(token: str, base: str, days: int) -> list[dict]:
    params: dict[str, str] = {
        "type": "GENERATION",
        "fromStartTime": _from_ts(days),
    }
    return _api_get("/api/public/observations", params, token, base)


# ── aggregation ────────────────────────────────────────────────────────────

def _latency_ms(t: dict) -> float:
    v = t.get("latency") or t.get("duration") or 0
    return float(v)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(int(len(s) * pct / 100), len(s) - 1))
    return s[idx]


def agent_stats(traces: list[dict]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for t in traces:
        name = t.get("name") or "unknown"
        groups.setdefault(name, []).append(t)

    result = {}
    for name, ts in groups.items():
        latencies = [_latency_ms(t) for t in ts if _latency_ms(t) > 0]
        errors = sum(1 for t in ts if t.get("level") == "ERROR")
        result[name] = {
            "count": len(ts),
            "errors": errors,
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
        }
    return result


def model_leaderboard(obs: list[dict]) -> list[dict]:
    """Group GENERATION observations by model; sort by total cost descending."""
    models: dict[str, dict] = {}
    for o in obs:
        model = o.get("model") or "unknown"
        usage = o.get("usage") or {}
        cost = float(usage.get("totalCost") or usage.get("total_cost") or 0)
        tokens = int(usage.get("total") or usage.get("totalTokens") or 0)
        level = o.get("level", "DEFAULT")

        if model not in models:
            models[model] = {"calls": 0, "tokens": 0, "cost": 0.0, "errors": 0}
        models[model]["calls"] += 1
        models[model]["tokens"] += tokens
        models[model]["cost"] += cost
        if level in ("ERROR", "WARNING"):
            models[model]["errors"] += 1

    board = [{"model": m, **stats} for m, stats in models.items()]
    return sorted(board, key=lambda x: x["cost"], reverse=True)


# ── output modes ───────────────────────────────────────────────────────────

_HR = "─" * 68


def _obs_total_cost(obs: list[dict]) -> float:
    total = 0.0
    for o in obs:
        usage = o.get("usage") or {}
        total += float(usage.get("totalCost") or usage.get("total_cost") or 0)
    return total


def print_summary(traces: list[dict], obs: list[dict], days: int) -> None:
    total = len(traces)
    errors = sum(1 for t in traces if t.get("level") == "ERROR")
    err_pct = errors / total * 100 if total else 0.0
    cost = _obs_total_cost(obs)

    print(f"\nVAKED FLEET — last {days}d")
    print(_HR)
    print(f"traces  {total:>6}    errors {errors:>4}  ({err_pct:.1f}%)")
    print(f"cost    ${cost:.4f}")
    print(_HR)

    stats = agent_stats(traces)
    if stats:
        print(f"{'agent':<32} {'traces':>6}  {'err':>4}  {'p50ms':>7}  {'p95ms':>7}")
        for name, s in sorted(stats.items()):
            print(
                f"{name:<32} {s['count']:>6}  {s['errors']:>4}  "
                f"{s['p50']:>7.0f}  {s['p95']:>7.0f}"
            )

    board = model_leaderboard(obs)
    if board:
        print(_HR)
        print(f"MODEL LEADERBOARD — last {days}d")
        print(
            f"{'#':<4} {'model':<44} {'calls':>6}  {'tok(k)':>7}  {'cost':>8}  {'err':>4}"
        )
        for i, m in enumerate(board, 1):
            print(
                f"{i:<4} {m['model']:<44} {m['calls']:>6}  "
                f"{m['tokens'] // 1000:>7}  ${m['cost']:>7.4f}  {m['errors']:>4}"
            )

    recent_errors = sorted(
        [
            t for t in traces
            if t.get("level") in ("ERROR", "WARNING")
            or int((t.get("metadata") or {}).get("diag_count") or 0) > 0
        ],
        key=lambda x: x.get("timestamp") or "",
        reverse=True,
    )[:8]
    if recent_errors:
        print(_HR)
        print("TOP ISSUES (most recent first)")
        for t in recent_errors:
            ts = (t.get("timestamp") or "")[:16].replace("T", " ")
            name = (t.get("name") or "?")[:30]
            msg = (t.get("statusMessage") or t.get("status_message") or "")[:36]
            level = t.get("level") or "?"
            print(f"[{ts}]  {name:<30}  {level:<8}  {msg}")
    print()


def print_traces(traces: list[dict], days: int) -> None:
    project = _project_id()
    base = _base_url()
    print(f"\nVAKED TRACES — last {days}d  ({len(traces)} total)")
    print(_HR)
    hdr = f"{'timestamp':<20}  {'name':<28}  {'status':<8}  {'ms':>7}"
    if project:
        hdr += "  url"
    print(hdr)
    print(_HR)
    for t in sorted(traces, key=lambda x: x.get("timestamp") or "", reverse=True):
        ts = (t.get("timestamp") or "")[:16].replace("T", " ")
        name = (t.get("name") or "?")[:27]
        level = t.get("level") or "OK"
        ms = _latency_ms(t)
        line = f"{ts:<20}  {name:<28}  {level:<8}  {ms:>7.0f}"
        if project:
            tid = t.get("id") or ""
            line += f"  {base}/project/{project}/traces/{tid}"
        print(line)
    print()


def export_json(traces: list[dict], obs: list[dict], days: int) -> None:
    date = datetime.date.today().strftime("%Y%m%d")
    path = f"vaked-traces-{date}.json"
    payload = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "days": days,
        "summary": {
            "trace_count": len(traces),
            "error_count": sum(1 for t in traces if t.get("level") == "ERROR"),
            "total_cost": _obs_total_cost(obs),
        },
        "model_leaderboard": model_leaderboard(obs),
        "traces": traces,
        "observations": obs,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"vaked_dash: wrote {path}  ({len(traces)} traces, {len(obs)} observations)")


def export_csv(traces: list[dict], days: int) -> None:
    date = datetime.date.today().strftime("%Y%m%d")
    path = f"vaked-traces-{date}.csv"
    fields = [
        "trace_id", "name", "status", "started_at", "duration_ms",
        "diag_count", "diag_codes", "ast_items", "artifacts",
        "file", "pr_url", "error_message",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for t in traces:
            meta = t.get("metadata") or {}
            w.writerow({
                "trace_id": t.get("id") or "",
                "name": t.get("name") or "",
                "status": t.get("level") or "OK",
                "started_at": (t.get("timestamp") or "")[:19],
                "duration_ms": round(_latency_ms(t)),
                "diag_count": meta.get("diag_count") or "",
                "diag_codes": (
                    json.dumps(meta["diag_codes"])
                    if meta.get("diag_codes")
                    else ""
                ),
                "ast_items": meta.get("ast_items") or "",
                "artifacts": meta.get("artifacts") or "",
                "file": meta.get("file") or "",
                "pr_url": meta.get("pr_url") or "",
                "error_message": (
                    t.get("statusMessage") or t.get("status_message") or ""
                ),
            })
    print(f"vaked_dash: wrote {path}  ({len(traces)} rows)")


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Vaked Langfuse fleet dashboard — query, debug, export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "ENV: LANGFUSE_HOST  LANGFUSE_PUBLIC_KEY  LANGFUSE_SECRET_KEY\n"
            "     LANGFUSE_PROJECT_ID  (optional; enables trace deep-links)"
        ),
    )
    ap.add_argument("--days", type=int, default=7, metavar="N",
                    help="lookback window in days (default: 7)")
    ap.add_argument("--agent", metavar="NAME",
                    help="filter by trace name (e.g. vakedc.check, pr-review)")
    ap.add_argument("--errors-only", action="store_true",
                    help="show only error/warning traces or traces with diagnostics")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--summary", action="store_true",
                      help="fleet summary + model leaderboard (default)")
    mode.add_argument("--traces", action="store_true",
                      help="one-line-per-trace table with deep-link URLs")
    mode.add_argument("--export", choices=["json", "csv"],
                      help="export trace data to a dated file")
    args = ap.parse_args()

    base = _base_url()
    if not base:
        sys.exit("vaked_dash: LANGFUSE_HOST is required")
    token = _auth_token()

    print(f"vaked_dash: querying {base}  (last {args.days}d)…", file=sys.stderr)
    traces = fetch_traces(token, base, args.days, args.agent, args.errors_only)

    if args.traces:
        print_traces(traces, args.days)
    elif args.export == "csv":
        export_csv(traces, args.days)
    elif args.export == "json":
        obs = fetch_observations(token, base, args.days)
        export_json(traces, obs, args.days)
    else:
        obs = fetch_observations(token, base, args.days)
        print_summary(traces, obs, args.days)


if __name__ == "__main__":
    main()
