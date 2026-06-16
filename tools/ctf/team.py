"""CTF teams: deterministic per-category skill + deterministic selection strategies.

A strategy is a pure function `pick(team, remaining, arena, all_teams) -> challenge_id | None`.
All ties break by `id` (lexicographic) so every pick is total-ordered → deterministic.
No `random`; skill is derived via hashlib from (seed, team_id, category).
"""
from __future__ import annotations

import hashlib


def skill(seed, team_id: str, category: str) -> float:
    """Stable per-(team, category) multiplier in [0.5, 1.5). Deterministic, no RNG."""
    h = hashlib.sha256(("%s:%s:%s" % (seed, team_id, category)).encode()).hexdigest()
    return 0.5 + (int(h[:8], 16) % 1000) / 1000.0


def greedy_points(team, remaining, arena, all_teams):
    if not remaining:
        return None
    return min(remaining, key=lambda c: (-c["points"], c["id"]))["id"]


def greedy_easy(team, remaining, arena, all_teams):
    if not remaining:
        return None
    return min(remaining, key=lambda c: (c["effort"], -c["points"], c["id"]))["id"]


def ratio_balanced(team, remaining, arena, all_teams):
    if not remaining:
        return None
    return min(remaining, key=lambda c: (-(c["points"] / c["effort"]), c["id"]))["id"]


def category_focus(cat: str):
    def pick(team, remaining, arena, all_teams):
        if not remaining:
            return None
        pool = [c for c in remaining if c["category"] == cat] or remaining
        return min(pool, key=lambda c: (-c["points"], c["id"]))["id"]
    return pick


def best_response(team, remaining, arena, all_teams):
    """Game-theoretic: maximize contention-adjusted value (points + first-blood bonus IFF
    this team is the fastest solver among all teams for that challenge). Ties by id."""
    import game  # deferred import (game imports team) to avoid an import cycle
    if not remaining:
        return None
    return sorted(remaining,
                  key=lambda c: (-game.expected_value(team, c, all_teams, arena), c["id"]))[0]["id"]


STRATEGIES = {
    "greedy_points": greedy_points,
    "greedy_easy": greedy_easy,
    "ratio_balanced": ratio_balanced,
    "best_response": best_response,
}


def resolve_strategy(name: str):
    """Map a strategy name to its pick fn. `category_focus:<cat>` is parameterized."""
    if name.startswith("category_focus:"):
        return category_focus(name.split(":", 1)[1])
    if name not in STRATEGIES:
        raise ValueError("unknown strategy: %s" % name)
    return STRATEGIES[name]
