#!/usr/bin/env python3
"""vakedc.overlay — additive execution/capability overlay on the LPG (0015 §4).

Runs AFTER Resolver.build(). Only ADDS nodes/edges; never mutates existing build
logic. Reconstructs node ids by the same path-derived chain rule the resolver
uses (graph.node_id(basename, chain)).
"""
from __future__ import annotations

from . import parser as P
from .graph import GraphNode, GraphEdge, Provenance, Span, node_id

# transition state machine (0015 §4)
_TRANSITIONS = {
    "pause":  ("running", "paused"),
    "resume": ("paused",  "running"),
    "stop":   ("running", "stopped"),
    "rewind": ("paused",  "running"),
}


def _prov(decl, provfile):
    return Provenance(file=provfile, decl=f"{decl.kind} {decl.name}",
                      span=Span(decl.byteStart, decl.byteEnd, decl.line, decl.col))


def _emit_lifecycle(graph, life, chain, owner_id, owner, basename, provfile):
    prov = _prov(owner, provfile)
    needed = {"running"}
    for cl in life.clauses:
        frm, to = _TRANSITIONS[cl.event]
        needed.add(frm); needed.add(to)
    state_id = {}
    for name in sorted(needed):
        sid = node_id(basename, chain + ["state:" + name])
        graph.add_node(GraphNode(id=sid, kind="lifecycle-state", name=name,
                                 labels=["lifecycle-state"],
                                 props={"terminal": name == "stopped"},
                                 provenance=prov))
        state_id[name] = sid
    for cl in life.clauses:
        frm, to = _TRANSITIONS[cl.event]
        tid = node_id(basename, chain + ["transition:" + cl.event])
        graph.add_node(GraphNode(id=tid, kind="transition", name=cl.event,
                                 labels=["transition"], props={"event": cl.event},
                                 provenance=prov))
        graph.add_edge(GraphEdge(owner_id, tid, "controls"))
        graph.add_edge(GraphEdge(tid, state_id[frm], "enabled-in"))
        graph.add_edge(GraphEdge(tid, state_id[to], "results-in"))


def _emit_grants(graph, cap_decl, basename, provfile):
    """capability domain decl -> one `grant` node per declared grant."""
    prov = _prov(cap_decl, provfile)
    for st in cap_decl.body:
        if isinstance(st, P.GrantDecl):
            for gname in st.names:
                gid = node_id(basename, [cap_decl.name, "grant:" + gname])
                graph.add_node(GraphNode(id=gid, kind="grant", name=gname,
                                         labels=["grant"], props={}, provenance=prov))


def _walk(graph, body, chain, owner_id, owner, basename, provfile):
    """Recurse a decl/nodedecl body, dispatching overlay handlers."""
    for st in body:
        if isinstance(st, P.LifecycleDecl):
            _emit_lifecycle(graph, st, chain, owner_id, owner, basename, provfile)
        elif isinstance(st, P.Assignment) and st.target == "capabilities" \
                and isinstance(st.value, P.ListLit):
            for item in st.value.items:
                # parser wraps `domain.grant` as P.App(ref=P.Ref([domain, grant]))
                if isinstance(item, P.App) and item.ref is not None \
                        and isinstance(item.ref, P.Ref) and len(item.ref.parts) == 2:
                    domain, grant = item.ref.parts
                    gid = node_id(basename, [domain, "grant:" + grant])
                    graph.add_edge(GraphEdge(owner_id, gid, "holds"))
        elif isinstance(st, P.NodeDecl):
            child_chain = chain + [st.name]
            child_id = node_id(basename, child_chain)
            _walk(graph, st.body, child_chain, child_id, owner, basename, provfile)
        elif isinstance(st, P.Decl):
            child_chain = chain + [st.name]
            child_id = node_id(basename, child_chain)
            _walk(graph, st.body, child_chain, child_id, st, basename, provfile)


def apply_execution_overlay(graph, items, basename, provfile):
    for it in items:
        if isinstance(it, P.Decl) and it.kind == "capability":
            _emit_grants(graph, it, basename, provfile)
    for it in items:
        if isinstance(it, P.Decl):
            chain = [it.name]
            _walk(graph, it.body, chain, node_id(basename, chain), it, basename, provfile)
