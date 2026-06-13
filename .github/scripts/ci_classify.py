#!/usr/bin/env python3
"""Classify a PR into a CI tier and emit GITHUB_OUTPUT variables.

Outputs:
  tier          smoke | standard | full | extended
  changed_groups  comma-separated set: language, nix, docs, agents, tools, tests, ci, other
  ping_owner    true | false
  run_nix_parse true | false   (nix paths changed, or tier >= full)
  run_nix_check true | false   (nix paths changed AND tier >= extended)

Tier logic (label wins over auto-detection):
  size/chore, size/tiny   → smoke     (grammar + doc smoke only)
  size/small, size/targeted → standard (smoke + core compiler)
  size/medium             → standard
  size/big                → full      (all 14 spec tests)
  size/ultra              → extended  (full + nix-check)
  ping-owner              → smoke + block flag (CI comments but doesn't gate)

Auto-detection from diff stats (when no size/* label):
  ≤20 net lines, only non-src paths  → smoke
  ≤20 net lines, any src             → standard
  ≤100 net lines                     → standard
  ≤400 net lines                     → full
  >400 net lines                     → extended
"""
import json
import os
import re
import subprocess
import sys

SIZE_TIERS = {
    "size/chore": "smoke",
    "size/tiny": "smoke",
    "size/small": "standard",
    "size/targeted": "standard",
    "size/medium": "standard",
    "size/big": "full",
    "size/ultra": "extended",
}

# Paths that are purely non-source (docs, config, ci scripts)
NON_SRC_PREFIXES = (
    "docs/", "protocol/", "prompts/", ".github/", "CLAUDE.md",
    "README", "CHANGELOG", "DEPLOY", "CONTRIBUTING", "SECURITY",
    "ROADMAP", "REVIEW_MAP", "VAKED_AGENTS",
)

PATH_GROUPS = {
    "language": ("vaked/", "vakedc/", "vakedz/"),
    "nix":      ("nix/", "hosts/", "flake.nix", "flake.lock"),
    "docs":     ("docs/", "protocol/", "prompts/", "examples/evaluation/"),
    "agents":   ("vaked-agents/",),
    "tools":    ("tools/",),
    "tests":    ("tests/",),
    "ci":       (".github/",),
}


def classify_paths(files):
    groups = set()
    for f in files:
        matched = False
        for group, prefixes in PATH_GROUPS.items():
            if any(f.startswith(p) or f == p.rstrip("/") for p in prefixes):
                groups.add(group)
                matched = True
                break
        if not matched:
            groups.add("other")
    return groups


def is_non_src(f):
    return any(f.startswith(p) or f == p.rstrip("/") for p in NON_SRC_PREFIXES)


def auto_tier(added, files):
    only_non_src = all(is_non_src(f) for f in files) if files else True
    if added <= 20 and only_non_src:
        return "smoke"
    if added <= 100:
        return "standard"
    if added <= 400:
        return "full"
    return "extended"


def git(*args):
    return subprocess.check_output(["git"] + list(args), text=True).strip()


def main():
    labels_raw = os.environ.get("PR_LABELS", "[]")
    try:
        labels = json.loads(labels_raw)
    except Exception:
        labels = []

    ping_owner = "ping-owner" in labels

    base_sha = os.environ.get("BASE_SHA", "")
    head_sha = os.environ.get("HEAD_SHA", "HEAD")

    if not base_sha:
        # Fallback: compare against parent
        try:
            base_sha = git("rev-parse", "HEAD~1")
        except Exception:
            base_sha = "HEAD~1"

    try:
        raw_files = git("diff", "--name-only", base_sha, head_sha)
        files = [f for f in raw_files.splitlines() if f]

        stat = git("diff", "--shortstat", base_sha, head_sha)
        m = re.search(r"(\d+) insertion", stat)
        added = int(m.group(1)) if m else 0
    except Exception as e:
        print(f"::warning::git diff failed ({e}); defaulting to full tier", file=sys.stderr)
        files, added = [], 999

    changed_groups = classify_paths(files)

    # Tier: label wins, then auto
    tier = None
    for label in labels:
        if label in SIZE_TIERS:
            tier = SIZE_TIERS[label]
            break
    if tier is None:
        tier = auto_tier(added, files)

    run_nix_parse = "nix" in changed_groups or tier in ("full", "extended")
    run_nix_check = "nix" in changed_groups and tier == "extended"

    # Write outputs
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    lines = [
        f"tier={tier}",
        f"changed_groups={','.join(sorted(changed_groups))}",
        f"ping_owner={'true' if ping_owner else 'false'}",
        f"run_nix_parse={'true' if run_nix_parse else 'false'}",
        f"run_nix_check={'true' if run_nix_check else 'false'}",
    ]
    if output_path:
        with open(output_path, "a") as fh:
            fh.write("\n".join(lines) + "\n")

    # Human-readable summary to stdout (visible in Actions log)
    print(f"tier:           {tier}")
    print(f"ping_owner:     {ping_owner}")
    print(f"added lines:    {added}")
    print(f"files changed:  {len(files)}")
    print(f"changed_groups: {sorted(changed_groups)}")
    print(f"run_nix_parse:  {run_nix_parse}")
    print(f"run_nix_check:  {run_nix_check}")
    print(f"size label:     {next((l for l in labels if l in SIZE_TIERS), '(auto)')}")


if __name__ == "__main__":
    main()
