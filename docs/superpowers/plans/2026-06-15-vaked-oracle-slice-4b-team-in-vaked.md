# vaked-oracle slice 4b · thread 1 — team-in-vaked — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower the slice-4a reverser team (roster + budget + OpenRouter egress membrane) from a Vaked capability graph, so declaration and enforcement cannot drift.

**Architecture:** A new `vaked/examples/oracle-team.vaked` declares the team mesh + two `networkMembrane` egress cordons. `tools/oracle/roster_from_vaked.py` reads the lowered `graph.json` artifact (engine-agnostic) into `(panelists, judge, budget)` and runs a tool-local egress drift-check; `oracle team --from-vaked` uses it instead of a hand-written `panel.example.json`. The same graph lowers (existing vakedc 0012) to `gen/ebpf.policy.json`, the manifest `agent_guardd.policy` consumes.

**Tech Stack:** Python 3 stdlib only (urllib, json, argparse, unittest). vakedc (Python, M3-safe parse/check/lower — no compile). Reuses `tools/oracle/panel.py` + `team.py` (slice 4a) and `agent_guardd/policy.py` read/call-only.

**Spec:** `docs/superpowers/specs/2026-06-15-vaked-oracle-slice-4b-team-in-vaked-design.md`

**Ground-truth LPG shapes (verified by running vakedc on canonical examples):**
- mesh node: `{"kind":"node","name":N,"props":{"capabilities":[{"ref":"network.egress"}],"model":{"lit":"string","value":"..."},"role":{"lit":"string","value":"..."}, ...}}` — open scalars are `{"lit":...,"value":...}`; **numbers arrive as strings** (`{"lit":"number","value":"443"}`).
- networkMembrane: a top-level `{"kind":"network","name":N,"props":{"principal":{"lit":"string","value":"feketecs"},"default":{"value":"deny"},"allow":[{"ref":"egress","args":[{"value":"openrouter.ai"},{"value":"443"}]}]}}`.
- lowered manifest `.vaked/lower/gen/ebpf.policy.json`: `{"runtime":..., "version":1, "membranes":[{"membrane":..,"principal":..,"grant":..,"default":"deny","allow":[{"proto":"tcp","host":"127.0.0.1","cidr":"127.0.0.1/32","port":9}]}]}` — exactly what `agent_guardd.policy.load_policy` parses. An IP host gets `/32`; a DNS host (`openrouter.ai`) is un-attestable at `decide()` (non-IP → deny) — the documented gap.

**Constraints:** never build/compile on the M3 (vakedc parse/check/lower is pure Python = allowed) · revdev unprivileged · Snyk OFF · reuse `panel.py`/`team.py`/`agent_guardd` read-call-only · never print the OpenRouter key · codenames ASCII-only.

---

### Task 1: `oracle-team.vaked` — the team capability graph + two egress cordons

**Files:**
- Create: `vaked/examples/oracle-team.vaked`

- [ ] **Step 1: Write the declaration**

Create `vaked/examples/oracle-team.vaked`:

