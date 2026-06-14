#!/usr/bin/env python3
"""Extract a readable, redacted transcript from a Claude Code session .jsonl.

Keeps: user-typed messages, assistant prose, and the Bash commands run.
Drops: hook spam, system reminders, skill bodies, tool-result bodies, local
command stdout. Redacts: emails, IPs, tailnet name, provider keys, device codes.

Usage: scrub-transcript.py SESSION.jsonl > transcript.md
"""
import json
import re
import sys

NOISE = (
    "UserPromptSubmit hook", "MANDATORY: META-COGNITION", "Base directory for this skill",
    "<system-reminder>", "Caveat: The messages below", "RUST SKILLS DISPLAY FORMAT",
    "SessionStart hook", "local-command-stdout", "<command-name>", "<bash-input>",
    "<bash-stdout>", "function_results", "Respond terse like smart caveman",
    "The following skills are available", "deferred tools", "<task-notification>",
)

REDACTIONS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"\btail[0-9a-f]{6,}\b"), "<tailnet>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"keyid:[^\"'\s]+"), "<key>"),
    (re.compile(r"\bsk-[A-Za-z0-9._-]{6,}\b"), "<key>"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "<token>"),
    (re.compile(r"\b\d{4}-[A-Z0-9]{4}\b"), "<code>"),
]

def redact(s: str) -> str:
    for pat, repl in REDACTIONS:
        s = pat.sub(repl, s)
    return s

def is_noise(s: str) -> bool:
    return any(m in s for m in NOISE)

def texts(content):
    out = []
    if isinstance(content, str):
        out.append(("text", content))
    elif isinstance(content, list):
        for p in content:
            if not isinstance(p, dict):
                continue
            t = p.get("type")
            if t == "text" and p.get("text"):
                out.append(("text", p["text"]))
            elif t == "tool_use" and p.get("name") == "Bash":
                cmd = (p.get("input") or {}).get("command", "")
                if cmd:
                    out.append(("bash", cmd))
            elif t == "tool_use":
                out.append(("tool", p.get("name", "tool")))
    return out

def main(path):
    print("# swe-af fan-out batch — scrubbed session transcript\n")
    print("> Redacted for publication (emails/IPs/tailnet/keys/codes → placeholders). "
          "Hook noise, skill bodies, and tool-result bodies removed. "
          "Engineering arc only.\n")
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        role = obj.get("type") or (obj.get("message") or {}).get("role")
        msg = obj.get("message") or {}
        content = msg.get("content", obj.get("content"))
        if role not in ("user", "assistant"):
            continue
        for kind, body in texts(content):
            body = body.strip()
            if not body or is_noise(body):
                continue
            body = redact(body)
            if kind == "bash":
                first = body.strip().splitlines()[0][:200]
                print(f"\n```bash\n$ {first}\n```")
            elif kind == "tool":
                continue
            else:
                who = "🧑 **user**" if role == "user" else "🤖 **claude**"
                snippet = body if len(body) < 1200 else body[:1200] + " …"
                print(f"\n{who}: {snippet}")

if __name__ == "__main__":
    main(sys.argv[1])
