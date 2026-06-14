#!/usr/bin/env python3
"""Generate an asciinema v2 .cast replaying the swe-af fan-out batch live smoke
(2026-06-14, bench-node). Deterministic — built from the REAL captured commands
and outputs of the run that opened draft PR #193. No live deps; re-run to
regenerate. Play: `asciinema play docs/demo/swe-af-smoke.cast`.
"""
import json
import sys

# Fixed timestamp of the recorded run (2026-06-14T05:55Z), so output is stable.
TS = 1781414100
PROMPT = "[1;32mdev@bench-node[0m:[1;34m~[0m$ "

# (think_delay_before_cmd, command, [output_lines], pause_after)
STEPS = [
    (0.6, "# swe-af fan-out batch — live end-to-end smoke (bench-node -> Aperture -> draft PR)", [], 0.8),
    (0.4, "swe-af-enqueue --repo peterlodri-sec/vaked-base --issue 192",
     ["enqueued 8954bf2f-fb02-44ea-820d-3bab2f446df0 -> peterlodri-sec/vaked-base (issue #192)"], 1.0),
    (0.5, "journalctl -u swe-af-orchestrator -f", [
        "INFO async_nats: event: connected",
        "INFO swe_af_orchestrator: orchestrator up pool=3 subject=swe.af.tasks scratch=/home/dev/swe-af-scratch",
        "INFO swe_af_orchestrator: task lease task=8954bf2f repo=peterlodri-sec/vaked-base issue=192",
        "      git clone --filter=blob:none peterlodri-sec/vaked-base ... done",
        "      vaked-swe-af MODE=plan  -> Aperture(/v1) deepseek/deepseek-v4-flash ... plan ready",
        "      vaked-swe-af MODE=code  -> Aperture(/v1) deepseek/deepseek-v4-flash ... 1 file",
        "      apply docs/SWE_AF_SMOKE.md ; git push swe-af/issue-192 --force-with-lease",
        "eventd: appended seq 0 (d5ad56ab1c9e0a5e…) log.jsonl",
        "eventd: appended seq 1 (23d136dec642a6dd…) log.jsonl",
        "eventd: appended seq 2 (d98d136f5aedb629…) log.jsonl",
        "eventd: log.jsonl — chain OK (3 entries, tail d98d136f5aedb629…)",
        "INFO swe_af_orchestrator: task done task=8954bf2f pr=Some(\"https://github.com/peterlodri-sec/vaked-base/pull/193\")",
    ], 1.2),
    (0.5, "gh pr view 193 --json isDraft,title,url -q '.title, .url, (\"draft=\" + (.isDraft|tostring))'", [
        "swe_af: docs: add swe-af smoke marker file",
        "https://github.com/peterlodri-sec/vaked-base/pull/193",
        "draft=true",
    ], 0.9),
    (0.5, "gh pr diff 193", [
        "diff --git a/docs/SWE_AF_SMOKE.md b/docs/SWE_AF_SMOKE.md",
        "new file mode 100644",
        "--- /dev/null",
        "+++ b/docs/SWE_AF_SMOKE.md",
        "@@ -0,0 +1 @@",
        "[32m+swe-af smoke run OK[0m",
    ], 0.8),
    (0.6, "# POLA: draft only, never merged. eventd chain verified. no secrets persisted.", [], 1.5),
]

def emit(out):
    header = {"version": 2, "width": 108, "height": 34, "timestamp": TS,
              "title": "swe-af fan-out batch — live smoke (PR #193)",
              "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}}
    out.write(json.dumps(header) + "\n")
    t = 0.0

    def ev(data):
        nonlocal t
        out.write(json.dumps([round(t, 3), "o", data]) + "\n")

    for think, cmd, lines, pause in STEPS:
        t += think
        ev(PROMPT)
        # "type" the command character-by-character for a live feel
        for ch in cmd:
            t += 0.012
            ev(ch)
        t += 0.15
        ev("\r\n")
        for ln in lines:
            t += 0.18
            ev(ln + "\r\n")
        t += pause

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "docs/demo/swe-af-smoke.cast"
    with open(path, "w") as f:
        emit(f)
    print(f"wrote {path}")