```
# oracle-team.vaked — the slice-4a reverser TEAM's OWN capability graph
# (tools/oracle/{panel,team,memory}.py, docs/oracle/v0.md), declared in Vaked so the
# team's roster + budget + egress are LOWERED from this declaration instead of a
# hand-written panel.example.json (tools/oracle/roster_from_vaked.py). Declaration
# and enforcement cannot drift — dogfood symmetry with oracle-re-loop.vaked, now for
# an agent that LEAVES the box (OpenRouter egress).
#
# POLA: local panelists reach their model on loopback only; the two OpenRouter nodes
# (feketecs, anstetten) hold network.egress refined by a deny-by-default
# networkMembrane allowing ONLY openrouter.ai:443. The operator holds the attenuated
# superset every node delegates from.
#
# NOTE on roster open fields (`endpoint`, `keyEnv`, `temperature`, `reasoningEffort`,
# `budgetCalls`): these ride the OPEN `meshNode` schema as descriptive fields — the
# same stopgap as `writeScope` in dogfood-kernel.vaked. Follow-up: a roster-field
# schema. The EGRESS, by contrast, is modelled properly via `networkMembrane`.
#
# NOTE on the cordon: agent_guardd.decide() attests IP literals only, so the
# openrouter.ai (DNS) rule lowers descriptively but is un-attestable at the packet
# layer; roster_from_vaked.check_roster_egress enforces it at the tool layer. A local
# egress proxy (pinned loopback IP) is the path to full packet attestation — follow-up.

runtime "oracle-team" {
  systems = ["aarch64-darwin", "x86_64-linux"]   # M3 orchestrates; dev-cx53 runs the heavy work

  mesh oracleTeam {
    node operator {
      role = "control-plane"
      capabilities = [fs.repo_rw, network.egress, mem.admin]
    }
    node coordinator {
      # holds network.egress because it SUB-DELEGATES egress to feketecs/anstetten;
      # the checker refuses an edge whose child grant exceeds the parent's (lattice
      # none < loopback < lan < egress), so coordinator must dominate its children.
      role = "coordinate"
      capabilities = [fs.repo_rw, network.egress, mem.admin]
      budgetCalls = 30
    }
    node infralight {
      role = "panelist"
      model = "qwen2.5-coder-3b-instruct"
      capabilities = [network.loopback, mem.recall]
      endpoint = "http://127.0.0.1:8091/v1/chat/completions"
      temperature = 0
    }
    node staticarmor {
      role = "panelist"
      model = "llm4decompile"
      capabilities = [network.loopback, mem.recall]
      endpoint = "http://127.0.0.1:8090/v1/chat/completions"
      temperature = 0
    }
    node feketecs {
      role = "panelist"
      model = "deepseek/deepseek-v4-flash"
      capabilities = [network.egress, mem.recall]
      endpoint = "https://openrouter.ai/api/v1/chat/completions"
      keyEnv = "OPENROUTER_API_KEY"
      temperature = 1
    }
    node anstetten {
      role = "judge"
      model = "deepseek/deepseek-v4-pro"
      capabilities = [network.egress, mem.recall]
      endpoint = "https://openrouter.ai/api/v1/chat/completions"
      keyEnv = "OPENROUTER_API_KEY"
      temperature = 1
      reasoningEffort = "high"
    }

    operator -> coordinator
    coordinator -> infralight
    coordinator -> staticarmor
    coordinator -> feketecs
    coordinator -> anstetten
  }

  # Loopback cordons: deny-by-default, allow ONLY each local model's port. These
  # lower to real IP rules (127.0.0.1/32:port) — fully eBPF-attestable.
  network infralightCordon  { principal = "infralight"  default = "deny" allow = [ egress("127.0.0.1", 8091) ] }
  network staticarmorCordon { principal = "staticarmor" default = "deny" allow = [ egress("127.0.0.1", 8090) ] }
  # OpenRouter cordons: the egress() DNS host is DROPPED at lower (the 0012 emitter
  # can't compute a CIDR for a non-IP host) → these lower to deny-all (allow []).
  # So OpenRouter egress is un-attestable at the packet layer and is enforced ONLY by
  # roster_from_vaked.check_roster_egress at the tool layer (the documented gap).
  network feketecsCordon  { principal = "feketecs"  default = "deny" allow = [ egress("openrouter.ai", 443) ] }
  network anstettenCordon { principal = "anstetten" default = "deny" allow = [ egress("openrouter.ai", 443) ] }
}
```

**Verified empirically (during planning):** this `check`s clean and `lower` emits an
`infralightCordon`/`staticarmorCordon` with real `127.0.0.1/32` IP rules + `feketecs`/
`anstetten` cordons with `allow: []` (DNS dropped). The egress edges do not escalate
because `coordinator` holds `network.egress`.

- [ ] **Step 2: Verify it parses + type-checks + lowers**

Run (from worktree root — vakedc is pure Python, M3-safe):
```bash
python3 -m vakedc check vaked/examples/oracle-team.vaked && \
python3 -m vakedc lower vaked/examples/oracle-team.vaked
```
Expected: `check` exits 0 (no escalation errors); `lower` writes `.vaked/lower/...` including `gen/ebpf.policy.json`. If `check` reports an unknown-field or escalation error, fix the declaration (open fields are allowed on `meshNode`; an edge must not grant more than the parent — `operator` is the superset). If `lower` rejects the DNS host in `egress("openrouter.ai", 443)`, keep the rule and note it (descriptive); it must at least parse+check.

- [ ] **Step 3: Verify the graph shape the reader depends on**

