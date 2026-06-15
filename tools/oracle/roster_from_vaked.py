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
