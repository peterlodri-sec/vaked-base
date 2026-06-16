"""CTF arena: the challenge board + config. Deterministic (literal, not generated)."""
from __future__ import annotations


def challenge(cid: str, category: str, points: int, effort: int) -> dict:
    """One challenge. `effort` = sim-minutes to solve at skill 1.0."""
    return {"id": cid, "category": category, "points": int(points), "effort": int(effort)}


def default_arena(seed: int = 1337) -> dict:
    """A fixed 8-challenge board across web/crypto/pwn/rev/misc."""
    challenges = [
        challenge("web-100", "web", 100, 3),
        challenge("web-300", "web", 300, 10),
        challenge("crypto-200", "crypto", 200, 7),
        challenge("crypto-500", "crypto", 500, 18),
        challenge("pwn-250", "pwn", 250, 9),
        challenge("pwn-400", "pwn", 400, 15),
        challenge("rev-150", "rev", 150, 5),
        challenge("misc-350", "misc", 350, 12),
    ]
    return {"challenges": challenges, "time_box_min": 20, "first_blood_bonus": 50,
            "seed": seed, "mode": "jeopardy"}


MODES = ("jeopardy", "koth")


def validate_arena(arena: dict) -> None:
    """Raise ValueError if the arena is structurally invalid."""
    challenges = arena.get("challenges") or []
    if not challenges:
        raise ValueError("arena has no challenges")
    seen = set()
    for c in challenges:
        if c["id"] in seen:
            raise ValueError("duplicate challenge id: %s" % c["id"])
        seen.add(c["id"])
        if c["points"] <= 0 or c["effort"] <= 0:
            raise ValueError("challenge %s: points and effort must be positive" % c["id"])
    if arena.get("time_box_min", 0) <= 0:
        raise ValueError("time_box_min must be positive")
    if arena.get("first_blood_bonus", -1) < 0:
        raise ValueError("first_blood_bonus must be non-negative")
    if arena.get("mode", "jeopardy") not in MODES:
        raise ValueError("unknown mode %r (one of %s)" % (arena.get("mode"), ", ".join(MODES)))
