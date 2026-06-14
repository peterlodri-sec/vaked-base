#!/usr/bin/env python3
"""vakedc.schedule — static parallel schedule (0015 §5).

Pure function of a parallel group's fibers: dependency DAG (A depends-on B when
A's `input` ref matches B's `output` ref) -> cycle check -> longest-path
wavefront levels -> one checkpoint per boundary. Consumed by both check.py
(diagnostics) and overlay.py (IR materialization). Deterministic: all iteration
over sorted names.
"""
from __future__ import annotations
from dataclasses import dataclass

from . import parser as P


@dataclass
class FiberIO:
    name: str
    inputs: "frozenset[str]"
    outputs: "frozenset[str]"


@dataclass
class Schedule:
    levels: dict
    deps: list
    checkpoints: list
    rewindable: dict
    cycle: "list | None"


def _ref_str(value):
    return ".".join(value.parts) if isinstance(value, P.Ref) else None


def fiber_ios(member_decls):
    """member_decls: list[P.Decl] (the group's fibers). -> list[FiberIO]."""
    out = []
    for d in member_decls:
        inputs, outputs = set(), set()
        for st in d.body:
            if isinstance(st, P.Assignment):
                rs = _ref_str(st.value)
                if rs is None:
                    continue
                if st.target == "input":
                    inputs.add(rs)
                elif st.target == "output":
                    outputs.add(rs)
        out.append(FiberIO(d.name, frozenset(inputs), frozenset(outputs)))
    return out


def member_names(group_decl):
    """Names listed in a parallel group's `fibers = [a, b, ...]`."""
    names = []
    for st in group_decl.body:
        if isinstance(st, P.Assignment) and st.target == "fibers" \
                and isinstance(st.value, P.ListLit):
            for item in st.value.items:
                if isinstance(item, P.Ref) and len(item.parts) == 1:
                    names.append(item.parts[0])
    return names


def _find_cycle(adj):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    stack = []

    def dfs(n):
        color[n] = GRAY
        stack.append(n)
        for m in sorted(adj[n]):
            if color[m] == GRAY:
                return stack[stack.index(m):] + [m]
            if color[m] == WHITE:
                r = dfs(m)
                if r:
                    return r
        stack.pop()
        color[n] = BLACK
        return None

    for n in sorted(adj):
        if color[n] == WHITE:
            r = dfs(n)
            if r:
                return r
    return None


def compute_schedule(fiber_io_list, retained=frozenset()):
    ios = sorted(fiber_io_list, key=lambda f: f.name)
    by_output = {}
    for f in ios:
        for o in sorted(f.outputs):
            by_output.setdefault(o, f.name)
    adj = {f.name: set() for f in ios}
    deps = []
    for f in ios:
        for inp in sorted(f.inputs):
            producer = by_output.get(inp)
            if producer is not None and producer != f.name and producer not in adj[f.name]:
                adj[f.name].add(producer)
                deps.append((f.name, producer, inp))
    deps.sort()

    cycle = _find_cycle(adj)
    if cycle is not None:
        return Schedule({}, deps, [], {}, cycle)

    levels = {}

    def level_of(n):
        if n in levels:
            return levels[n]
        levels[n] = 0 if not adj[n] else 1 + max(level_of(d) for d in sorted(adj[n]))
        return levels[n]

    for f in ios:
        level_of(f.name)
    max_level = max(levels.values()) if levels else 0
    checkpoints = list(range(max_level + 1))

    rewindable = {}
    for lv in checkpoints:
        crossing = set()
        for f in ios:
            if levels[f.name] == lv + 1:
                crossing |= f.inputs
        rewindable[lv] = bool(crossing) and crossing.issubset(retained)
    return Schedule(levels, deps, checkpoints, rewindable, None)
