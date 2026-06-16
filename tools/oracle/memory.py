"""memory.py — the-dossier: simple team memory for the reverser team (slice 4a).

Deterministic, simple, auto-fire-friendly. `remember()` appends facts (cheap sync write);
`recall()` does stdlib keyword/tag scoring; `inject()` renders recalled notes for the next
debate's context. The coordinator auto-fires `remember()` per verdict with deterministic
facts (no LLM). An optional detached LLM distiller is out of 4a scope — only the
deterministic core ships here.
"""
from __future__ import annotations

import json
import os
import re


def _tok(s):
    return set(re.findall(r"[a-z0-9_]+", (s or "").lower()))


class TeamMemory:
    def __init__(self, path):
        self.path = path
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)

    def remember(self, *, run_id, fn, kind, text, tags=(), ts=None):
        entry = {"ts": ts, "run_id": run_id, "fn": fn, "kind": kind,
                 "text": text, "tags": sorted(tags)}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def _all(self):
        if not os.path.exists(self.path):
            return []
        out = []
        for line in open(self.path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue   # skip corrupt/partial lines (interrupted write); append-only, rest intact
        return out

    def recall(self, query, k=5):
        qtok = _tok(query)
        if not qtok:
            return []
        def hits(qtoks, toks):   # query token is a substring of a stored token (decode ⊂ llama_decode)
            return sum(1 for qt in qtoks if any(qt in t for t in toks))
        scored = []
        for e in self._all():
            body = _tok(e.get("text", "")) | _tok(e.get("fn", ""))
            tags = {t.lower() for t in e.get("tags", [])}
            score = hits(qtok, body) + 2 * hits(qtok, tags)   # tag match weighted
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda se: se[0], reverse=True)
        return [e for _, e in scored[:k]]

    def inject(self, fn, query, k=5):
        notes = self.recall(query, k=k)
        if not notes:
            return ""
        lines = ["Prior team knowledge (the-dossier):"]
        lines += [f"- [{n.get('fn', '')}] {n.get('text', '')}" for n in notes]
        return "\n".join(lines)
