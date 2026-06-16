# vaked-oracle slice 4b · thread 3 — ARP-emission — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** The oracle emits its findings as per-function `arp_event` Vaked declarations to `docs/oracle/arp-trace.md`, verifiable via `vakedc check` — closing the oracle→Vaked/ARP dogfood loop without touching the execution ARP IR (other dev's lane).

**Tech Stack:** Python 3 stdlib. Tests = module-level `test_*` + plain `assert` (the `test_oracle.py` convention, NOT unittest). One test subprocesses `python3 -m vakedc check` (in-repo, M3-safe — no compile).

**Spec:** `docs/superpowers/specs/2026-06-16-vaked-oracle-slice-4b-arp-emit-design.md`

**Lane constraint:** consume the `arp_event` builtin schema read-only; **never** touch `exec-semantics`/`gocc`/execution-ARP-IR. Emit ONLY to `docs/oracle/arp-trace.md`.

**Worktree:** `.worktrees/oracle-arp` (branch `feat/oracle-arp-emit`). Every implementer: `cd` there first, confirm `git rev-parse --abbrev-ref HEAD` == `feat/oracle-arp-emit` before committing; `git add` only named files (no `-A`).

---

### Task 1: `arp_emit.py` — mapping + render + emit (+ vakedc-check dogfood test)

**Files:** Create `tools/oracle/arp_emit.py`; Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: failing tests** — append to `tools/oracle/test_oracle.py`:

```python
# ---- slice 4b thread 3: ARP-emission ----
def _arp_finding():
    return {"kind": "oracle_finding", "v": 1,
            "target": {"path": "libllama.so.0", "sha256": "0" * 64, "source_ref": "x"},
            "decompiler": {"model": "m"},
            "functions": [
                {"name": "llama_decode", "addr": "0x0", "pseudo_c_sha": "a" * 64,
                 "refined_c": "int llama_decode(void){return 0;}",
                 "fidelity": {"score": 0.581, "method": "x"}, "dynamic": {"frida": None, "ebpf": None}},
                {"name": "cache.sha256Hex", "addr": "0x0", "pseudo_c_sha": "b" * 64,
                 "refined_c": None,
                 "fidelity": {"score": None, "method": "x"}, "dynamic": {"frida": None, "ebpf": None}},
            ],
            "observed_effects": {"writes": [], "deletes": []}, "transition_xref": None,
            "confidence": 0.0}


def test_arp_finding_to_events_per_function():
    import arp_emit
    evs = arp_emit.finding_to_events(_arp_finding())
    assert len(evs) == 2
    a, b = evs
    assert a["command"] == "oracle RE llama_decode"
    assert a["inputs"] == ["libllama.so.0", "llama_decode"]
    assert a["status"] == "ok"                                   # 0.581 >= 0.4
    assert any(o.startswith("fidelity:0.581") for o in a["outputs"])
    assert b["command"] == "oracle RE cache.sha256Hex"
    assert b["status"] == "no-ground-truth"                      # score None
    assert "refined_sha:none" in b["outputs"]


def test_arp_slug_is_ident_safe():
    import arp_emit, re
    s = arp_emit._slug("cache.sha256Hex", "code")
    assert re.match(r"^[A-Za-z_]\w*$", s)                        # valid Vaked IDENT
    assert s.startswith("oracle_cache_sha256Hex_")


def test_arp_status_thresholds():
    import arp_emit
    assert arp_emit._status(None) == "no-ground-truth"
    assert arp_emit._status(0.2) == "low-fidelity"
    assert arp_emit._status(0.4) == "ok"
    assert arp_emit._status(0.9) == "ok"


def test_arp_render_block_shape():
    import arp_emit
    ev = {"slug": "oracle_f_abc", "command": "oracle RE f", "inputs": ["t", "f"],
          "outputs": ["refined_sha:abc", "fidelity:0.5"], "status": "ok"}
    blk = arp_emit.render_arp_block(ev, ts="2026-06-16 12:00")
    assert blk.startswith("```vaked\narp_event oracle_f_abc {")  # slug UNQUOTED
    assert 'ts      = "2026-06-16 12:00"' in blk
    assert 'command = "oracle RE f"' in blk
    assert 'status  = "ok"' in blk
    assert "inputs  =" in blk and "outputs =" in blk
    # omit empty inputs/outputs
    blk2 = arp_emit.render_arp_block({"slug": "oracle_g_x", "command": "c",
                                      "inputs": [], "outputs": [], "status": "ok"}, ts="t")
    assert "inputs  =" not in blk2 and "outputs =" not in blk2


def test_arp_emit_appends_and_headers_once():
    import arp_emit, tempfile, os
    p = tempfile.mktemp(suffix=".md")
    n1 = arp_emit.emit(_arp_finding(), path=p, ts="2026-06-16 12:00")
    n2 = arp_emit.emit(_arp_finding(), path=p, ts="2026-06-16 12:05")
    body = open(p).read()
    assert n1 == 2 and n2 == 2
    assert body.count("# vaked-oracle ARP trace") == 1            # header once
    assert body.count("arp_event ") == 4                          # 2 + 2
    os.remove(p)


def test_arp_emitted_blocks_pass_vakedc_check():
    import arp_emit, tempfile, os, sys, subprocess
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))   # tools/ -> `arp` package
    from arp import verify_log                                    # tools/arp/verify_log.py
    md = tempfile.mktemp(suffix=".md")
    arp_emit.emit(_arp_finding(), path=md, ts="2026-06-16 12:00")
    blocks = verify_log.extract(open(md).read())
    assert len(blocks) == 2
    src = "\n\n".join(blocks) + "\n"
    vk = tempfile.mktemp(suffix=".vaked")
    open(vk, "w").write(src)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    r = subprocess.run([sys.executable, "-m", "vakedc", "check", vk], cwd=repo_root,
                       capture_output=True, text=True)
    assert r.returncode == 0, "vakedc check failed: %s" % (r.stdout + r.stderr)
    os.remove(md); os.remove(vk)