Run:
```bash
python3 -m vakedc parse vaked/examples/oracle-team.vaked >/dev/null 2>&1 && \
python3 -c '
import json; g=json.load(open(".vaked/graph.json"))
nodes={n["name"]:n for n in g["nodes"] if n.get("kind")=="node"}
nets=[n for n in g["nodes"] if n.get("kind")=="network"]
assert "feketecs" in nodes and "anstetten" in nodes, "missing roster nodes"
assert nodes["feketecs"]["props"]["endpoint"]["value"].startswith("https://openrouter.ai")
principals = {n["props"]["principal"]["value"] for n in nets}
assert {"feketecs", "anstetten", "infralight"} <= principals, "missing cordons"
print("graph shape OK:", sorted(nodes), "membranes:", sorted(principals))
'
rm -rf .vaked
```
Expected: `graph shape OK: [...] membranes: ['anstetten', 'feketecs', 'infralight', 'staticarmor']`.

- [ ] **Step 4: Commit**

```bash
git add vaked/examples/oracle-team.vaked
git commit -m "feat(oracle): oracle-team.vaked — the reverser team's capability graph + egress cordons"
```

---

### Task 2: `roster_from_vaked.py` — graph → (panelists, judge, budget)

**Files:**
- Create: `tools/oracle/roster_from_vaked.py`
- Test: `tools/oracle/test_oracle.py` (append to the existing stdlib suite)

This task adds the module skeleton + roster extraction. The egress check is Task 3.

- [ ] **Step 1: Write the failing test**

Append to `tools/oracle/test_oracle.py` (inside the existing test class / module — it uses plain `unittest`). Add a fixture helper + tests:

```python
# ---- slice 4b thread 1: team-in-vaked ----
def _team_graph():
    """A minimal lowered-LPG fixture mirroring oracle-team.vaked (numbers are strings)."""
    def s(v): return {"lit": "string", "value": v}
    def num(v): return {"lit": "number", "value": v}
    def cap(ref): return {"ref": ref}
    return {"version": 1, "nodes": [
        {"kind": "node", "name": "operator", "props": {
            "role": s("control-plane"), "capabilities": [cap("fs.repo_rw"), cap("network.egress"), cap("mem.admin")]}},
        {"kind": "node", "name": "coordinator", "props": {
            "role": s("coordinate"), "capabilities": [cap("fs.repo_rw"), cap("network.loopback")], "budgetCalls": num("30")}},
        {"kind": "node", "name": "infralight", "props": {
            "role": s("panelist"), "model": s("qwen2.5-coder-3b-instruct"),
            "capabilities": [cap("network.loopback")],
            "endpoint": s("http://127.0.0.1:8091/v1/chat/completions"), "temperature": num("0")}},
        {"kind": "node", "name": "feketecs", "props": {
            "role": s("panelist"), "model": s("deepseek/deepseek-v4-flash"),
            "capabilities": [cap("network.egress")],
            "endpoint": s("https://openrouter.ai/api/v1/chat/completions"),
            "keyEnv": s("OPENROUTER_API_KEY"), "temperature": num("1")}},
        {"kind": "node", "name": "anstetten", "props": {
            "role": s("judge"), "model": s("deepseek/deepseek-v4-pro"),
            "capabilities": [cap("network.egress")],
            "endpoint": s("https://openrouter.ai/api/v1/chat/completions"),
            "keyEnv": s("OPENROUTER_API_KEY"), "temperature": num("1"), "reasoningEffort": s("high")}},
        {"kind": "network", "name": "feketecsCordon", "props": {
            "principal": s("feketecs"), "default": s("deny"),
            "allow": [{"ref": "egress", "args": [s("openrouter.ai"), num("443")]}]}},
        {"kind": "network", "name": "anstettenCordon", "props": {
            "principal": s("anstetten"), "default": s("deny"),
            "allow": [{"ref": "egress", "args": [s("openrouter.ai"), num("443")]}]}},
    ]}


class TestRosterFromVaked(unittest.TestCase):
    def test_load_roster_extracts_panelists_judge_budget(self):
        import os
        import roster_from_vaked as rfv
        os.environ["OPENROUTER_API_KEY"] = "test-key-not-real"
        try:
            panelists, judge, budget = rfv.load_roster_from_graph(_team_graph())
        finally:
            os.environ.pop("OPENROUTER_API_KEY", None)
        names = sorted(p.name for p in panelists)
        self.assertEqual(names, ["feketecs", "infralight"])      # judge excluded
        self.assertEqual(getattr(judge, "model", None), "deepseek/deepseek-v4-pro")
        self.assertEqual(budget, 30)
        feke = next(p for p in panelists if p.name == "feketecs")
        self.assertEqual(feke.client.temperature, 1.0)            # number-string coerced
        self.assertEqual(judge.reasoning_effort, "high")

    def test_load_roster_drops_node_with_absent_key_env(self):
        import os
        import roster_from_vaked as rfv
        os.environ.pop("OPENROUTER_API_KEY", None)               # ensure absent
        panelists, judge, budget = rfv.load_roster_from_graph(_team_graph())
        names = sorted(p.name for p in panelists)
        self.assertEqual(names, ["infralight"])                   # feketecs dropped (no key)
        # anstetten (judge) also dropped -> keyless fallback to first panelist
        self.assertIs(judge, panelists[0].client)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -5`
