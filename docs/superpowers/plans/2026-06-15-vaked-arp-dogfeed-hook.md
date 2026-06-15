# Tightened vaked→ARP dogfeeding hook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unreliable advisory ARP-log nag rule with a deterministic PostToolUse hook that records substantial shell commands as validatable `arp_event` Vaked declarations in `docs/arp-log.md`, plus a verifier and a portable bootstrap block.

**Architecture:** A `schema arp_event` in `builtins.vaked` makes `arp_event` instances check-validate by kind-name binding (zero grammar change — parser accepts any kind). A pure-python PostToolUse `Bash` hook filters noise, captures touched files via a git-porcelain stamp delta, and appends a fenced `arp_event` block. A batch verifier extracts the fences and runs `vakedc check` to prove the log is valid Vaked.

**Tech Stack:** Python 3 (stdlib only), vakedc (in-repo), Claude Code hooks, git porcelain.

**Worktree:** Standing constraint — do NOT work on `main`. Create an isolated worktree+branch first (superpowers:using-git-worktrees), e.g. branch `feat/arp-dogfeed-hook`. NEVER build on the dev machine; pure-python vakedc on tiny fixtures is allowed.

**Instance-name note:** Existing Vaked instances use **ident** names (`stream telemetry`), not quoted strings. So `arp_event` instances use an ident slug (`arp_event e_20260615_103045 { … }`) and carry the human timestamp in a `ts` field.

---

### Task 1: Define the `arp_event` schema

**Files:**
- Modify: `vaked/schema/builtins.vaked` (append)

- [ ] **Step 1: Append the schema**

Append to `vaked/schema/builtins.vaked`:

```vaked

schema arp_event {
  field ts      : String { required }
  field command : String { required nonempty }
  field inputs  : List<String> { optional }
  field outputs : List<String> { optional }
  field status  : String { required }
  field notes   : String { optional }
}
```

- [ ] **Step 2: Verify builtins still check-clean**

Run: `python3 -m vakedc check vaked/schema/builtins.vaked`
Expected: exit 0 (no diagnostics).

- [ ] **Step 3: Probe that an instance validates**

Create a throwaway `/tmp/arp_probe.vaked`:

```vaked
arp_event e_20260615_103045 {
  ts      = "2026-06-15 10:30"
  command = "python3 build.py"
  inputs  = ["build.py"]
  outputs = ["out/app"]
  status  = "ok"
}
```

Run: `python3 -m vakedc check /tmp/arp_probe.vaked`
Expected: exit 0. (If it fails on the ident name, the slug form is wrong — stop and inspect the parser's `name` production before continuing. The schema/field names should be correct.)

- [ ] **Step 4: Commit**

```bash
git add vaked/schema/builtins.vaked
git commit -m "feat(arp): add arp_event schema to builtins"
```

---

### Task 2: ARP-log verifier (`tools/arp/verify_log.py`)

**Files:**
- Create: `tools/arp/__init__.py` (empty)
- Create: `tools/arp/verify_log.py`
- Create: `tools/arp/test_arp_log.py` (verifier test added here, hook tests in Task 3)

- [ ] **Step 1: Write the failing test**

Create `tools/arp/test_arp_log.py`:

**NOTE — stdlib only:** pytest is NOT installed (no build/network on this machine).
Use `unittest` + `unittest.mock` throughout. Run with `python3 -m unittest`.

Create `tools/arp/test_arp_log.py`:

```python
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _run(args, **kw):
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          capture_output=True, text=True, **kw)


class VerifyLogTest(unittest.TestCase):
    def test_verify_log_extracts_and_checks(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, "log.md")
            with open(md, "w") as fh:
                fh.write(
                    "# log\n\n## 2026-06-15 10:30 — build\n\n"
                    "```vaked\n"
                    "arp_event e_1 {\n"
                    '  ts = "2026-06-15 10:30"\n'
                    '  command = "python3 build.py"\n'
                    '  status = "ok"\n'
                    "}\n"
                    "```\n"
                )
            r = _run(["-m", "tools.arp.verify_log", md])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tools.arp.test_arp_log.VerifyLogTest -v`
Expected: FAIL/ERROR — `No module named tools.arp.verify_log`.

- [ ] **Step 3: Write the verifier**

Create empty `tools/arp/__init__.py`. Create `tools/arp/verify_log.py`:

```python
#!/usr/bin/env python3
"""Extract ```vaked blocks from a markdown file, concat to a temp .vaked, run vakedc check.

Exit 0 = every block parses + checks against builtins (incl. schema arp_event).
This is the dogfood gate: Vaked validates its own ARP session log.
"""
import os
import re
import subprocess
import sys
import tempfile

