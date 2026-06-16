#!/usr/bin/env python3
"""Autonomous arena bot — solves the self-contained puzzles and submits flags. Stdlib only.

Demonstrates the arena's bot API: `GET /challenges.json` (flag-free) → decode each puzzle by
category (crypto=ROT13, misc=base64, rev=single-byte-XOR brute) → `POST /submit`. Box-backed
challenges (no artifact) are left to human/HTTP solvers — the bot skips them.

    python3 arena_bot.py --url http://127.0.0.1:8099 --handle autobot
"""
from __future__ import annotations

import argparse
import base64
import codecs
import json
import urllib.parse
import urllib.request


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=6) as r:  # noqa: S310 (loopback/tailnet lab)
        return r.read()


def solve_artifact(category: str, artifact: str | None) -> str | None:
    """Decode a self-contained puzzle artifact to its flag, or None if not solvable."""
    if not artifact:
        return None
    if category == "crypto":                      # Caesar / ROT13
        out = codecs.decode(artifact, "rot13")
    elif category == "misc":                      # base64
        try:
            out = base64.b64decode(artifact).decode()
        except (ValueError, UnicodeDecodeError):
            return None
    elif category == "rev":                       # single-byte XOR — brute all 256 keys
        raw = bytes.fromhex(artifact)
        for k in range(256):
            try:
                cand = bytes(b ^ k for b in raw).decode()
            except UnicodeDecodeError:
                continue
            if cand.startswith("FLAG{") and cand.endswith("}"):
                return cand
        return None
    else:
        return None
    return out if out.startswith("FLAG{") and out.endswith("}") else None


def submit(base: str, handle: str, cid: str, flag: str) -> None:
    data = urllib.parse.urlencode({"handle": handle, "challenge": cid, "flag": flag}).encode()
    urllib.request.urlopen(base + "/submit", data=data, timeout=6).read()  # noqa: S310


def play(base: str, handle: str) -> list[str]:
    """Fetch challenges, solve every self-contained puzzle, submit. Returns solved ids."""
    base = base.rstrip("/")
    solved = []
    for c in json.loads(_get(base + "/challenges.json")):
        flag = solve_artifact(c["category"], c.get("artifact"))
        if flag:
            submit(base, handle, c["id"], flag)
            solved.append(c["id"])
    return solved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="autonomous CTF arena puzzle bot")
    ap.add_argument("--url", default="http://127.0.0.1:8099")
    ap.add_argument("--handle", default="autobot")
    ns = ap.parse_args(argv)
    solved = play(ns.url, ns.handle)
    print("solved %d: %s" % (len(solved), ", ".join(solved) or "(none)"))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