Expected: FAIL — `ModuleNotFoundError: No module named 'roster_from_vaked'`.

- [ ] **Step 3: Write the implementation**

Create `tools/oracle/roster_from_vaked.py`:

```python
"""roster_from_vaked — derive the slice-4a reverser team from a Vaked graph.

Engine-agnostic: reads the lowered LPG artifact (graph.json from `vakedc`/`vakedz`
parse), so it survives the vakedc->vakedz cutover. Closes roster/budget/egress drift:
the team's panelists, judge, budget, and egress allow-set come from
vaked/examples/oracle-team.vaked instead of a hand-written panel.example.json.

POLA egress check (check_roster_egress, see below): every node that carries an
`endpoint` must reach loopback OR a (host, port) inside its networkMembrane
allow-set; a roster reaching an undeclared host is rejected. Tool-local analog of
the language's E-CAP-USE check; promote to a vakedc E-EGRESS-USE pass later.

Pure stdlib.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlsplit

import panel as P

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def load_graph(path):
    with open(path) as f:
        return json.load(f)


def _val(v):
    """Unwrap a graph scalar ({"lit":..,"value":..} or bare) to its python value."""
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def _mesh_nodes(graph):
    """name -> props for every mesh node (kind 'node')."""
    return {n["name"]: n.get("props", {})
            for n in graph.get("nodes", []) if n.get("kind") == "node"}


def _roster_nodes(nodes):
    """The panelist/judge nodes: those carrying an `endpoint` (operator/coordinator have none)."""
    return {name: props for name, props in nodes.items() if props.get("endpoint")}


def load_roster_from_graph(graph):
    """(panelists, judge, budget). Builds panel.OpenAIChatClient per endpoint node;
    role=='judge' -> judge; coordinator (role 'coordinate') budgetCalls -> budget.
    A node whose keyEnv is set-but-absent is dropped (stderr), mirroring
    panel.load_roster; a keyless judge falls back to the first panelist."""
    nodes = _mesh_nodes(graph)
    panelists, judge = [], None
    for name, props in sorted(_roster_nodes(nodes).items()):
        key_env = _val(props.get("keyEnv"))
        key = ""
        if key_env:
            key = os.environ.get(key_env, "")
            if not key:
                print(f"roster_from_vaked: dropping {name} — env {key_env} not set", file=sys.stderr)
                continue
        client = P.OpenAIChatClient(
            _val(props.get("endpoint")), _val(props.get("model")), key,
            temperature=float(_val(props.get("temperature")) or 0),
            reasoning_effort=_val(props.get("reasoningEffort")))
        if _val(props.get("role")) == "judge":
            judge = client
        else:
            panelists.append(P.Panelist(name=name, client=client))
    if judge is None and panelists:
        judge = panelists[0].client
    budget = 30
    for props in nodes.values():
        if _val(props.get("role")) == "coordinate" and props.get("budgetCalls") is not None:
            budget = int(_val(props.get("budgetCalls")))
            break
    return panelists, judge, budget
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -3`
Expected: PASS (the two new tests + the existing 72 all green).

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/roster_from_vaked.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): roster_from_vaked — derive panelists/judge/budget from the Vaked graph"
```

---

### Task 3: `check_roster_egress` — the egress drift check (POLA)

**Files:**
- Modify: `tools/oracle/roster_from_vaked.py`
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test**

Append to `tools/oracle/test_oracle.py`:

Module-level `test_*` functions with plain `assert` (the file's convention — NO `unittest`/`TestCase`, or the custom runner silently skips them):

```python
def test_egress_check_clean_graph_has_no_violations():
    import roster_from_vaked as rfv
    assert rfv.check_roster_egress(_team_graph()) == []


def test_egress_check_loopback_endpoint_needs_no_membrane():
    import roster_from_vaked as rfv
    g = _team_graph()
    # drop both cordons; loopback nodes still clean, egress nodes now violate
    g["nodes"] = [n for n in g["nodes"] if n.get("kind") != "network"]
    names = sorted(v["node"] for v in rfv.check_roster_egress(g))
    assert names == ["anstetten", "feketecs"]            # loopback infralight is clean