_FENCE = re.compile(r"```vaked\n(.*?)```", re.S)


def extract(md: str) -> list[str]:
    return [b.strip() for b in _FENCE.findall(md)]


def main(argv: list[str]) -> int:
    path = argv[0] if argv else "docs/arp-log.md"
    with open(path, encoding="utf-8") as fh:
        blocks = extract(fh.read())
    if not blocks:
        print("verify_log: no vaked blocks found")
        return 0
    src = "\n\n".join(blocks) + "\n"
    fd, tmp = tempfile.mkstemp(suffix=".vaked")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(src)
        r = subprocess.run([sys.executable, "-m", "vakedc", "check", tmp])
        return r.returncode
    finally:
        os.unlink(tmp)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tools.arp.test_arp_log.VerifyLogTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/arp/__init__.py tools/arp/verify_log.py tools/arp/test_arp_log.py
git commit -m "feat(arp): add ARP-log verifier (vakedc check over md fences)"
```

---

### Task 3: Capture hook (`.claude/hooks/arp_log.py`)

**Files:**
- Create: `.claude/hooks/arp_log.py`
- Test: `tools/arp/test_arp_log.py` (extend)

The module splits pure helpers (testable) from IO (`main`). Build it helper-by-helper.

- [ ] **Step 1: Write failing tests for the pure helpers**

Insert into `tools/arp/test_arp_log.py` (above the `if __name__` guard), adding
`import importlib.util` to the top imports:

```python
_HOOK = os.path.join(ROOT, ".claude", "hooks", "arp_log.py")


def _load_hook():
    import importlib.util
    spec = importlib.util.spec_from_file_location("arp_log", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HookHelpersTest(unittest.TestCase):
    def setUp(self):
        self.h = _load_hook()

    def test_is_substantial(self):
        h = self.h
        self.assertTrue(h.is_substantial("python3 build.py"))
        self.assertTrue(h.is_substantial("make test"))
        self.assertFalse(h.is_substantial("ls -la"))
        self.assertFalse(h.is_substantial("git status"))
        self.assertFalse(h.is_substantial("cat foo.txt"))
        self.assertFalse(h.is_substantial("python3 -m vakedc check x.vaked"))
        self.assertFalse(h.is_substantial(""))

    def test_extract_inputs(self):
        self.assertEqual(self.h.extract_inputs("cp src/a.txt dest/b.txt"),
                         ["src/a.txt", "dest/b.txt"])
        self.assertEqual(self.h.extract_inputs("echo hi"), [])

    def test_status_from_response(self):
        h = self.h
        self.assertEqual(h.status_from_response({"exit_code": 0}), "ok")
        self.assertEqual(h.status_from_response({}), "ok")
        self.assertTrue(h.status_from_response({"interrupted": True}).startswith("err"))
        self.assertTrue(
            h.status_from_response({"exit_code": 2, "stderr": "boom"}).startswith("err"))

    def test_render_block_validates(self):
        from tools.arp.verify_log import extract
        block = self.h.render_block("2026-06-15 10:30", "python3 build.py",
                                    ["build.py"], ["out/app"], "ok")
        blocks = extract(block)
        self.assertTrue(blocks, "render_block must emit a ```vaked fence")
        fd, tmp = tempfile.mkstemp(suffix=".vaked")
        os.close(fd)
        try:
            with open(tmp, "w") as fh:
                fh.write(blocks[0] + "\n")
            r = _run(["-m", "vakedc", "check", tmp])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            os.unlink(tmp)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.arp.test_arp_log.HookHelpersTest -v`
Expected: FAIL — hook file does not exist.

- [ ] **Step 3: Write the hook**

Create `.claude/hooks/arp_log.py`:

```python
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
    return s.replace("\\", "\\\\").replace('"', '\\"')


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
```

- [ ] **Step 4: Run the helper tests**

Run: `python3 -m unittest tools.arp.test_arp_log.HookHelpersTest -v`
Expected: PASS (all four).

- [ ] **Step 5: Write failing tests for `main` (append + skip)**

Insert into `tools/arp/test_arp_log.py` (above the `if __name__` guard). Uses
`mock.patch.object` + `tempfile.TemporaryDirectory` (stdlib):

```python
class HookMainTest(unittest.TestCase):
    def _drive(self, command, gitmap):
        h = _load_hook()
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "docs"))
            log = os.path.join(d, "docs", "arp-log.md")
            with open(log, "w") as fh:
                fh.write("# ARP Event Log\n")
            payload = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "tool_response": {"exit_code": 0},
            })
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": d}), \
                 mock.patch.object(h, "git_status_map", lambda root: gitmap), \
                 mock.patch.object(h, "_load_stamp", lambda: {}), \
                 mock.patch.object(h, "_save_stamp", lambda m: None), \
                 mock.patch.object(sys, "stdin", io.StringIO(payload)):
                rc = h.main()
            with open(log) as fh:
                return rc, fh.read()

    def test_main_appends_for_substantial(self):
        rc, body = self._drive("python3 build.py src/main.py", {"out/app": "??"})
        self.assertEqual(rc, 0)
        self.assertIn("arp_event e_", body)
        self.assertIn('command = "python3 build.py src/main.py"', body)
        self.assertIn("out/app", body)

    def test_main_skips_trivial(self):
        rc, body = self._drive("ls -la", {})
        self.assertEqual(rc, 0)
        self.assertEqual(body, "# ARP Event Log\n")  # unchanged