```
(Note: `from arp import verify_log` — `tools/arp/__init__.py` exists, and the test adds repo root to `sys.path`; `verify_log.extract` pulls the ```vaked blocks.)

- [ ] **Step 2: run, expect FAIL** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -8` → `ModuleNotFoundError: No module named 'arp_emit'`.

- [ ] **Step 3: implement** — create `tools/oracle/arp_emit.py`:

```python
"""arp_emit — emit oracle findings as typed `arp_event` Vaked declarations.

One `arp_event` per reverse-engineered function, appended to a dedicated ARP trace
(`docs/oracle/arp-trace.md`), verifiable via `vakedc check` (tools/arp/verify_log.py).
The oracle is a one-way PRODUCER of arp_event blocks conforming to the builtin
`arp_event` schema — it never touches the execution ARP IR. Pure stdlib.
"""
from __future__ import annotations

import hashlib
import os
import re


def _slug(name, refined_c):
    base = re.sub(r"\W", "_", name)
    h = hashlib.sha256((refined_c or "").encode()).hexdigest()[:12]
    return "oracle_%s_%s" % (base, h)


def _status(score):
    if score is None:
        return "no-ground-truth"
    if score < 0.4:
        return "low-fidelity"
    return "ok"


def _vstr(s):
    return '"%s"' % str(s).replace("\\", "\\\\").replace('"', '\\"')


def _vlist(xs):
    return "[" + ", ".join(_vstr(x) for x in xs) + "]"


