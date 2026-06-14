#!/usr/bin/env python3
"""Generate compact context snapshot for vaked CI agents.

Reads GOALS.md, docs/context/TIMELINE.md, and tools/ralph/state/events.jsonl
from the repo root, emits a small markdown file (~500 chars) that captures
the essential project state without all the prose. Agents load this instead
of the full files, keeping the OpenRouter prompt-cache prefix stable.
"""

import json
import re
import sys
from pathlib import Path
from datetime import date

REPO = Path(__file__).resolve().parent.parent


def phase_status(goals: str) -> list[str]:
    lines = goals.splitlines()
    results = []
    current = current_title = None
    done = total = 0
    for line in lines:
        m = re.match(r"^### Phase (\d+) — (.+?)(?:\s*\*\(.+?\)\*)?$", line.strip())
        if m:
            if current is not None:
                mark = "✅" if done == total and total > 0 else ("🟡" if done > 0 else "⬜")
                results.append(f"Phase {current} {mark} ({done}/{total}): {current_title}")
            current = m.group(1)
            current_title = m.group(2).strip()
            done = total = 0
        elif current is not None and re.match(r"^- \[", line.strip()):
            total += 1
            if line.strip().startswith("- [x]"):
                done += 1
    if current is not None:
        mark = "✅" if done == total and total > 0 else ("🟡" if done > 0 else "⬜")
        results.append(f"Phase {current} {mark} ({done}/{total}): {current_title}")
    return results


def timeline_meta(timeline: str) -> str:
    for line in timeline.splitlines():
        if line.startswith("**Snapshot:**"):
            return line.strip()
    return ""


def ralph_decisions(events_path: Path, n: int = 5) -> list[str]:
    try:
        raw = events_path.read_text().splitlines()
    except FileNotFoundError:
        return []
    decides = []
    for line in reversed(raw):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            p = e.get("payload", {})
            if p.get("event") == "decide":
                cost = p.get("cost", 0.0)
                decides.append(f"  {p['track']} iter {p['iteration']} (${cost:.4f})")
                if len(decides) >= n:
                    break
        except (json.JSONDecodeError, KeyError):
            continue
    return list(reversed(decides))


def main() -> None:
    try:
        goals = (REPO / "GOALS.md").read_text()
    except FileNotFoundError:
        print("ERROR: GOALS.md not found", file=sys.stderr)
        sys.exit(1)

    timeline = (REPO / "docs/context/TIMELINE.md").read_text() if \
        (REPO / "docs/context/TIMELINE.md").exists() else ""
    events_path = REPO / "tools/ralph/state/events.jsonl"

    phases = phase_status(goals)
    meta = timeline_meta(timeline)
    decisions = ralph_decisions(events_path)

    out = [
        f"<!-- generated {date.today()} from GOALS.md · TIMELINE.md · events.jsonl"
        " — do not edit manually -->",
        "## Vaked project status",
        "",
    ]
    if meta:
        out += [meta, ""]

    out.append("### Phases")
    out.extend(f"- {p}" for p in phases)
    out.append("")

    if decisions:
        out.append("### Recent ralph decisions (last 5, chronological)")
        out.extend(decisions)
        out.append("")

    print("\n".join(out))


if __name__ == "__main__":
    main()