```

- [ ] **Step 6: Run the full test file**

Run: `python3 -m unittest tools.arp.test_arp_log -v`
Expected: all PASS (verifier + helpers + main).

- [ ] **Step 7: Make the hook executable + commit**

```bash
chmod +x .claude/hooks/arp_log.py
git add .claude/hooks/arp_log.py tools/arp/test_arp_log.py
git commit -m "feat(arp): deterministic PostToolUse capture hook + tests"
```

---

### Task 4: Register the hook, retire the advisory rule

**Files:**
- Modify: `.claude/settings.json` (PostToolUse array)
- Delete: `.claude/hookify.vaked-arp-log.local.md` (gitignored, per-machine)

- [ ] **Step 1: Inspect current PostToolUse config**

Run: `python3 -c "import json;print(json.dumps(json.load(open('.claude/settings.json')).get('hooks',{}).get('PostToolUse',[]),indent=2))"`
Expected: prints the existing PostToolUse entries (e.g. the `Write|Edit` vaked-check hook). Note the exact structure to match it.

- [ ] **Step 2: Add the Bash hook entry**

Add to `.claude/settings.json` under `hooks.PostToolUse` (a new array element; do not clobber existing entries):

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "type": "command",
      "command": "python3 \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/arp_log.py\""
    }
  ]
}
```

- [ ] **Step 3: Validate settings.json is well-formed**

Run: `python3 -c "import json;json.load(open('.claude/settings.json'));print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Retire the advisory rule**

Run: `rm -f .claude/hookify.vaked-arp-log.local.md`
(It is gitignored — no commit needed for the deletion. This prevents double-handling.)

- [ ] **Step 5: Commit settings**

```bash
git add .claude/settings.json
git commit -m "chore(arp): register capture hook, retire advisory rule"
```

---

### Task 5: Portable bootstrap block (`docs/arp-log.meta-hook.md`)

**Files:**
- Create: `docs/arp-log.meta-hook.md`

- [ ] **Step 1: Write the meta-hook doc**

Create `docs/arp-log.meta-hook.md`:

````markdown
# ARP dogfeed hook — portable bootstrap

Copy-paste this block into any skill, workflow, or agent prompt. An agent that
reads it can set up + register + run the vaked→ARP capture hook from scratch,
without any other doc.

[<arp-dogfeed-hook setup="idempotent">

GOAL: record substantial shell commands as validatable `arp_event` Vaked
declarations in `docs/arp-log.md`.

STEP 1 — schema (idempotent): ensure `vaked/schema/builtins.vaked` contains:
    schema arp_event {
      field ts      : String { required }
      field command : String { required nonempty }
      field inputs  : List<String> { optional }
      field outputs : List<String> { optional }
      field status  : String { required }
      field notes   : String { optional }
    }
Verify: `python3 -m vakedc check vaked/schema/builtins.vaked` → exit 0.

STEP 2 — hook: create `.claude/hooks/arp_log.py`, a PostToolUse handler that
reads stdin JSON and on `tool_name == "Bash"`:
  - skip if command matches trivial reads (ls/cat/echo/which/pwd/head/tail/cd,
    git status|log|diff|show|branch) OR contains ".vaked"|"vakedc"|"run_all.py";
  - keep a $TMPDIR/arp-gitmap.json stamp of `git status --porcelain -uall -z`;
    delta vs stamp = `outputs` (drop arp-log.md itself); advance stamp every run;
  - `inputs` = path-looking tokens in the command;
  - `status` = "ok" or "err: exit <n>: <stderr tail>" from `tool_response`
    (fields: exit_code|returncode, stderr, interrupted);
  - append a fenced block to `docs/arp-log.md`:
        ## YYYY-MM-DD HH:MM — <first 48 chars of command>

        ```vaked
        arp_event e_YYYYMMDD_HHMMSS {
          ts      = "YYYY-MM-DD HH:MM"
          command = "<command>"
          inputs  = ["..."]    # omit if empty
          outputs = ["..."]    # omit if empty
          status  = "ok"
        }
        ```
  - always exit 0; never block; instance name is an IDENT slug (not a string).
  (Reference implementation: `.claude/hooks/arp_log.py` in vaked-base.)

STEP 3 — register: add to `.claude/settings.json` under hooks.PostToolUse
(append, don't clobber):
    { "matcher": "Bash", "hooks": [ { "type": "command",
      "command": "python3 \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/arp_log.py\"" } ] }

STEP 4 — verify the loop: `python3 tools/arp/verify_log.py docs/arp-log.md`
extracts the ```vaked fences, concatenates to a temp .vaked, runs
`python3 -m vakedc check`. Exit 0 = the log is provably valid Vaked.