def test_egress_check_endpoint_outside_allow_set_is_a_violation():
    import roster_from_vaked as rfv
    g = _team_graph()
    # point feketecs at an undeclared host
    for n in g["nodes"]:
        if n.get("name") == "feketecs":
            n["props"]["endpoint"] = {"lit": "string", "value": "https://evil.example/v1/chat/completions"}
    viol = rfv.check_roster_egress(g)
    assert [v["node"] for v in viol] == ["feketecs"]
    assert viol[0]["host"] == "evil.example"
    assert viol[0]["port"] == 443
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -5`
Expected: FAIL — `AttributeError: module 'roster_from_vaked' has no attribute 'check_roster_egress'`.

- [ ] **Step 3: Write the implementation**

Append to `tools/oracle/roster_from_vaked.py`:

```python
def membrane_allow(graph):
    """principal -> set of (host, port) allow rules from networkMembrane (kind 'network') nodes."""
    out = {}
    for n in graph.get("nodes", []):
        if n.get("kind") != "network":
            continue
        props = n.get("props", {})
        principal = _val(props.get("principal"))
        if principal is None:
            continue
        rules = set()
        for r in props.get("allow", []):
            if r.get("ref") != "egress":
                continue
            args = r.get("args", [])
            if len(args) >= 2:
                rules.add((str(_val(args[0])), int(_val(args[1]))))
        out.setdefault(principal, set()).update(rules)
    return out


def _endpoint_host_port(endpoint):
    """(host, port) from an endpoint URL; default port by scheme."""
    u = urlsplit(endpoint or "")
    host = u.hostname or ""
    port = u.port or (443 if u.scheme == "https" else 80)
    return host, port


def check_roster_egress(graph):
    """Drift check: each endpoint node must reach loopback OR a (host, port) in its
    own networkMembrane allow-set. Returns [] when clean (deny-by-default). The
    tool-local E-EGRESS-USE analog; non-empty -> the caller must reject the run."""
    nodes = _mesh_nodes(graph)
    allow = membrane_allow(graph)
    violations = []
    for name, props in sorted(_roster_nodes(nodes).items()):
        host, port = _endpoint_host_port(_val(props.get("endpoint")))
        if host in LOOPBACK_HOSTS:
            continue
        if (host, port) in allow.get(name, set()):
            continue
        violations.append({"node": name, "host": host, "port": port,
                           "reason": "host:port not in node's networkMembrane allow-set (deny-by-default)"})
    return violations
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -3`
Expected: PASS (3 new + all prior green).

- [ ] **Step 5: Commit**

```bash
git add tools/oracle/roster_from_vaked.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): check_roster_egress — reject a roster reaching an undeclared host (POLA)"
```

---

### Task 4: wire `oracle team --from-vaked` (with egress reject)

**Files:**
- Modify: `tools/oracle/oracle.py` (team subparser lines 74-83; `cmd_team` 216-240)
- Test: `tools/oracle/test_oracle.py`

- [ ] **Step 1: Write the failing test**

Append to `tools/oracle/test_oracle.py`:

Module-level `test_*` functions (file convention); `assertRaises(SystemExit)` becomes a `try/except`:

```python
def test_team_from_vaked_parses():
    import oracle
    ns = oracle.parse_args(["team", "--target", "/bin/true", "--funcs", "f",
                            "--from-vaked", "graph.json"])
    assert ns.from_vaked == "graph.json"
    assert ns.panel is None


def test_team_panel_and_from_vaked_mutually_exclusive():
    import oracle
    try:
        oracle.parse_args(["team", "--target", "/bin/true", "--funcs", "f",
                           "--panel", "p.json", "--from-vaked", "graph.json"])
        assert False, "expected SystemExit (mutually exclusive)"
    except SystemExit:
        pass


