#!/usr/bin/env python3
"""test_lower_scale — guards the O(N²)→O(N) child-lookup optimization.

Three checks:
  1. CORRECTNESS — `_children_of` (now backed by `graph.edges_from`'s O(1)
     adjacency index) returns exactly what the original O(E) full scan returned,
     same nodes in the same order, for star + chain shapes.
  2. END-TO-END — a generated `mesh` with many `node` children parses, checks
     clean, and lowers without error (exercises the real pipeline at scale).
  3. PERF-REGRESSION — lowering's child traversal over a large graph finishes
     well under a generous ceiling. Under the old O(N²) full-scan (which also
     copied every edge via the `edges` property each call) this blows the
     budget; the linear index keeps it in milliseconds.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (REPO_ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from gen_scale_fixture import vaked_mesh, graph_contains_star, graph_contains_chain  # noqa: E402
from vakedc.parser import parse_source  # noqa: E402
from vakedc.resolve import build_graph  # noqa: E402
from vakedc import check_source, load_builtins, default_builtins_path  # noqa: E402
from vakedc import lower as lower_mod  # noqa: E402
from vakedc.lower import _children_of  # noqa: E402

PERF_N = 30000
PERF_CEILING_S = 3.0  # linear index runs in ~ms; O(N²)+edge-copy would be minutes


def _naive_children(graph, parent_id):
    """The original O(E) full-scan algorithm — reference for correctness."""
    out = []
    for e in graph.edges:
        if e.label == "contains" and e.source == parent_id:
            child = graph.get_node(e.target)
            if child is not None:
                out.append(child)
    return out


def _check_correctness(lines):
    ok = True
    g, root = graph_contains_star(200)
    via_index = _children_of(g, root)
    via_naive = _naive_children(g, root)
    if via_index != via_naive:
        ok = False
        lines.append("  CORRECTNESS: star root children differ index vs naive")
    if len(via_index) != 200:
        ok = False
        lines.append(f"  CORRECTNESS: star root expected 200 children, got {len(via_index)}")
    # a leaf has no children
    leaf = "scale.vaked#root/n0"
    if _children_of(g, leaf) != []:
        ok = False
        lines.append("  CORRECTNESS: leaf should have no children")
    # memoization: same bucket object returned on repeat lookups
    if g.edges_from(root) is not g.edges_from(root):
        ok = False
        lines.append("  CORRECTNESS: edges_from not memoized (rebuilds each call)")

    gc, ids = graph_contains_chain(500)
    # every node except the last has exactly its single successor as child
    for i in range(len(ids) - 1):
        kids = _children_of(gc, ids[i])
        if [k.id for k in kids] != [ids[i + 1]]:
            ok = False
            lines.append(f"  CORRECTNESS: chain node {ids[i]} child mismatch")
            break
    if _children_of(gc, ids[-1]) != []:
        ok = False
        lines.append("  CORRECTNESS: chain tail should have no children")
    if ok:
        lines.append("  CORRECTNESS: index == naive (star + chain), memoized")
    return ok


def _check_end_to_end(lines):
    src = vaked_mesh(200)
    builtins = load_builtins(default_builtins_path())
    diags = check_source(src, "scale.vaked", builtins_cache=builtins)
    if diags:
        lines.append(f"  END-TO-END: generated mesh did not check clean ({len(diags)} diagnostics)")
        return False
    items = parse_source(src, "scale.vaked")
    graph = build_graph(items, "scale.vaked")
    mesh_ids = [n.id for n in graph.nodes if n.kind == "mesh"]
    n_children = len(_children_of(graph, mesh_ids[0])) if mesh_ids else -1
    try:
        lower_mod.lower(graph, items)  # must not raise
    except Exception as e:  # noqa: BLE001
        lines.append(f"  END-TO-END: lower raised {type(e).__name__}: {e}")
        return False
    if n_children != 200:
        lines.append(f"  END-TO-END: mesh expected 200 contains children, got {n_children}")
        return False
    lines.append("  END-TO-END: mesh(200) parse+check(clean)+lower OK, 200 contains children")
    return True


def _check_perf(lines):
    g, _root = graph_contains_star(PERF_N)
    all_ids = [n.id for n in g.nodes]
    t0 = time.perf_counter()
    total = 0
    for pid in all_ids:
        total += len(_children_of(g, pid))
    dt = time.perf_counter() - t0
    ok = dt < PERF_CEILING_S and total == PERF_N
    lines.append(f"  PERF: {len(all_ids)} parents traversed in {dt * 1000:.0f} ms "
                 f"(ceiling {PERF_CEILING_S * 1000:.0f} ms), {total} total contains "
                 f"({'OK' if ok else 'EXCEEDED — possible O(N^2) regression'})")
    return ok


def run():
    lines = []
    ok = True
    ok &= _check_correctness(lines)
    ok &= _check_end_to_end(lines)
    ok &= _check_perf(lines)
    return ok, lines


if __name__ == "__main__":
    ok, lines = run()
    print("\n".join(lines))
    raise SystemExit(0 if ok else 1)
