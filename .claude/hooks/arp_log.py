#!/usr/bin/env python3
"""PostToolUse Bash hook — append substantial commands to docs/arp-log.md as
typed `arp_event` Vaked declarations. Deterministic; no model involvement.

Reads the PostToolUse stdin JSON, filters trivial/excluded commands, captures
files touched via a git-porcelain stamp delta, and appends a fenced arp_event
block. Always exits 0 (never blocks the tool result).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile

EXCLUDE = (".vaked", "vakedc", "run_all.py")
_TRIVIAL = re.compile(
    r"^\s*(ls|cat|echo|which|pwd|head|tail|true|cd|tree"
    r"|git\s+(status|log|diff|show|branch|remote))\b"
)
_PATHISH = re.compile(r"(?:[\w.@~-]+/)+[\w.@-]+|\b[\w@-]+\.[A-Za-z0-9]{1,8}\b")
_STAMP = os.path.join(tempfile.gettempdir(), "arp-gitmap.json")


def is_substantial(cmd: str) -> bool:
    if not cmd or not cmd.strip():
        return False
    if any(x in cmd for x in EXCLUDE):
        return False
    if _TRIVIAL.match(cmd):
        return False
    return True


def extract_inputs(cmd: str) -> list[str]:
    out, seen = [], set()
    for tok in _PATHISH.findall(cmd):
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def status_from_response(resp) -> str:
    if not isinstance(resp, dict):
        return "ok"
    if resp.get("interrupted"):
        return "err: interrupted"
    code = resp.get("exit_code", resp.get("returncode"))
    if isinstance(code, int) and code != 0:
        tail = (resp.get("stderr") or "").strip().splitlines()
        msg = f": {tail[-1][:80]}" if tail else ""
        return f"err: exit {code}{msg}"
    return "ok"


def git_status_map(root: str) -> dict:
    try:
        out = subprocess.run(
            ["git", "-C", root, "status", "--porcelain", "-uall", "-z"],
            capture_output=True, text=True).stdout
    except Exception:
        return {}
    m, toks, i = {}, out.split("\0"), 0
    while i < len(toks):
        t = toks[i]
        if not t:
            i += 1
            continue
        code, path = t[:2], t[3:]
        if code and code[0] in ("R", "C"):
            i += 1  # rename/copy source path is the next token
        m[path] = code
        i += 1
    return m


def _load_stamp() -> dict:
    try:
        with open(_STAMP, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_stamp(m: dict) -> None:
    try:
        with open(_STAMP, "w", encoding="utf-8") as fh:
            json.dump(m, fh)
    except Exception:
        pass


def outputs_delta(before: dict, after: dict) -> list[str]:
    changed = [p for p, c in after.items() if before.get(p) != c]
    changed += [p for p in before if p not in after]
    # drop the log itself + the stamp so the hook never records its own write
    return sorted(p for p in set(changed) if not p.endswith("arp-log.md"))


def _esc(s: str) -> str:
    return (s.replace("\\", "\\\\")
             .replace('"', '\\"')
             .replace("\n", "\\n")
             .replace("\r", "\\r"))


def _vstr(s: str) -> str:
    return '"' + _esc(s) + '"'


def _vlist(xs: list[str]) -> str:
    return "[" + ", ".join(_vstr(x) for x in xs) + "]"


def _label(cmd: str) -> str:
    return " ".join(cmd.split())[:48]


def _slug(now: datetime.datetime) -> str:
    return "e_" + now.strftime("%Y%m%d_%H%M%S")


def render_block(ts: str, cmd: str, inputs: list[str], outputs: list[str],
                 status: str, notes: str = "", now=None) -> str:
    now = now or datetime.datetime.now()
    lines = [
        f"## {ts} — {_label(cmd)}",
        "",
        "```vaked",
        f"arp_event {_slug(now)} {{",
        f"  ts      = {_vstr(ts)}",
        f"  command = {_vstr(cmd.strip())}",
    ]
    if inputs:
        lines.append(f"  inputs  = {_vlist(inputs)}")
    if outputs:
        lines.append(f"  outputs = {_vlist(outputs)}")
    lines.append(f"  status  = {_vstr(status)}")
    if notes:
        lines.append(f"  notes   = {_vstr(notes)}")
    lines += ["}", "```", ""]
    return "\n".join(lines)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "")
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    before = _load_stamp()
    after = git_status_map(root)
    _save_stamp(after)  # always advance the stamp, even for trivial commands

    if not is_substantial(cmd):
        return 0

    now = datetime.datetime.now()
    block = render_block(
        ts=now.strftime("%Y-%m-%d %H:%M"),
        cmd=cmd,
        inputs=extract_inputs(cmd),
        outputs=outputs_delta(before, after),
        status=status_from_response(data.get("tool_response")),
        now=now,
    )
    log = os.path.join(root, "docs", "arp-log.md")
    try:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("\n" + block)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
