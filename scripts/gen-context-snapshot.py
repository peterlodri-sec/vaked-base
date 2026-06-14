#!/usr/bin/env python3
"""Generate compact context snapshot for vaked CI agents.

Scans GOALS.md, TIMELINE.md, protocol/rfcs/, ROADMAP, and
tools/ralph/state/events.jsonl → emits ~1.5KB markdown that agents
load instead of the full 10K of GOALS + TIMELINE. Keeps prompt-cache
prefix stable between runs.
"""

import json
import re
import sys
from pathlib import Path
from datetime import date

REPO = Path(__file__).resolve().parent.parent

# Stable project metadata (updated manually when tracks/labels change).
RALPH_TRACKS = [
    "base-language-spec",
    "graph-concept",
    "mlir-topology",
    "hcp-litany",
]

AREA_LABELS = {
    "area/language":  "vaked/ grammar · schema · examples",
    "area/compiler":  "vakedc/ parse → check → lower",
    "area/docs":      "docs/ design series · context · references",
    "area/protocol":  "protocol/ HCP/Litany RFCs · wire formats",
    "area/runtime":   "daemons/ OTP · Zig · eBPF",
    "area/agents":    "vaked-agents/ CI + fleet agents",
}


# ── GOALS.md ────────────────────────────────────────────────────────────────

def phase_status(goals: str) -> list[str]:
    lines = goals.splitlines()
    results, current, current_title = [], None, None
    done = total = 0
    for line in lines:
        m = re.match(r"^### Phase (\d+) — (.+?)(?:\s*\*\(.+?\)\*)?$", line.strip())
        if m:
            if current is not None:
                mark = "✅" if done == total and total > 0 else ("🟡" if done > 0 else "⬜")
                results.append(f"Phase {current} {mark} ({done}/{total}): {current_title}")
            current, current_title = m.group(1), m.group(2).strip()
            done = total = 0
        elif current is not None and re.match(r"^- \[", line.strip()):
            total += 1
            if line.strip().startswith("- [x]"):
                done += 1
    if current is not None:
        mark = "✅" if done == total and total > 0 else ("🟡" if done > 0 else "⬜")
        results.append(f"Phase {current} {mark} ({done}/{total}): {current_title}")
    return results


# ── TIMELINE.md ─────────────────────────────────────────────────────────────

def timeline_meta(timeline: str) -> str:
    for line in timeline.splitlines():
        if line.startswith("**Snapshot:**"):
            return line.strip()
    return ""


# ── protocol/rfcs/ ──────────────────────────────────────────────────────────

def rfc_list(rfc_dir: Path) -> list[str]:
    result = []
    for f in sorted(rfc_dir.glob("*.md")):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        title = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        if title:
            result.append(f"  {f.stem[:4]} {title}")
    return result


# ── ROADMAP_2026-2027.md ────────────────────────────────────────────────────

def wp_status(roadmap: str) -> list[str]:
    rows = []
    for line in roadmap.splitlines():
        # Match WP table rows: | **WP1** | ... | ✅/⏳/📋 ... |
        m = re.match(r"\|\s*\*\*WP(\d+)\*\*\s*\|([^|]+)\|([^|]+)\|[^|]*\|([^|]+)\|", line)
        if m:
            num, component, status, timeline = (
                m.group(1).strip(),
                m.group(2).strip(),
                m.group(3).strip(),
                m.group(4).strip(),
            )
            # Collapse to first meaningful word of status
            status_short = status.split()[0] if status else "?"
            rows.append(f"  WP{num} {status_short}: {component} ({timeline.strip('—').strip() or 'n/a'})")
    return rows


# ── events.jsonl ────────────────────────────────────────────────────────────

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


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        goals = (REPO / "GOALS.md").read_text()
    except FileNotFoundError:
        print("ERROR: GOALS.md not found", file=sys.stderr)
        sys.exit(1)

    timeline = (REPO / "docs/context/TIMELINE.md").read_text(errors="replace") \
        if (REPO / "docs/context/TIMELINE.md").exists() else ""
    roadmap = (REPO / "ROADMAP_2026-2027.md").read_text(errors="replace") \
        if (REPO / "ROADMAP_2026-2027.md").exists() else ""

    phases   = phase_status(goals)
    meta     = timeline_meta(timeline)
    rfcs     = rfc_list(REPO / "protocol/rfcs")
    wps      = wp_status(roadmap)
    decisions = ralph_decisions(REPO / "tools/ralph/state/events.jsonl")

    out: list[str] = [
        f"<!-- generated {date.today()} from GOALS.md · TIMELINE.md · rfcs/ · ROADMAP"
        " · events.jsonl — do not edit manually -->",
        "## Vaked project status",
        "",
    ]

    if meta:
        out += [meta, ""]

    out += ["### Phases (milestone map)"]
    out.extend(f"- {p}" for p in phases)
    out.append("")

    if wps:
        out += ["### Work packages"]
        out.extend(wps)
        out.append("")

    if rfcs:
        out += ["### Protocol RFCs (all Draft)"]
        out.extend(rfcs)
        out.append("")

    out += ["### Ralph decision tracks"]
    out.extend(f"  {t}" for t in RALPH_TRACKS)
    out.append("")

    out += ["### Area labels → file paths"]
    out.extend(f"  {label}: {desc}" for label, desc in AREA_LABELS.items())
    out.append("")

    if decisions:
        out += ["### Recent ralph decisions (last 5, chronological)"]
        out.extend(decisions)
        out.append("")

    print("\n".join(out))


if __name__ == "__main__":
    main()
