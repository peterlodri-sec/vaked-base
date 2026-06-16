"""CTF teams: deterministic per-category skill + deterministic selection strategies.

A strategy is a pure function `pick(team, remaining, arena, all_teams, ctx=None) -> id | None`,
where `ctx` (optional) carries clock context `{tick, box_min}` so a strategy can reason about
the remaining time box. All ties break by `id` (lexicographic) → every pick is total-ordered,
deterministic. No `random`; skill is hashlib-derived from (seed, team_id, category).
"""
from __future__ import annotations

import hashlib


def skill(seed, team_id: str, category: str) -> float:
    """Stable per-(team, category) multiplier in [0.5, 1.5). Deterministic, no RNG."""
    h = hashlib.sha256(("%s:%s:%s" % (seed, team_id, category)).encode()).hexdigest()
    return 0.5 + (int(h[:8], 16) % 1000) / 1000.0


def greedy_points(team, remaining, arena, all_teams, ctx=None):
    if not remaining:
        return None
    return min(remaining, key=lambda c: (-c["points"], c["id"]))["id"]


def greedy_easy(team, remaining, arena, all_teams, ctx=None):
    if not remaining:
        return None
    return min(remaining, key=lambda c: (c["effort"], -c["points"], c["id"]))["id"]


def ratio_balanced(team, remaining, arena, all_teams, ctx=None):
    if not remaining:
        return None
    return min(remaining, key=lambda c: (-(c["points"] / c["effort"]), c["id"]))["id"]


def category_focus(cat: str):
    def pick(team, remaining, arena, all_teams, ctx=None):
        if not remaining:
            return None
        pool = [c for c in remaining if c["category"] == cat] or remaining
        return min(pool, key=lambda c: (-c["points"], c["id"]))["id"]
    return pick


def best_response(team, remaining, arena, all_teams, ctx=None):
    """Game-theoretic: maximize contention-adjusted value (points + first-blood bonus IFF this
    team is the fastest solver among all teams for that challenge). Box-blind — may chase a
    high-value target it cannot finish in time. Ties by id."""
    import game  # deferred import (game imports team) to avoid an import cycle
    if not remaining:
        return None
    return sorted(remaining,
                  key=lambda c: (-game.expected_value(team, c, all_teams, arena), c["id"]))[0]["id"]


def box_aware_response(team, remaining, arena, all_teams, ctx=None):
    """Box-aware best-response: only commit to challenges finishable in the remaining box, then
    maximize contention-adjusted value (ties by id). A challenge needs ceil(effort/skill) ticks;
    since `remaining_ticks` is integer, feasibility is exactly `effort/skill <= remaining_ticks`.
    With no clock `ctx`, degrades to `best_response` (full box assumed)."""
    import game
    if not remaining:
        return None
    pool = remaining
    if ctx:
        remaining_ticks = ctx["box_min"] - ctx["tick"] + 1
        feasible = [c for c in remaining
                    if c["effort"] / skill(arena["seed"], team["id"], c["category"]) <= remaining_ticks]
        pool = feasible or remaining   # nothing fits → fall back (will go idle / partial)
    return sorted(pool,
                  key=lambda c: (-game.expected_value(team, c, all_teams, arena), c["id"]))[0]["id"]


STRATEGIES = {
    "greedy_points": greedy_points,
    "greedy_easy": greedy_easy,
    "ratio_balanced": ratio_balanced,
    "best_response": best_response,
    "box_aware_response": box_aware_response,
}


def resolve_strategy(name: str):
    """Map a strategy name to its pick fn. `category_focus:<cat>` is parameterized."""
    if name.startswith("category_focus:"):
        return category_focus(name.split(":", 1)[1])
    if name not in STRATEGIES:
        raise ValueError("unknown strategy: %s" % name)
    return STRATEGIES[name]
