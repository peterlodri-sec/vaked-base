#!/usr/bin/env python3
"""
Benchmark: caveman wenyan-ultra vs normal (default) mode.

Measures output token count and artifact English accuracy across 8 prompts.
Writes results to report.md in the same directory.

Usage:
    ANTHROPIC_API_KEY=sk-... python3 tools/caveman-bench/bench.py
"""

import os
import re
import sys
import time
import pathlib
import importlib.util

# ---------------------------------------------------------------------------
# Load corpus from sibling file without installing as a package
# ---------------------------------------------------------------------------
_here = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("corpus", _here / "corpus.py")
corpus_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus_mod)
PROMPTS = corpus_mod.PROMPTS

# ---------------------------------------------------------------------------
# Caveman wenyan-ultra system prompt — mirrors SKILL.md core rules
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
or any text persisted externally, you MUST output standard English — complete sentences, \
normal articles, no classical Chinese compression. This applies even in wenyan-ultra mode.
The gate applies to: file content, commit messages, PR descriptions, issue bodies.
It does NOT apply to your conversational replies (those stay wenyan-ultra).
"""

NORMAL_SYSTEM = """\
You are a helpful, knowledgeable software engineering assistant. \
Reply clearly and concisely in standard English.
"""

MODEL = "claude-sonnet-4-6"
CJK_RE = re.compile(r"[一-鿿㐀-䶿]")

# ---------------------------------------------------------------------------

def call_api(client, system: str, user: str) -> dict:
    """Single API call; returns {text, input_tokens, output_tokens}."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = msg.content[0].text
    return {
        "text": text,
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def run_benchmark(client) -> list[dict]:
    results = []
    modes = [
        ("normal", NORMAL_SYSTEM),
        ("wenyan-ultra", WENYAN_SYSTEM),
    ]
    total = len(PROMPTS) * len(modes)
    done = 0
    for prompt in PROMPTS:
        row = {"id": prompt["id"], "category": prompt["category"], "is_artifact": prompt["is_artifact"]}
        for mode_name, system in modes:
            print(f"  [{done+1}/{total}] {prompt['id']} / {mode_name} ...", flush=True)
            result = call_api(client, system, prompt["text"])
            row[f"{mode_name}_input_tok"] = result["input_tokens"]
            row[f"{mode_name}_output_tok"] = result["output_tokens"]
            row[f"{mode_name}_chars"] = len(result["text"])
            row[f"{mode_name}_text"] = result["text"]
            if prompt["is_artifact"]:
                row[f"{mode_name}_artifact_english"] = not has_cjk(result["text"])
            done += 1
            time.sleep(0.5)  # gentle rate limiting
        results.append(row)
    return results


def build_report(results: list[dict]) -> str:
    lines = [
        "# Caveman Wenyan-Ultra vs Normal — Benchmark Report",
        "",
        f"Model: `{MODEL}` | Prompts: {len(results)} | Date: run at script time",
        "",
        "## Per-Prompt Token Comparison",
        "",
        "| ID | Category | Normal out-tok | Wenyan out-tok | Savings % | Wenyan chars | Normal chars |",
        "|----|----------|---------------|----------------|-----------|--------------|--------------|",
    ]

    total_normal = 0
    total_wenyan = 0

    for r in results:
        n_tok = r["normal_output_tok"]
        w_tok = r["wenyan-ultra_output_tok"]
        savings = (n_tok - w_tok) / n_tok * 100 if n_tok else 0
        total_normal += n_tok
        total_wenyan += w_tok
        lines.append(
            f"| {r['id']} | {r['category']} | {n_tok} | {w_tok} | {savings:+.1f}% "
            f"| {r['wenyan-ultra_chars']} | {r['normal_chars']} |"
        )

    agg_savings = (total_normal - total_wenyan) / total_normal * 100 if total_normal else 0
    lines += [
        "",
        f"**Aggregate output token savings: {agg_savings:.1f}%** "
        f"(normal total={total_normal}, wenyan total={total_wenyan})",
        "",
        "## Artifact Gate Accuracy",
        "",
        "For artifact prompts, wenyan-ultra responses must contain no CJK characters.",
        "",
        "| ID | Normal English? | Wenyan English? | Pass |",
        "|----|----------------|-----------------|------|",
    ]

    artifact_rows = [r for r in results if r["is_artifact"]]
    all_pass = True
    for r in artifact_rows:
        n_eng = r.get("normal_artifact_english", True)
        w_eng = r.get("wenyan-ultra_artifact_english", False)
        passed = "✓" if w_eng else "✗ FAIL"
        if not w_eng:
            all_pass = False
        lines.append(f"| {r['id']} | {'yes' if n_eng else 'no'} | {'yes' if w_eng else 'NO — CJK FOUND'} | {passed} |")

    lines += [
        "",
        f"**Artifact gate result: {'PASS — all artifacts in English' if all_pass else 'FAIL — CJK found in artifact output'}**",
        "",
        "## Sample Responses",
        "",
    ]

    for r in results:
        lines += [
            f"### {r['id']} ({r['category']})",
            "",
            "**Normal:**",
            "```",
            r["normal_text"][:600] + ("..." if len(r["normal_text"]) > 600 else ""),
            "```",
            "",
            "**Wenyan-ultra:**",
            "```",
            r["wenyan-ultra_text"][:600] + ("..." if len(r["wenyan-ultra_text"]) > 600 else ""),
            "```",
            "",
        ]

    return "\n".join(lines)


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Running benchmark: {len(PROMPTS)} prompts × 2 modes = {len(PROMPTS)*2} API calls")
    print(f"Model: {MODEL}")
    print()

    results = run_benchmark(client)
    report = build_report(results)

    out_path = _here / "report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {out_path}")

    # Also print aggregate to stdout
    total_normal = sum(r["normal_output_tok"] for r in results)
    total_wenyan = sum(r["wenyan-ultra_output_tok"] for r in results)
    savings = (total_normal - total_wenyan) / total_normal * 100 if total_normal else 0
    print(f"Aggregate output token savings: {savings:.1f}%")

    artifact_rows = [r for r in results if r["is_artifact"]]
    gate_pass = all(r.get("wenyan-ultra_artifact_english", False) for r in artifact_rows)
    print(f"Artifact gate: {'PASS' if gate_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