INVARIANTS: zero grammar change (parser accepts any kind; checker binds
instance→schema by kind-name). Idempotent: re-running setup must not duplicate
the schema or the settings entry.

</arp-dogfeed-hook>]
````

- [ ] **Step 2: Sanity-check the embedded schema matches builtins**

Run: `grep -A7 "schema arp_event" vaked/schema/builtins.vaked docs/arp-log.meta-hook.md`
Expected: the field list is identical in both files.

- [ ] **Step 3: Commit**

```bash
git add docs/arp-log.meta-hook.md
git commit -m "docs(arp): portable bootstrap block for the dogfeed hook"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Drive the hook manually with a substantial command**

Run:
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"python3 -c \"open(\\\"sentinel.tmp\\\",\\\"w\\\").write(\\\"x\\\")\""},"tool_response":{"exit_code":0}}' \
  | CLAUDE_PROJECT_DIR="$PWD" python3 .claude/hooks/arp_log.py
```
Expected: exit 0; `docs/arp-log.md` gains a `## … — python3 -c …` entry with a
`arp_event e_…` block. (Clean up: `rm -f sentinel.tmp`.)

- [ ] **Step 2: Drive it with a trivial command**

Run:
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"tool_response":{"exit_code":0}}' \
  | CLAUDE_PROJECT_DIR="$PWD" python3 .claude/hooks/arp_log.py
```
Expected: exit 0; `docs/arp-log.md` unchanged (no new entry).

- [ ] **Step 3: Verify the populated log is valid Vaked**

Run: `python3 tools/arp/verify_log.py docs/arp-log.md`
Expected: exit 0.

- [ ] **Step 4: Full test suite**

Run: `python3 -m unittest tools.arp.test_arp_log -v`
Expected: all PASS.

- [ ] **Step 5: Commit any log fixture / final touch-ups**

```bash
git add -A
git commit -m "test(arp): end-to-end dogfeed hook verified"
```

---

## Self-review notes

- **Spec coverage:** schema (Task 1), deterministic hook (Task 3), register+retire (Task 4), verifier (Task 2), tests (Tasks 2-3), meta-hook (Task 5), end-to-end (Task 6). All six spec components covered.
- **Deliberate refinement vs spec:** spec mentioned per-block self-validation inside the hook; moved to the batch `verify_log.py` gate to avoid spawning vakedc on every command (latency). The hook always appends; validity is enforced by Task 6 Step 3 + the `render_block` validation test (Task 3 Step 1).
- **Instance naming:** spec's old quoted-string label replaced with an ident slug + `ts` field, matching existing Vaked instance syntax (verified by Task 1 Step 3 probe + Task 3 render_block test).
- **Constraints honored:** worktree+branch, no main commits, pure-python tests on tiny fixtures, no build.
