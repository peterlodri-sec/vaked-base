#!/usr/bin/env python3
"""vaked-optitron — daily optimization crawler.

A singularity-native crawler whose ONE job is to surface a single novel, proven,
independently-confirmed compiler / allocator / Zig / Rust / Vaked optimization — or
nothing. It abstains by default: only a finding that clears the strict gate (>=2
independent sources + repo/ledger novelty + a REPRODUCED micro-benchmark + a
confidence threshold) is acted on, by opening a GitHub issue labelled `agent` (the
swe_af workflow's trigger) and announcing to Mastodon + Telegram.

The declarative spec lives in `.claude/skills/vaked-optitron/SKILL.md`; this harness
is one concrete runtime that loads it as its system prompt. Stdlib-first, mirrors the
ralph archetype (hash-chained ledger, OpenRouter via urllib, optional Langfuse, guard
on secrets, advisory — any failure logs and exits 0).

Commands:
  crawl [--once] [--dry-run]    one crawl→verify→bench→adjudicate→act cycle
  events [--replay]             verify the hash-chained ledger / print state

Env: OPENROUTER_API_KEY | RALPH_API_KEY · OPTITRON_BASE_URL · LANGFUSE_* · GH_TOKEN
     OPTITRON_CRAWL_MODEL · OPTITRON_VERIFY_MODEL · OPTITRON_BENCH_MODEL
     OPTITRON_RUN_BENCH (default 1) · OPTITRON_DRY_ACT (skip issue/post) · GITHUB_REPOSITORY
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optitroncore as C  # noqa: E402

REPO_HOME = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
EVENTS_PATH = os.path.join(STATE_DIR, "events.jsonl")
SKILL_PATH = os.path.join(REPO_HOME, ".claude", "skills", "vaked-optitron", "SKILL.md")
PURPOSE_PATH = os.path.join(HERE, "PURPOSE.md")
SOURCES_PATH = os.path.join(HERE, "sources.json")
TOOT_PATH = os.path.join(REPO_HOME, ".github", "social", "toot.txt")
TELEGRAM_PATH = os.path.join(REPO_HOME, ".github", "social", "telegram.txt")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Web-enabled crawl + skeptical reasoning verifier + cheap bench coder. All overridable.
CRAWL_MODEL = os.environ.get("OPTITRON_CRAWL_MODEL", "openai/gpt-oss-120b:online")
VERIFY_MODEL = os.environ.get("OPTITRON_VERIFY_MODEL", "qwen/qwen3-235b-a22b-thinking-2507")
BENCH_MODEL = os.environ.get("OPTITRON_BENCH_MODEL", "deepseek/deepseek-v4-flash")

# Per-1M-token (prompt, completion) — rough; the budget cap is the real guard.
PRICES = {
    "openai/gpt-oss-120b": (0.10, 0.50),
    "openai/gpt-oss-120b:online": (0.10, 0.50),
    "qwen/qwen3-235b-a22b-thinking-2507": (0.15, 0.85),
    "deepseek/deepseek-v4-flash": (0.20, 0.40),
}


# ---------------------------------------------------------------------------
# CI logging
# ---------------------------------------------------------------------------

def notice(msg: str) -> None:
    print(f"::notice::optitron: {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"::warning::optitron: {msg}", flush=True)


def summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Secrets / endpoints / Langfuse (mirrors ralph)
# ---------------------------------------------------------------------------

def api_key() -> str:
    return os.environ.get("RALPH_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""


def base_url() -> str:
    return os.environ.get("OPTITRON_BASE_URL") or OPENROUTER_URL


_LF = None
_LF_INIT = False


def _langfuse():
    global _LF, _LF_INIT
    if _LF_INIT:
        return _LF
    _LF_INIT = True
    try:
        if os.environ.get("LANGFUSE_PUBLIC_KEY"):
            from langfuse import Langfuse  # reads LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST
            _LF = Langfuse()
    except Exception:
        _LF = None
    return _LF


def _flush_langfuse() -> None:
    lf = _langfuse()
    if lf is not None:
        try:
            lf.flush()
        except Exception:
            pass


def cost_of(model: str, usage: dict) -> float:
    p_in, p_out = PRICES.get(model, PRICES.get(model.split(":")[0], (0.5, 1.0)))
    pt = usage.get("prompt_tokens", 0) / 1_000_000
    ct = usage.get("completion_tokens", 0) / 1_000_000
    return pt * p_in + ct * p_out


def openrouter_call(model: str, messages: list[dict], *, temperature: float,
                    max_tokens: int, response_format: dict | None = None,
                    reasoning: dict | None = None, retries: int = 3,
                    span_name: str = "optitron.generation") -> dict:
    """One OpenRouter chat call (urllib, retry+backoff, optional Langfuse span)."""
    body: dict = {"model": model, "messages": messages, "temperature": temperature,
                  "top_p": 0.95, "max_tokens": max_tokens, "usage": {"include": True}}
    if response_format is not None:
        body["response_format"] = response_format
    if reasoning is not None:
        body["reasoning"] = reasoning
    data = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}

    lf = _langfuse()
    gen_cm = gen = None
    if lf is not None:
        try:
            gen_cm = lf.start_as_current_generation(
                name=span_name, model=model, input=messages,
                model_parameters={"temperature": temperature, "max_tokens": max_tokens})
            gen = gen_cm.__enter__()
        except Exception:
            gen_cm = gen = None

    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(base_url(), data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
            if gen is not None:
                try:
                    out = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
                    gen.update(output=out, usage_details=parsed.get("usage"))
                except Exception:
                    pass
            if gen_cm is not None:
                try:
                    gen_cm.__exit__(None, None, None)
                except Exception:
                    pass
            return parsed
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt)
    if gen_cm is not None:
        try:
            gen_cm.__exit__(None, None, None)
        except Exception:
            pass
    raise RuntimeError(f"openrouter_call({model}) failed after {retries}: {last}")


def call_json(model: str, messages: list[dict], schema: dict, *, max_tokens: int,
              reasoning: dict | None = None) -> "tuple[dict, float]":
    """A structured-output call → (parsed-json, cost). Tolerant of fenced JSON."""
    resp = openrouter_call(model, messages, temperature=0.2, max_tokens=max_tokens,
                           response_format=schema, reasoning=reasoning)
    cost = cost_of(model, resp.get("usage", {}) or {})
    content = resp.get("choices", [{}])[0].get("message", {}).get("content", "") or "{}"
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1].lstrip("json").strip() if "```" in content else content
    try:
        return json.loads(content), cost
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start:end + 1]), cost
        raise


# ---------------------------------------------------------------------------
# Ledger (load → verify → append; fsync). Findings memory + tamper-evidence.
# ---------------------------------------------------------------------------

def load_events() -> list[dict]:
    if not os.path.exists(EVENTS_PATH):
        return []
    out: list[dict] = []
    with open(EVENTS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_event(payload: dict) -> dict:
    os.makedirs(STATE_DIR, exist_ok=True)
    events = load_events()
    if not C.verify_chain(events):
        events = C.longest_valid_prefix(events)  # torn tail — keep valid prefix
    prev = events[-1]["hash"] if events else C.GENESIS_HASH
    entry = C.make_entry(prev, len(events), payload)
    with open(EVENTS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return entry


def prior_titles() -> list[str]:
    titles: list[str] = []
    for e in load_events():
        p = e.get("payload", {})
        if p.get("event") in ("found", "rejected") and p.get("title"):
            titles.append(p["title"])
    return titles


# ---------------------------------------------------------------------------
# Deterministic novelty — already applied in THIS repo?
# ---------------------------------------------------------------------------

def known_in_repo(signature: str) -> bool:
    sig = (signature or "").strip()
    if len(sig) < 4:
        return False
    try:
        r = subprocess.run(["git", "-C", REPO_HOME, "grep", "-qiF", sig],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------------------
# Benchmark runner — compile + run the model's micro-bench, parse the sentinel.
# Honest gate: if no toolchain / no green run, bench is None → finding abstains.
# ---------------------------------------------------------------------------

def run_bench(lang: str, source: str) -> "dict | None":
    if os.environ.get("OPTITRON_RUN_BENCH", "1") != "1":
        return None
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        if lang == "rust":
            src, exe = os.path.join(d, "b.rs"), os.path.join(d, "b")
            compile_cmd = ["rustc", "-O", "-o", exe, src]
        elif lang == "c":
            src, exe = os.path.join(d, "b.c"), os.path.join(d, "b")
            compile_cmd = ["cc", "-O2", "-o", exe, src]
        else:
            return None
        try:
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(source)
            cp = subprocess.run(compile_cmd, capture_output=True, timeout=120)
            if cp.returncode != 0:
                warn(f"bench compile failed: {cp.stderr.decode('utf-8', 'replace')[:200]}")
                return None
            rp = subprocess.run([exe], capture_output=True, timeout=25)
            if rp.returncode != 0:
                warn("bench run nonzero exit")
                return None
            return C.parse_bench_output(rp.stdout.decode("utf-8", "replace"))
        except (OSError, subprocess.SubprocessError) as e:
            warn(f"bench error: {e}")
            return None


# ---------------------------------------------------------------------------
# Act — the swe_af hand-off + announcements (all gated behind a passing finding)
# ---------------------------------------------------------------------------

def gh(args: list[str]) -> "str | None":
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            warn(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[:200]}")
            return None
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        warn(f"gh error: {e}")
        return None


def issue_body(cand: dict, verify: dict, bench: dict, adj: dict) -> str:
    srcs = "\n".join(f"- [{s.get('kind')}] {s.get('org')}: {s.get('url')}\n  > {s.get('quote')}"
                     for s in cand.get("sources", []))
    return (
        f"**Optimization (optitron finding):** {cand.get('title')}\n\n"
        f"**Area:** `{cand.get('area')}` · **Confidence:** {adj.get('confidence'):.2f} · "
        f"**Hallucination risk:** {adj.get('hallucination_risk')}\n\n"
        f"## Mechanism\n{cand.get('mechanism')}\n\n"
        f"## Measured\nbaseline `{bench['baseline_ns']:.0f}ns` → optimized "
        f"`{bench['optimized_ns']:.0f}ns` (**{bench['delta']*100:.1f}%** faster, reproduced)\n\n"
        f"## Independent sources ({verify.get('independent_count')})\n{srcs}\n\n"
        f"## Cross-check\n{verify.get('rationale')}\n\n"
        f"_Filed by vaked-optitron. Labelled `agent` to hand off to the swe_af "
        f"workflow (plan → code → review → publish). Re-verify the benchmark before "
        f"implementing._\n"
    )


def create_agent_issue(title: str, body: str) -> "str | None":
    """Open the issue labelled `agent` — swe_af's documented trigger."""
    if os.environ.get("OPTITRON_DRY_ACT"):
        notice("DRY_ACT: would open `agent` issue:\n" + title)
        return "dry-run://issue"
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
        bf = fh.name
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    args = ["issue", "create", "--title", title, "--body-file", bf, "--label", "agent"]
    if repo:
        args += ["--repo", repo]
    url = gh(args)
    try:
        os.unlink(bf)
    except OSError:
        pass
    return url


