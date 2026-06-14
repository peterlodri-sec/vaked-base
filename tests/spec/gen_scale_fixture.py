#!/usr/bin/env python3
"""gen_scale_fixture — synthetic large inputs for lowering scale tests.

`wavefront.vaked` (3 fibers) is far too small to expose the O(N²) child-lookup
that the adjacency index in `graph.py` fixes. This module generates inputs big
enough to make the curve visible:

  * ``vaked_mesh(n)`` — valid `.vaked` source: one `mesh` containing `n` `node`
    decls (so the mesh has `n` `contains` children). Exercises the FULL pipeline
    (parse → check → lower) at scale. Modeled on
    ``vaked/examples/primitives/mesh.vaked``.
  * ``graph_contains_star(n)`` / ``graph_contains_chain(n)`` — build a
    ``vakedc.graph.Graph`` directly (root + n contains children / a length-n
    contains chain). Targets the graph traversal itself, independent of grammar
    validity, for a robust perf-regression gate.

Run standalone to emit a `.vaked` fixture:  python3 tests/spec/gen_scale_fixture.py 1000 > /tmp/scale.vaked
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from vakedc.graph import Graph, GraphNode, GraphEdge  # noqa: E402


def vaked_mesh(n: int) -> str:
    """A `mesh` with `n` `node` children — `n` `contains` edges. Valid v0.2
    Vaked (each node mirrors the shape in primitives/mesh.vaked: a role string
    and a capabilities list of builtin ref-apps)."""
    lines = ["mesh scalefield {"]
    for i in range(n):
        lines.append(f"  node n{i} {{")
        lines.append('    role = "worker"')
        lines.append("    capabilities = [fs.repo_ro]")
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def graph_contains_star(n: int) -> "tuple[Graph, str]":
    """Graph: one root with `n` direct `contains` children. Returns (graph,
    root_id). The root's child-lookup is O(E)=O(n) under a full scan."""
    g = Graph("scale.vaked")
    root_id = "scale.vaked#root"
    g.add_node(GraphNode(id=root_id, kind="mesh", name="root",
                         labels=["mesh"], props={}, provenance=None))
    for i in range(n):
        cid = f"scale.vaked#root/n{i}"
        g.add_node(GraphNode(id=cid, kind="node", name=f"n{i}",
                             labels=["node"], props={}, provenance=None))
        g.add_edge(GraphEdge(source=root_id, target=cid, label="contains"))
    return g, root_id


def graph_contains_chain(n: int) -> "tuple[Graph, list[str]]":
    """Graph: a length-`n` `contains` chain root -> c0 -> c1 -> ... Returns
    (graph, ordered ids). Every node has exactly one child (or none, the last)."""
    g = Graph("scale.vaked")
    ids = []
    prev = "scale.vaked#root"
    g.add_node(GraphNode(id=prev, kind="mesh", name="root",
                         labels=["mesh"], props={}, provenance=None))
    ids.append(prev)
    for i in range(n):
        cid = f"scale.vaked#root/c{i}"
        g.add_node(GraphNode(id=cid, kind="node", name=f"c{i}",
                             labels=["node"], props={}, provenance=None))
        g.add_edge(GraphEdge(source=prev, target=cid, label="contains"))
        ids.append(cid)
        prev = cid
    return g, ids


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    sys.stdout.write(vaked_mesh(n))
