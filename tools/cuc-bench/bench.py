#!/usr/bin/env python3
"""
Benchmark: CUC (caveman ultra chinese) wenyan-ultra vs normal (default) mode.

Measures output token count and artifact English accuracy across 8 prompts.
Writes results to report-<model>.md in the same directory.

Backends (priority order):
  - Anthropic API:   ANTHROPIC_API_KEY env var, model claude-sonnet-4-6
  - OpenRouter API:  OPENROUTER_API_KEY env var, model via BENCH_MODEL env var
  - OpenAI API:      OPENAI_API_KEY env var, model gpt-4o-mini

Usage:
    ANTHROPIC_API_KEY=sk-ant-...    python3 tools/cuc-bench/bench.py
    OPENAI_API_KEY=sk-...           python3 tools/cuc-bench/bench.py
    OPENROUTER_API_KEY=sk-or-...  \\
      BENCH_MODEL=deepseek/deepseek-r1  python3 tools/cuc-bench/bench.py
"""

import json
import os
import pathlib
import re
import sys
import time
import urllib.request
import urllib.error
import importlib.util

# ---------------------------------------------------------------------------
# Load corpus
# ---------------------------------------------------------------------------
_here = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("corpus", _here / "corpus.py")
corpus_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus_mod)
PROMPTS = corpus_mod.PROMPTS

# ---------------------------------------------------------------------------
# Caveman wenyan-ultra system prompt
# ---------------------------------------------------------------------------
WENYAN_SYSTEM = """\
You are in wenyan-ultra mode. This is a mandatory, persistent communication style.

Rules:
- ALL chat responses use classical Chinese ultra-compression (文言超縮).
- Maximum compression: omit subjects when clear, use classical particles (之/乃/為/其/則/故), \
arrows for causality (X→Y), one character/word when one is enough.
- Technical terms, code symbols, function names, API names, CLI commands, error strings: \
NEVER translate or compress — keep verbatim.
- No filler, no hedging, no pleasantries.

ARTIFACT GATE (mandatory):
When producing content that will be written to a file, a git commit message, a PR title/body, \
or any text persisted externally, output standard English — complete sentences, normal articles, \
no classical Chinese compression. Gate applies to: file content, commit messages, PR descriptions, \
issue bodies. Does NOT apply to chat replies (those stay wenyan-ultra).
"""

NORMAL_SYSTEM = (
    "You are a helpful, knowledgeable software engineering assistant. "
    "Reply clearly and concisely in standard English."
)

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------
def detect_backend():
    if os.environ.get("OLLAMA_HOST"):
        return "ollama", os.environ["OLLAMA_HOST"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter", os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"]
    return None, None


# ---------------------------------------------------------------------------
# API calls via urllib (no SDK dependency)
# ---------------------------------------------------------------------------
def call_anthropic(api_key: str, system: str, user: str) -> dict:
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return {
        "text": data["content"][0]["text"],
        "input_tokens": data["usage"]["input_tokens"],
        "output_tokens": data["usage"]["output_tokens"],
        "model": data["model"],
    }


SINGLE_TURN_MODELS = {"morph/morph-v3-large", "morph/morph-v3"}