def announce(cand: dict, bench: dict, issue_url: str) -> None:
    """Stage a Mastodon toot + Telegram message; the push triggers the post workflows."""
    if os.environ.get("OPTITRON_DRY_ACT"):
        notice("DRY_ACT: would announce to Mastodon + Telegram")
        return
    pct = f"{bench['delta']*100:.0f}%"
    toot = (f"optitron found a {cand.get('area')} optimization: {cand.get('title')}. "
            f"{pct} faster on a reproduced micro-bench, {2}+ independent sources. "
            f"Handed to swe_af. {issue_url}")[:480]
    tg = (f"🛰️ optitron finding ({cand.get('area')}): {cand.get('title')}\n"
          f"{pct} faster (reproduced) · handed to swe_af\n{issue_url}")
    for path, text in ((TOOT_PATH, toot), (TELEGRAM_PATH, tg)):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as e:
            warn(f"staging {path} failed: {e}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _read(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return default


def cmd_crawl(args) -> int:
    skill = _read(SKILL_PATH, "You are vaked-optitron, a strict optimization crawler.")
    purpose = _read(PURPOSE_PATH, "Find ONE novel, proven optimization or nothing.")
    cfg = json.loads(_read(SOURCES_PATH, "{}") or "{}")
    sources_hint = cfg.get("hint", "arXiv; LLVM/Cranelift/Zig/Rust release notes & RFCs; "
                                   "mimalloc/snmalloc/tcmalloc papers; godbolt/bench write-ups.")
    min_sources = cfg.get("min_sources", 2)
    min_conf = cfg.get("min_confidence", 0.80)
    min_delta = cfg.get("min_bench_delta", 0.10)
    budget = float(args.budget_total)

    crawl_msgs = C.build_crawl_messages(skill, purpose, sources_hint, prior_titles())

    if args.dry_run:
        est = 0.0
        for m, toks in ((CRAWL_MODEL, 30_000), (VERIFY_MODEL, 12_000), (BENCH_MODEL, 8_000)):
            est += cost_of(m, {"prompt_tokens": toks, "completion_tokens": toks // 2})
        print("=== optitron dry-run ===")
        print(f"crawl model: {CRAWL_MODEL}\nverify: {VERIFY_MODEL}\nbench: {BENCH_MODEL}")
        print(f"gate: >={min_sources} independent sources, bench delta >={min_delta*100:.0f}%, "
              f"confidence >={min_conf}")
        print(f"per-candidate est ~${est:.3f}; daily hard cap ${budget:.2f}")
        print("--- crawl prompt (system=SKILL.md) ---")
        print(crawl_msgs[1]["content"][:1200])
        return 0

    if not api_key():
        notice("no API key (OPENROUTER_API_KEY/RALPH_API_KEY) — skipping")
        return 0

    spent = 0.0
    funnel = {"crawled": 0, "novel": 0, "confirmed": 0, "found": 0}
    try:
        cands_raw, c = call_json(CRAWL_MODEL, crawl_msgs, C.CRAWL_SCHEMA, max_tokens=4000)
        spent += c
        candidates = [x for x in cands_raw.get("candidates", []) if C.in_scope(x.get("area", ""))]
        funnel["crawled"] = len(candidates)
        append_event({"event": "crawl", "candidates": len(candidates), "cost": round(spent, 5)})
        notice(f"crawled {len(candidates)} in-scope candidates (${spent:.4f})")
    except Exception as e:  # noqa: BLE001
        warn(f"crawl failed: {e}")
        append_event({"event": "error", "stage": "crawl", "msg": str(e)[:200]})
        return 0

    for cand in candidates:
        title = cand.get("title", "?")
        if spent >= budget:
            notice(f"budget cap ${budget:.2f} reached — stopping")
            break
        # 2. novelty (deterministic + ledger dedupe)
        if cand.get("signature") and known_in_repo(cand["signature"]):
            append_event({"event": "rejected", "title": title, "reason": "known-in-repo"})
            continue
        if title in prior_titles():
            append_event({"event": "rejected", "title": title, "reason": "already-found"})
            continue
        if not C.sources_independent(cand.get("sources", []), min_sources):
            append_event({"event": "rejected", "title": title, "reason": "sources-not-independent"})
            continue
        funnel["novel"] += 1
        # 3. adversarial cross-check
        try:
            verify, c = call_json(VERIFY_MODEL, C.build_verify_messages(skill, cand),
                                  C.VERIFY_SCHEMA, max_tokens=2000,
                                  reasoning={"enabled": True, "effort": "medium"})
            spent += c
        except Exception as e:  # noqa: BLE001
            append_event({"event": "rejected", "title": title, "reason": f"verify-error:{e}"[:120]})
            continue
        if not verify.get("independent") or not verify.get("claim_supported"):
            append_event({"event": "rejected", "title": title, "reason": "cross-check-failed"})
            continue
        funnel["confirmed"] += 1
        # 4. benchmark
        bench = None
        try:
            bspec, c = call_json(BENCH_MODEL, C.build_bench_messages(skill, cand),
                                 C.BENCH_SCHEMA, max_tokens=3000)
            spent += c
            bench = run_bench(bspec.get("lang", ""), bspec.get("source", ""))
        except Exception as e:  # noqa: BLE001
            warn(f"bench stage error: {e}")
        # 5. adjudicate
        try:
            adj, c = call_json(VERIFY_MODEL, C.build_adjudicate_messages(skill, cand, verify, bench or {}),
                               C.ADJUDICATE_SCHEMA, max_tokens=1200,
                               reasoning={"enabled": True, "effort": "medium"})
            spent += c
        except Exception as e:  # noqa: BLE001
            append_event({"event": "rejected", "title": title, "reason": f"adjudicate-error:{e}"[:120]})
            continue
        passed, reason = C.passes_gate(verify=verify, bench=bench, adjudication=adj,
                                       min_sources=min_sources, min_confidence=min_conf,
                                       min_delta=min_delta)
        if not passed:
            append_event({"event": "rejected", "title": title, "reason": reason,
                          "confidence": adj.get("confidence")})
            notice(f"rejected '{title}': {reason}")
            continue
        # 6. ACT — gated, certain finding
        body = issue_body(cand, verify, bench, adj)
        url = create_agent_issue(f"[optitron] {title}", body) or "(issue-create-failed)"
        announce(cand, bench, url)
        append_event({"event": "found", "title": title, "area": cand.get("area"),
                      "confidence": adj.get("confidence"), "delta": bench["delta"],
                      "issue": url, "cost": round(spent, 5)})
        funnel["found"] = 1
        notice(f"FOUND '{title}' → {url} ({bench['delta']*100:.1f}% faster, "
               f"conf {adj.get('confidence'):.2f})")
        break  # one finding per run — that is the job

    if funnel["found"] == 0:
        append_event({"event": "none", "crawled": funnel["crawled"], "cost": round(spent, 5)})
        notice("no finding cleared the gate today (abstaining — that is success)")
    summary(f"## optitron crawl\n\nfunnel: {funnel['crawled']} crawled → {funnel['novel']} novel "
            f"→ {funnel['confirmed']} confirmed → **{funnel['found']} found**\n\n"
            f"spend: ${spent:.4f} / ${budget:.2f} cap")
    _flush_langfuse()
    return 0


def cmd_events(args) -> int:
    events = load_events()
    ok = C.verify_chain(events)
    found = [e["payload"] for e in events if e["payload"].get("event") == "found"]
    print(f"events: {len(events)} · chain {'OK' if ok else 'BROKEN'} · findings: {len(found)}")
    if args.replay:
        for p in found:
            print(f"  - {p.get('title')} ({p.get('area')}, {p.get('delta', 0)*100:.0f}%) {p.get('issue')}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="optitron")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("crawl")
    pc.add_argument("--once", action="store_true")
    pc.add_argument("--dry-run", action="store_true")
    pc.add_argument("--budget-total", default=os.environ.get("OPTITRON_BUDGET", "4.0"))
    pc.set_defaults(fn=cmd_crawl)
    pe = sub.add_parser("events")
    pe.add_argument("--replay", action="store_true")
    pe.set_defaults(fn=cmd_events)
    args = ap.parse_args()
    try:
        return args.fn(args)
    except Exception as e:  # noqa: BLE001 — advisory: never hard-fail CI
        warn(f"unhandled: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