def test_team_requires_one_roster_source():
    import oracle
    try:
        oracle.parse_args(["team", "--target", "/bin/true", "--funcs", "f"])
        assert False, "expected SystemExit (one of --panel/--from-vaked required)"
    except SystemExit:
        pass
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -5`
Expected: FAIL — `--from-vaked` unrecognized / `ns` has no `from_vaked` (and currently `--panel` is required so the third test would pass for the wrong reason).

- [ ] **Step 3: Edit the team subparser**

In `tools/oracle/oracle.py`, replace the current `--panel` line (74-83 block) so `--panel` and `--from-vaked` form a required mutually-exclusive group, and `--budget-calls` defaults to `None` (so the graph budget can fill in):

```python
    t = sub.add_parser("team", help="reverser debate-panel team (slice 4a/4b)")
    t.add_argument("--target", required=True)
    t.add_argument("--funcs", required=True, type=lambda s: [x for x in s.split(",") if x])
    src = t.add_mutually_exclusive_group(required=True)
    src.add_argument("--panel", help="roster JSON (see panel.example.json)")
    src.add_argument("--from-vaked", dest="from_vaked",
                     help="lowered graph.json — derive roster+budget+egress, with the POLA egress check")
    t.add_argument("--pyghidra-python", default=os.environ.get("ORACLE_PYGHIDRA_PYTHON", "python3"))
    t.add_argument("--source-dir", default=None, help="ground-truth source (fidelity + crabcc/ctags investigate)")
    t.add_argument("--crabcc-root", default=None, help="crabcc/ctags index root (defaults to --source-dir)")
    t.add_argument("--budget-calls", type=int, default=None)
    t.add_argument("--max-workers", type=int, default=4)
    t.add_argument("--memory", default=os.path.join(ORACLE_DIR, "dossier.jsonl"))
    return p.parse_args(argv)
```

- [ ] **Step 4: Run to verify the arg tests pass**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -3`
Expected: the 3 `TestTeamFromVakedArgs` tests PASS. (Existing tests that called `team` with `--budget-calls` still work; any that relied on the old default `60` now get `None` — handled in Step 5.)

- [ ] **Step 5: Edit `cmd_team` to branch on `--from-vaked` + reject on egress violation**

Replace the head of `cmd_team` (lines 216-221) with the branch below, and update the `run_team(...)` call's `budget_calls=` argument (line 236) to use the effective budget:

```python
def cmd_team(ns: argparse.Namespace) -> int:
    import investigate as inv
    if ns.from_vaked:
        import roster_from_vaked as rfv
        graph = rfv.load_graph(ns.from_vaked)
        violations = rfv.check_roster_egress(graph)
        if violations:
            for v in violations:
                print(f"team: EGRESS VIOLATION node={v['node']} reaches "
                      f"{v['host']}:{v['port']} — {v['reason']}")
            return 1
        panelists, judge, graph_budget = rfv.load_roster_from_graph(graph)
    else:
        panelists, judge, graph_budget = (*panel_mod.load_roster(ns.panel), 60)
    if not panelists:
        print("team: no usable panelists (check roster / keys)")
        return 1
    budget_calls = ns.budget_calls if ns.budget_calls is not None else graph_budget
```

Then in the `run_team(...)` call change `budget_calls=ns.budget_calls` to `budget_calls=budget_calls`.

- [ ] **Step 6: Run the full suite**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -3`
Expected: PASS (all tests green).

- [ ] **Step 7: Commit**

```bash
git add tools/oracle/oracle.py tools/oracle/test_oracle.py
git commit -m "feat(oracle): team --from-vaked — graph-derived roster + reject on egress drift"
```

---

### Task 5: manifest interop — the lowered policy loads in agent_guardd + attests the DNS gap

**Files:**
- Test: `tools/oracle/test_oracle.py` (test-only; proves the lowered `ebpf.policy.json` is consumable and the DNS host is un-attestable)

- [ ] **Step 1: Write the failing test**

Append to `tools/oracle/test_oracle.py`:

Module-level functions (file convention; `sys` is already imported at the top of `test_oracle.py`):

```python
def _ebpf_policy_doc():
    # the exact shape vakedc lower emits for oracle-team: loopback cordon gets a real
    # IP rule; the OpenRouter cordon's DNS host is DROPPED at lower -> allow [].
    return {"runtime": "oracle-team", "version": 1, "membranes": [
        {"membrane": "infralightCordon", "principal": "infralight", "grant": "network.loopback",
         "default": "deny", "allow": [
             {"proto": "tcp", "host": "127.0.0.1", "cidr": "127.0.0.1/32", "port": 8091}]},
        {"membrane": "feketecsCordon", "principal": "feketecs", "grant": "network.egress",
         "default": "deny", "allow": []},      # DNS host dropped at lower -> deny-all
    ]}


