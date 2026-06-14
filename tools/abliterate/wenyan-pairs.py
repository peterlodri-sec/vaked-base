#!/usr/bin/env python3
"""
Generate wenyan-ultra ↔ normal pairs for mlx-tune fine-tuning.

Uses the cuc-bench corpus + two existing bench reports (normal vs wenyan-ultra)
to build a JSONL training dataset compatible with mlx-tune / mlx-lm LoRA format.

Output: tools/abliterate/wenyan-pairs.jsonl
Format: {"text": "<s>[INST] {prompt_text} [/INST] {wenyan_response}</s>"}

The model has already been verbosity-ablated by Heretic; this LoRA teaches it
to use cuc-style compression natively — recovering benchmark accuracy while
keeping the compression as a default style.

Usage:
    python3 tools/abliterate/wenyan-pairs.py [--report path/to/report-*.md]
"""

import json
import re
import sys
import pathlib
import argparse

HERE = pathlib.Path(__file__).parent
REPO_ROOT = HERE.parent.parent
CORPUS_PATH = REPO_ROOT / "tools" / "cuc-bench" / "corpus.py"


def load_corpus():
    import importlib.util
    spec = importlib.util.spec_from_file_location("corpus", CORPUS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PROMPTS


def extract_responses_from_report(report_path: pathlib.Path) -> dict:
    """Parse a cuc-bench markdown report, return {prompt_id: {normal: str, wenyan: str}}."""
    text = report_path.read_text()
    results = {}
    # Match "### <id> (<category>)" sections
    sections = re.split(r"\n### ([^\n(]+) \([^)]+\)\n", text)
    # sections[0] = header, then alternating: id, content, id, content...
    for i in range(1, len(sections), 2):
        prompt_id = sections[i].strip()
        content = sections[i + 1] if i + 1 < len(sections) else ""
        normal_match = re.search(r"\*\*Normal:\*\*\n```\n(.*?)\n```", content, re.DOTALL)
        wenyan_match = re.search(r"\*\*Wenyan-ultra:\*\*\n```\n(.*?)\n```", content, re.DOTALL)
        if normal_match and wenyan_match:
            results[prompt_id] = {
                "normal": normal_match.group(1).strip(),
                "wenyan": wenyan_match.group(1).strip(),
            }
    return results


def build_pairs(prompts: list, responses: dict) -> list:
    """Build instruction-tuning pairs using wenyan response as target."""
    pairs = []
    for p in prompts:
        pid = p["id"]
        if pid not in responses:
            continue
        wenyan = responses[pid]["wenyan"]
        if not wenyan or wenyan.startswith("ERROR:"):
            continue
        pairs.append({
            "text": f"<s>[INST] {p['text']} [/INST] {wenyan}</s>"
        })
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=pathlib.Path,
                        help="Path to a cuc-bench report-*.md file")
    parser.add_argument("--out", type=pathlib.Path,
                        default=HERE / "wenyan-pairs.jsonl")
    args = parser.parse_args()

    if args.report:
        report_paths = [args.report]
    else:
        # Use all available reports
        report_paths = list((REPO_ROOT / "tools" / "cuc-bench").glob("report-*.md"))
        # Prefer llama report (highest gate compliance)
        llama = [p for p in report_paths if "llama" in p.name]
        report_paths = llama if llama else report_paths

    if not report_paths:
        print("No reports found. Run tools/cuc-bench/bench.py first.", file=sys.stderr)
        sys.exit(1)

    prompts = load_corpus()
    all_pairs = []
    for rp in report_paths:
        print(f"Parsing: {rp.name}")
        responses = extract_responses_from_report(rp)
        pairs = build_pairs(prompts, responses)
        all_pairs.extend(pairs)
        print(f"  {len(pairs)} pairs extracted")

    # Deduplicate by text
    seen = set()
    unique = []
    for p in all_pairs:
        if p["text"] not in seen:
            seen.add(p["text"])
            unique.append(p)

    args.out.write_text("\n".join(json.dumps(p) for p in unique) + "\n")
    print(f"\nWrote {len(unique)} pairs → {args.out}")
    print("Next: bash tools/abliterate/finetune-mlx.sh llama")


if __name__ == "__main__":
    main()