def call_openrouter(api_key: str, system: str, user: str) -> dict:
    model = os.environ.get("BENCH_MODEL", "deepseek/deepseek-r1")
    # Models that reject multi-turn / system messages — fold system into user.
    if model in SINGLE_TURN_MODELS:
        messages = [{"role": "user", "content": f"{system}\n\n---\n\n{user}"}]
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    payload = json.dumps({
        "model": model,
        "max_tokens": 2048,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "HTTP-Referer": "https://github.com/peterlodri-sec/vaked-base",
            "X-Title": "cuc-bench",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    choice = data["choices"][0]["message"]["content"]
    usage = data["usage"]
    return {
        "text": choice,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "model": data.get("model", model),
    }


def call_openai(api_key: str, system: str, user: str) -> dict:
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    choice = data["choices"][0]["message"]["content"]
    usage = data["usage"]
    return {
        "text": choice,
        "input_tokens": usage["prompt_tokens"],
        "output_tokens": usage["completion_tokens"],
        "model": data["model"],
    }


def call_ollama(host_url: str, system: str, user: str) -> dict:
    model = os.environ.get("BENCH_MODEL", "llama3.3:70b-instruct-q4_K_M")
    payload = json.dumps({
        "model": model,
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{host_url.rstrip('/')}/v1/chat/completions",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unreachable at {host_url}: {exc}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Ollama returned no choices: {data}")
    choice = choices[0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "text": choice,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", len(choice.split())),
        "model": data.get("model", model),
    }


def call_api(backend: str, api_key_or_url: str, system: str, user: str) -> dict:
    if backend == "ollama":
        return call_ollama(api_key_or_url, system, user)
    if backend == "anthropic":
        return call_anthropic(api_key_or_url, system, user)
    if backend == "openrouter":
        return call_openrouter(api_key_or_url, system, user)
    return call_openai(api_key_or_url, system, user)


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------
def run_benchmark(backend: str, api_key: str) -> list:
    results = []
    modes = [("normal", NORMAL_SYSTEM), ("wenyan-ultra", WENYAN_SYSTEM)]
    total = len(PROMPTS) * len(modes)
    done = 0
    for prompt in PROMPTS:
        row = {
            "id": prompt["id"],
            "category": prompt["category"],
            "is_artifact": prompt["is_artifact"],
        }
        for mode_name, system in modes:
            print(f"  [{done+1}/{total}] {prompt['id']} / {mode_name} ...", flush=True)
            try:
                result = call_api(backend, api_key, system, prompt["text"])
                row[f"{mode_name}_input_tok"] = result["input_tokens"]
                row[f"{mode_name}_output_tok"] = result["output_tokens"]
                row[f"{mode_name}_chars"] = len(result["text"])
                row[f"{mode_name}_text"] = result["text"]
                row["model"] = result["model"]
                if prompt["is_artifact"]:
                    row[f"{mode_name}_artifact_english"] = not has_cjk(result["text"])
            except Exception as exc:
                print(f"    ERROR: {exc}", file=sys.stderr)
                row[f"{mode_name}_input_tok"] = 0
                row[f"{mode_name}_output_tok"] = 0
                row[f"{mode_name}_chars"] = 0
                row[f"{mode_name}_text"] = f"ERROR: {exc}"
                if prompt["is_artifact"]:
                    row[f"{mode_name}_artifact_english"] = None
            done += 1
            time.sleep(0.4)
        results.append(row)
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def build_report(results: list, backend: str) -> str:
    model = results[0].get("model", "unknown") if results else "unknown"
    lines = [
        "# CUC (Caveman Ultra Chinese) — Wenyan-Ultra vs Normal Benchmark Report",
        "",
        f"**Backend:** {backend} | **Model:** `{model}` | **Prompts:** {len(results)}",
        "",
        "## Per-Prompt Token Comparison",
        "",
        "| ID | Category | Normal tok | Wenyan tok | Savings % | Normal chars | Wenyan chars |",
        "|----|----------|-----------|-----------|-----------|-------------|-------------|",
    ]

    total_normal_tok = 0
    total_wenyan_tok = 0
    total_normal_chars = 0
    total_wenyan_chars = 0

    for r in results:
        n_tok = r.get("normal_output_tok", 0)
        w_tok = r.get("wenyan-ultra_output_tok", 0)
        n_ch = r.get("normal_chars", 0)
        w_ch = r.get("wenyan-ultra_chars", 0)
        savings_tok = (n_tok - w_tok) / n_tok * 100 if n_tok else 0
        total_normal_tok += n_tok
        total_wenyan_tok += w_tok
        total_normal_chars += n_ch
        total_wenyan_chars += w_ch
        lines.append(
            f"| {r['id']} | {r['category']} | {n_tok} | {w_tok} | {savings_tok:+.1f}% "
            f"| {n_ch} | {w_ch} |"
        )

    agg_tok = (total_normal_tok - total_wenyan_tok) / total_normal_tok * 100 if total_normal_tok else 0
    agg_ch = (total_normal_chars - total_wenyan_chars) / total_normal_chars * 100 if total_normal_chars else 0

    lines += [
        "",
        f"**Aggregate output token savings: {agg_tok:.1f}%** "
        f"(normal={total_normal_tok} tok, wenyan={total_wenyan_tok} tok)",
        f"**Character reduction: {agg_ch:.1f}%** "
        f"(normal={total_normal_chars} chars, wenyan={total_wenyan_chars} chars)",
        "",
        "## Artifact Gate Accuracy",
        "",
        "Artifact prompts in wenyan-ultra mode must contain **no CJK characters** in the response.",
        "",
        "| ID | Normal English? | Wenyan English? | Gate |",
        "|----|----------------|-----------------|------|",
    ]

    artifact_rows = [r for r in results if r["is_artifact"]]
    all_pass = True
    for r in artifact_rows:
        n_eng = r.get("normal_artifact_english", True)
        w_eng = r.get("wenyan-ultra_artifact_english")
        if w_eng is None:
            passed = "?"
        elif w_eng:
            passed = "✓ PASS"
        else:
            passed = "✗ FAIL"
            all_pass = False
        lines.append(
            f"| {r['id']} | {'yes' if n_eng else 'no'} "
            f"| {'yes' if w_eng else ('NO — CJK found' if w_eng is False else 'error')} "
            f"| {passed} |"
        )

    gate_result = "PASS — all artifacts in English" if all_pass else "FAIL — CJK found in artifact"
    lines += [
        "",
        f"**Artifact gate: {gate_result}**",
        "",
        "## Sample Responses (first 400 chars)",
        "",
    ]

    for r in results:
        lines += [
            f"### {r['id']} ({r['category']})",
            "",
            "**Normal:**",
            "```",
            r.get("normal_text", "")[:400].replace("```", "'''"),
            "```",
            "",
            "**Wenyan-ultra:**",
            "```",
            r.get("wenyan-ultra_text", "")[:400].replace("```", "'''"),
            "```",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    backend, api_key = detect_backend()
    if not backend:
        print("ERROR: set OLLAMA_HOST, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    print(f"Backend: {backend}")
    print(f"Prompts: {len(PROMPTS)} × 2 modes = {len(PROMPTS)*2} API calls")
    print()

    results = run_benchmark(backend, api_key)
    report = build_report(results, backend)

    model_slug = results[0].get("model", "unknown").replace("/", "-").replace(":", "-")
    out_path = _here / f"report-{model_slug}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport: {out_path}")

    total_n = sum(r.get("normal_output_tok", 0) for r in results)
    total_w = sum(r.get("wenyan-ultra_output_tok", 0) for r in results)
    savings = (total_n - total_w) / total_n * 100 if total_n else 0
    print(f"Token savings: {savings:.1f}%")

    artifacts = [r for r in results if r["is_artifact"]]
    gate = all(r.get("wenyan-ultra_artifact_english", False) for r in artifacts)
    print(f"Artifact gate: {'PASS' if gate else 'FAIL'}")


if __name__ == "__main__":
    main()