def finding_to_events(finding):
    """One arp_event dict per analyzed function in the finding."""
    tgt = (finding.get("target") or {}).get("path", "?")
    out = []
    for fe in finding.get("functions", []):
        name = fe.get("name", "?")
        rc = fe.get("refined_c")
        score = (fe.get("fidelity") or {}).get("score")
        refined_sha = hashlib.sha256((rc or "").encode()).hexdigest()[:12] if rc else "none"
        out.append({
            "slug": _slug(name, rc),
            "command": "oracle RE %s" % name,
            "inputs": [tgt, name],
            "outputs": ["refined_sha:%s" % refined_sha,
                        "fidelity:%s" % ("none" if score is None else score)],
            "status": _status(score),
        })
    return out


def render_arp_block(ev, *, ts):
    """The fenced ```vaked arp_event block for one event. Slug is an IDENT (unquoted)."""
    lines = ["```vaked", "arp_event %s {" % ev["slug"],
             "  ts      = %s" % _vstr(ts),
             "  command = %s" % _vstr(ev["command"])]
    if ev.get("inputs"):
        lines.append("  inputs  = %s" % _vlist(ev["inputs"]))
    if ev.get("outputs"):
        lines.append("  outputs = %s" % _vlist(ev["outputs"]))
    lines.append("  status  = %s" % _vstr(ev["status"]))
    lines += ["}", "```", ""]
    return "\n".join(lines)


_HEADER = ("# vaked-oracle ARP trace\n\nPer-function `arp_event` declarations emitted from "
           "oracle findings (`tools/oracle/arp_emit.py`). Verify: "
           "`python3 tools/arp/verify_log.py docs/oracle/arp-trace.md`.\n\n")


def emit(finding, *, path, ts):
    """Append one `## ts — command` heading + arp_event block per function. Header once."""
    events = finding_to_events(finding)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(_HEADER)
        for ev in events:
            f.write("## %s — %s\n\n%s\n" % (ts, ev["command"], render_arp_block(ev, ts=ts)))
    return len(events)
```

- [ ] **Step 4: run, expect PASS** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -3` → all pass (6 new + 91 prior = 97). The `vakedc check` dogfood test must be green.

- [ ] **Step 5: commit**
```bash
git add tools/oracle/arp_emit.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): arp_emit — findings -> per-function arp_event Vaked declarations (vakedc-check dogfood)"
```

---

### Task 2: CLI `oracle arp-emit`

**Files:** Modify `tools/oracle/oracle.py`; Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: failing test** — append to `tools/oracle/test_oracle.py`:

```python
def test_arp_emit_cli():
    import oracle, tempfile, json, os
    fp = tempfile.mktemp(suffix=".json")
    open(fp, "w").write(json.dumps(_arp_finding()))
    out = tempfile.mktemp(suffix=".md")
    ns = oracle.parse_args(["arp-emit", "--finding", fp, "--out", out, "--ts", "2026-06-16 12:00"])
    assert ns.finding == fp and ns.out == out and ns.ts == "2026-06-16 12:00"
    assert oracle.cmd_arp_emit(ns) == 0
    body = open(out).read()
    assert "arp_event oracle_llama_decode_" in body
    os.remove(fp); os.remove(out)
```

- [ ] **Step 2: run, expect FAIL** — no `arp-emit` subcommand / `cmd_arp_emit`.

- [ ] **Step 3: implement** in `tools/oracle/oracle.py`:
  (a) subparser (alongside the others in `parse_args`):
```python
    a = sub.add_parser("arp-emit", help="emit a finding as per-function arp_event Vaked declarations")
    a.add_argument("--finding", required=True, help="finding JSON (oracle run/team output)")
    a.add_argument("--out", default="docs/oracle/arp-trace.md", help="ARP trace markdown to append to")
    a.add_argument("--ts", default=None, help="timestamp string for the arp_event.ts field")
```
  (b) `cmd_arp_emit` (near the other `cmd_*`):