def test_ebpf_manifest_loads_and_decides():
    import os
    import json
    import tempfile
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # repo root for agent_guardd
    from agent_guardd import policy as agp
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(_ebpf_policy_doc(), f)
        path = f.name
    pol = agp.load_policy(path)
    loop = pol.membrane_for("infralight")
    feke = pol.membrane_for("feketecs")
    # loopback IP rule -> enforceable (fully eBPF-attestable)
    assert agp.decide(loop, "127.0.0.1", 8091)[0] == "allow"
    assert agp.decide(loop, "127.0.0.1", 9999)[0] == "deny"
    # OpenRouter cordon -> deny-all (DNS dropped at lower; also non-IP at decide). The
    # documented gap: packet-layer egress to OpenRouter is un-attestable; the tool-layer
    # check_roster_egress is the only enforcement.
    assert agp.decide(feke, "openrouter.ai", 443)[0] == "deny"
    os.unlink(path)
```

- [ ] **Step 2: Run to verify it fails first, then passes**

Run: `python3 tools/oracle/test_oracle.py 2>&1 | tail -5`
Expected: PASS immediately (no new product code — this is a characterization/interop test). If `ImportError: agent_guardd` → the repo-root `sys.path.insert` is wrong; fix the relative path so `agent_guardd` (a top-level package) imports. The test must end green, proving (a) the manifest the graph lowers to is consumable by the real daemon and (b) the DNS cordon is denied at `decide()` — exactly the gap the spec flags.

- [ ] **Step 3: Commit**

```bash
git add tools/oracle/test_oracle.py
git commit -m "test(oracle): lowered ebpf.policy loads in agent_guardd; DNS cordon un-attestable (gap attested)"
```

---

### Task 6: `team:vaked` Taskfile target

**Files:**
- Modify: `tools/oracle/Taskfile.yml` (add a task after the existing `team:` task, ~line 99)

- [ ] **Step 1: Add the task**

Append to `tools/oracle/Taskfile.yml`:

```yaml
  team:vaked:
    desc: "team-in-vaked (slice 4b): lower oracle-team.vaked -> graph.json + ebpf.policy.json, then run the graph-derived team (dev-cx53). Auto-sources ~/.config/oracle/openrouter.env"
    vars:
      VAKED: '{{.VAKED | default "vaked/examples/oracle-team.vaked"}}'
    cmds:
      - |
        [ -f ~/.config/oracle/openrouter.env ] && . ~/.config/oracle/openrouter.env || true   # diverse-panel key (no-op if absent)
        python3 -m vakedc parse {{.VAKED}}
        python3 -m vakedc lower {{.VAKED}}     # emits .vaked/lower/gen/ebpf.policy.json (agent_guardd manifest)
        export GHIDRA_INSTALL_DIR=$(for d in /nix/store/*ghidra*/lib/ghidra; do [ -d "$d/Ghidra" ] && echo "$d" && break; done)
        export JAVA_HOME=$(for d in /nix/store/*openjdk*; do [ -x "$d/bin/java" ] && echo "$d" && break; done)
        export ORACLE_LIBSTDCXX_DIR=$(dirname $(find /nix/store/*gcc*lib*/lib -name libstdc++.so.6 2>/dev/null | head -1))
        export ORACLE_PYGHIDRA_PYTHON=$HOME/oracle/pgvenv/bin/python
        ORACLE_DIR="${ORACLE_DIR:-$HOME/oracle/team-vaked-run}" python3 tools/oracle/oracle.py team \
          --target {{.TARGET}} --funcs {{.FUNCS}} --from-vaked .vaked/graph.json \
          --pyghidra-python "$ORACLE_PYGHIDRA_PYTHON" \
          --source-dir "${LLAMA_CPP_SRC:-$HOME/oracle/llama.cpp-src}" \
          --crabcc-root "${LLAMA_CPP_SRC:-$HOME/oracle/llama.cpp-src}" \
          --memory "$HOME/oracle/dossier.jsonl"
```

- [ ] **Step 2: Verify the Taskfile is valid YAML and the task is listed**

Run: `cd tools/oracle && task --list 2>&1 | grep -E "team:vaked"` (or `python3 -c 'import yaml,sys; yaml.safe_load(open("tools/oracle/Taskfile.yml"))'` if `task`/PyYAML unavailable on the M3 — at minimum confirm the file parses).
Expected: the `team:vaked` task appears / the YAML parses without error. (No team run on the M3 — that is the on-box acceptance.)

- [ ] **Step 3: Commit**

```bash
git add tools/oracle/Taskfile.yml
git commit -m "chore(oracle): team:vaked task — lower oracle-team.vaked then run the graph-derived team"
```

---

### Task 7: docs — v0.md team-in-vaked section + .DEV.TODO

**Files:**
- Modify: `docs/oracle/v0.md` (add a "team-in-vaked (slice 4b · thread 1)" subsection near the team-mode section ~line 129)
- Modify: `.DEV.TODO`

- [ ] **Step 1: Add the v0.md section**

Add after the team-mode acceptance blocks in `docs/oracle/v0.md`:

```markdown
## Team-in-vaked (slice 4b · thread 1)

