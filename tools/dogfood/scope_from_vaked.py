"""dogfood.scope_from_vaked — lower a Vaked POLA declaration into the kernel's
enforced write-scope.

The kernel's capability scope is no longer hand-typed: it is derived from a Vaked
capability graph (e.g. vaked/examples/dogfood-kernel.vaked) so the declaration and
the enforcement cannot drift. We read the **parsed LPG artifact** (`graph.json`),
not the source — which makes this engine-agnostic: it works whether the LPG was
emitted by `vakedc` (Python) or `vakedz` (Zig), so it survives the planned
vakedc→vakedz cutover.

A principal's write-scope is its `writeScope` open field, granted ONLY if its `fs`
capability is write-capable (`repo_rw`/`host_rw`); a read-only principal
(`repo_ro`/`none`) gets `[]` regardless of any writeScope, and a write-capable
principal with no writeScope refinement also gets `[]` (deny-by-default: an
unrefined repo-wide grant is not a usable narrow scope — set writeScope).

Produce the graph.json first:  python3 -m vakedc parse <file.vaked>   (→ .vaked/graph.json)
"""
from __future__ import annotations

import argparse
import json
import sys

FS_WRITE_GRANTS = {"repo_rw", "host_rw"}


def _grant(ref: str) -> "tuple[str, str] | None":
    if "." not in ref:
        return None
    dom, _, grant = ref.partition(".")
    return dom, grant


def _find_node(graph: dict, principal: str) -> dict:
    for n in graph.get("nodes", []):
        if (n.get("kind") == "node" and n.get("name") == principal
                and "role" in n.get("props", {})):
            return n
    raise KeyError(f"no mesh node named {principal!r} in the graph")


def write_scope(graph: dict, principal: str) -> list[str]:
    """The granted write-path prefixes for ``principal`` (repo-relative)."""
    props = _find_node(graph, principal)["props"]
    fs_grants = {g for c in props.get("capabilities", [])
                 for parsed in [_grant(c.get("ref", ""))] if parsed
                 for dom, g in [parsed] if dom == "fs"}
    if not (fs_grants & FS_WRITE_GRANTS):
        return []                       # read-only principal ⇒ no write authority
    ws = props.get("writeScope") or []
    # values arrive as {"lit": "string", "value": "..."} or bare strings
    return [e["value"] if isinstance(e, dict) else e for e in ws]


def load_graph(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scope_from_vaked")
    ap.add_argument("--graph", default=".vaked/graph.json",
                    help="parsed LPG artifact (vakedc/vakedz `parse` output)")
    ap.add_argument("--principal", required=True, help="mesh node name")
    ap.add_argument("--json", action="store_true", help="emit a JSON list")
    args = ap.parse_args(argv)
    scope = write_scope(load_graph(args.graph), args.principal)
    print(json.dumps(scope) if args.json else ",".join(scope))
    return 0


if __name__ == "__main__":
    sys.exit(main())