```python
def cmd_arp_emit(ns: argparse.Namespace) -> int:
    import arp_emit
    import datetime
    with open(ns.finding, encoding="utf-8") as fh:
        finding = json.load(fh)
    ts = ns.ts or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    n = arp_emit.emit(finding, path=ns.out, ts=ts)
    print("arp-emit: wrote %d arp_event(s) to %s" % (n, ns.out))
    return 0
```
  (c) dispatch in `main`: `if ns.cmd == "arp-emit": return cmd_arp_emit(ns)`.

- [ ] **Step 4: run, expect PASS** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -3` → all pass (1 new + 97 = 98).

- [ ] **Step 5: commit**
```bash
git add tools/oracle/oracle.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): oracle arp-emit CLI — finding JSON -> arp_event trace"
```

---

### Task 3: Taskfile targets + docs

**Files:** Modify `tools/oracle/Taskfile.yml`, `docs/oracle/v0.md`, `.DEV.TODO`

- [ ] **Step 1: Taskfile** — append (2-space indent under `tasks:`):
```yaml
  arp:emit:
    desc: "emit a finding as per-function arp_event declarations into docs/oracle/arp-trace.md"
    cmds:
      - python3 tools/oracle/oracle.py arp-emit --finding "{{.FINDING}}" --out "${ARP_OUT:-docs/oracle/arp-trace.md}"
  arp:verify:
    desc: "verify the oracle ARP trace parses+checks as Vaked (dogfood gate)"
    cmds:
      - python3 tools/arp/verify_log.py docs/oracle/arp-trace.md
```
Verify YAML: `python3 -c "import yaml; yaml.safe_load(open('tools/oracle/Taskfile.yml')); print('YAML OK')"`.

- [ ] **Step 2: docs** — add to `docs/oracle/v0.md` (after the thread-2 recursive-self-RE section):
```markdown
## ARP-emission (slice 4b · thread 3)

The oracle emits each reverse-engineered function as a typed `arp_event` Vaked declaration
(`tools/oracle/arp_emit.py` → `docs/oracle/arp-trace.md`): `command="oracle RE <fn>"`,
`inputs=[target, fn]`, `outputs=[refined_sha, fidelity]`, `status=ok|low-fidelity|no-ground-truth`.
The trace is gated by `vakedc check` (`task -d tools/oracle arp:verify`) — Vaked validating the
oracle's own execution record, closing the oracle → Vaked/ARP dogfood loop.

**Lane boundary:** this consumes the `arp_event` builtin schema **read-only** and emits to a
dedicated trace; it does **not** touch the execution ARP IR (a separate workstream). Emit:
`task -d tools/oracle arp:emit FINDING=<finding.json>`.
```
And append to `.DEV.TODO`:
```markdown
### Slice 4b — thread 3 (ARP-emission) — DONE (branch feat/oracle-arp-emit)
oracle findings -> per-function arp_event Vaked declarations (arp_emit.py + `oracle arp-emit` +
arp:emit/arp:verify tasks); gated by vakedc check. Read-only against the arp_event builtin schema;
execution ARP IR untouched. Slice 4b COMPLETE (threads 1,2,3 + dogfeed).
```

- [ ] **Step 3: verify suite green** — `python3 tools/oracle/test_oracle.py 2>&1 | tail -1` → "98 passed, 0 failed".

- [ ] **Step 4: commit**
```bash
git add tools/oracle/Taskfile.yml docs/oracle/v0.md .DEV.TODO
git commit -m "chore(oracle): arp:emit/arp:verify tasks + docs (slice 4b thread 3)"
```

---

## Final verification
- [ ] Full suite green: `python3 tools/oracle/test_oracle.py` → 98 passed.
- [ ] `oracle arp-emit` on a real finding → `docs/oracle/arp-trace.md`; `python3 tools/arp/verify_log.py docs/oracle/arp-trace.md` exits 0 (the dogfood gate).
- [ ] Final whole-branch review (focus: slug always a valid IDENT; emitted blocks always pass vakedc check; execution-ARP-IR untouched).

## Out of scope
Auto-emit from run/team; execution ARP IR; per-step granularity.