The slice-4a team is now declared in Vaked (`vaked/examples/oracle-team.vaked`) and its
roster + budget + egress are **lowered from the graph** — no drift. `oracle team
--from-vaked <graph.json>` (via `tools/oracle/roster_from_vaked.py`) replaces the
hand-written `panel.example.json`: panelists/judge/budget come from the mesh nodes, and
`check_roster_egress` rejects any roster reaching a host outside its `networkMembrane`
allow-set (the tool-local POLA / E-EGRESS-USE analog). The same graph lowers (vakedc
0012) to `gen/ebpf.policy.json`, the manifest `agent_guardd.policy` consumes.

**The DNS/IP attestation gap (deliberate, documented).** `agent_guardd.decide()` attests
IP literals only; `openrouter.ai` is reached by hostname (Cloudflare, rotating IPs), so
the cordon is enforced at the **tool layer** (`check_roster_egress`, hostname-aware) and
carried into the manifest as a **non-attestable** DNS rule (denied at `decide()`).
Loopback panelists are fully eBPF-attestable. Full packet attestation needs a local
egress proxy with a pinned loopback IP — a follow-up, with the vakedc `E-EGRESS-USE` pass.

Reproduce: `task -d tools/oracle team:vaked` (auto-sources the staged OpenRouter key).
```

- [ ] **Step 2: Update .DEV.TODO**

In `.DEV.TODO`, add under the slice-4b area:
```markdown
### Slice 4b — thread 1 (team-in-vaked) — IN PROGRESS (branch feat/oracle-team-in-vaked)
oracle-team.vaked + roster_from_vaked (graph -> roster/judge/budget + egress drift check)
+ `team --from-vaked` + agent_guardd manifest interop. Follow-ups: vakedc E-EGRESS-USE
pass (RFC like 0027); local egress proxy for full OpenRouter packet attestation.
Next threads: 2 (RE-vakedz), 3 (ARP-emission, deferred — other dev's lane).
```

- [ ] **Step 3: Commit**

```bash
git add docs/oracle/v0.md .DEV.TODO
git commit -m "docs(oracle): team-in-vaked section + .DEV.TODO slice-4b thread 1"
```

---

## Final verification (after all tasks)

- [ ] Full suite green on the M3: `python3 tools/oracle/test_oracle.py` → all tests pass (72 baseline + ~9 new).
- [ ] `python3 -m vakedc check vaked/examples/oracle-team.vaked` exits 0; `lower` emits `gen/ebpf.policy.json`.
- [ ] Dispatch a final code review over the whole branch diff (subagent-driven-development final reviewer).

## On-box acceptance (dev-cx53 — separate, not on the M3)

The diverse-panel run is the acceptance, now graph-driven (mirrors the slice-4a diverse acceptance):
- `ssh dev@100.105.72.88` (servers up: qwen :8091, llm4decompile :8090; OpenRouter key staged at `~revdev/.config/oracle/openrouter.env`, 600 — never print it).
- Deploy the branch (`git archive feat/oracle-team-in-vaked tools vaked eventd agent_guardd | ssh … tar -x -C ~revdev/oracle-code`).
- On the box: `python3 -m vakedc parse+lower vaked/examples/oracle-team.vaked` → `graph.json` + `ebpf.policy.json`; `oracle team --from-vaked graph.json --target … --funcs llama_decode`.
- Expect: `check_roster_egress` clean → roster built (feketecs + locals + anstetten judge) → the pro judge adjudicates ≥2 divergent candidates (same evidence shape as slice 4a) → ledger `chain_ok`, the-dossier note, real OpenRouter cost; `agent_guardd.policy.load_policy(gen/ebpf.policy.json)` loads + `decide()` allows loopback / denies the DNS host. Record in `docs/oracle/v0.md`.

## Out of scope (own cycles)
vakedc `E-EGRESS-USE` checker pass · local egress proxy (full OpenRouter attestation) · live eBPF on the box (revdev unprivileged) · Thread 2 (RE-vakedz) · Thread 3 (ARP-emission, deferred — other dev's lane).
