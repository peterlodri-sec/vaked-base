#!/usr/bin/env python3
"""vakedc.oracle — projection-equivalence reference oracle.

``expected_behavior(graph)`` is a pure read-only projection over a built
LPG (as returned by ``vakedc.resolve.build_graph``).  It derives three
canonical summaries that a downstream test suite can assert against:

control_alphabet
    Sorted list of distinct ``event`` values from every ``transition`` node
    in the graph.

capabilities
    Mapping from holder-node *name* to a sorted list of grant-node *name*s,
    derived from every ``holds`` edge (``source → target`` where target is a
    ``grant`` node).

start_order
    List of fiber-name lists, grouped by ascending ``level`` prop.  Each
    inner list is sorted lexicographically.  Only ``fiber`` nodes that carry
    a ``level`` prop are included.
"""

from __future__ import annotations


def expected_behavior(graph) -> dict:
    """Return a dict with keys ``control_alphabet``, ``capabilities``, and
    ``start_order`` derived from *graph*.

    Parameters
    ----------
    graph:
        A :class:`vakedc.graph.Graph` instance (the output of
        ``vakedc.resolve.build_graph``).
    """
    # ------------------------------------------------------------------ #
    # control_alphabet: sorted distinct event values from transition nodes #
    # ------------------------------------------------------------------ #
    events: set[str] = set()
    for node in graph.nodes:
        if node.kind == "transition" and "event" in node.props:
            events.add(node.props["event"])
    control_alphabet = sorted(events)

    # ------------------------------------------------------------------ #
    # capabilities: holder-name -> sorted list of grant-names             #
    # ------------------------------------------------------------------ #
    node_by_id = {n.id: n for n in graph.nodes}
    capabilities: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.label == "holds":
            holder_node = node_by_id.get(edge.source)
            grant_node = node_by_id.get(edge.target)
            if holder_node is not None and grant_node is not None:
                holder_name = holder_node.name
                grant_name = grant_node.name
                capabilities.setdefault(holder_name, []).append(grant_name)
    for key in capabilities:
        capabilities[key] = sorted(capabilities[key])

    # ------------------------------------------------------------------ #
    # start_order: fiber nodes grouped by level, ascending                #
    # ------------------------------------------------------------------ #
    level_map: dict[int, list[str]] = {}
    for node in graph.nodes:
        if node.kind == "fiber" and "level" in node.props:
            lvl = node.props["level"]
            level_map.setdefault(lvl, []).append(node.name)
    start_order = [sorted(level_map[lvl]) for lvl in sorted(level_map)]

    return {
        "control_alphabet": control_alphabet,
        "capabilities": capabilities,
        "start_order": start_order,
    }
