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
                try:
                    rules.add((str(_val(args[0])), int(_val(args[1]))))
                except (TypeError, ValueError):
                    continue   # malformed port -> skip the rule (fail-soft, cf. lower.py _egress_rule)
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
    # NOTE: a membrane's `default` posture is intentionally ignored here — the tool
    # layer is allow-list-only (strictly >= the eBPF deny-by-default posture).
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
