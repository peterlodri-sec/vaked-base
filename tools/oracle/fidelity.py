"""Decompilation fidelity: normalized-token similarity vs ground-truth source.

Slice 1 method only. Token set = C identifiers/keywords/operators after stripping
comments and collapsing whitespace. Score = Jaccard over token multisets (Dice).
A later cycle replaces this with a tree-sitter AST diff.
"""
from __future__ import annotations

import re
from collections import Counter

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
_TOKEN = re.compile(r"[A-Za-z_]\w*|[^\sA-Za-z_]")


def _tokens(code: str) -> Counter:
    code = _COMMENT.sub(" ", code)
    return Counter(_TOKEN.findall(code))


def score(a: str, b: str) -> float:
    """Dice coefficient over token multisets; 0.0 if either side is empty."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = sum((ta & tb).values())
    return round(2 * inter / (sum(ta.values()) + sum(tb.values())), 4)
