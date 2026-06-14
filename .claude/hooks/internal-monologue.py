#!/usr/bin/env python3
"""
PreToolUse hook: internal-monologue.
Reads the pending tool call from stdin, emits one-sentence strategic reflection.
Uses ANTHROPIC_API_KEY (claude-sonnet-4-6) or falls back to OPENAI_API_KEY (gpt-4o-mini).
Never blocks — exit 0 always.
"""

import json
import os
import sys
import urllib.request

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

SYSTEM = (
    "You are a one-sentence planning assistant embedded in an AI coding agent. "
    "Given a tool call about to execute, output exactly one terse sentence (≤18 words) "
    "reflecting the strategic intent: what this action achieves toward the current goal. "
    "No preamble, no explanation, just the sentence."
)


def call_anthropic(tool_name: str, tool_summary: str) -> str:
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 60,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": f"Tool: {tool_name}\nInput: {tool_summary}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def call_openai(tool_name: str, tool_summary: str) -> str:
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "max_tokens": 60,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Tool: {tool_name}\nInput: {tool_summary}"},
        ],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def summarize_input(tool_input: dict) -> str:
    """Extract key fields for the prompt — keep it short."""
    keys = ["command", "file_path", "description", "title", "head", "query", "pattern"]
    parts = []
    for k in keys:
        if k in tool_input:
            v = str(tool_input[k])
            parts.append(f"{k}={v[:80]}")
    if not parts:
        raw = json.dumps(tool_input)
        parts = [raw[:120]]
    return "; ".join(parts)


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        tool_name = data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {})
        summary = summarize_input(tool_input)

        if ANTHROPIC_KEY:
            sentence = call_anthropic(tool_name, summary)
        elif OPENAI_KEY:
            sentence = call_openai(tool_name, summary)
        else:
            sys.exit(0)

        print(f"[monologue] {sentence}")
    except Exception:
        pass  # never block — hook failure must be silent
    sys.exit(0)


if __name__ == "__main__":
    main()
