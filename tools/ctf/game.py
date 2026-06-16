"""Game-theoretic layer over the CTF.

First-blood is a contested resource, so challenge selection is a congestion game. We
analyze the abstracted ONE-SHOT first-pick game: each team simultaneously picks one
challenge; its payoff is `points + (first_blood_bonus if it is the fastest among the
teams that picked the SAME challenge else 0)`, "fastest" = lowest effort/skill, ties by id.

Pure + deterministic (no clock, no RNG; brute-force optimum is bounded: teams ≤ 4,
challenges ≤ ~8).
"""
from __future__ import annotations

import itertools

import team as team_mod


def _solve_time(team_id: str, c: dict, arena: dict) -> float:
    return c["effort"] / team_mod.skill(arena["seed"], team_id, c["category"])


def _fastest_among(team_id: str, c: dict, contender_ids, arena: dict) -> bool:
    """Is `team_id` the fastest solver of `c` among `contender_ids` (ties by lower id)?"""
    st = _solve_time(team_id, c, arena)
    for oid in contender_ids:
        if oid == team_id:
            continue
        ost = _solve_time(oid, c, arena)
        if ost < st or (ost == st and oid < team_id):
            return False
    return True


def is_fastest(team: dict, c: dict, all_teams, arena: dict) -> bool:
    """Fastest among ALL teams (the pessimistic contention `best_response` assumes)."""
    return _fastest_among(team["id"], c, [o["id"] for o in all_teams], arena)


def expected_value(team: dict, c: dict, all_teams, arena: dict) -> int:
    """Contention-adjusted payoff `best_response` maximizes."""
    bonus = arena["first_blood_bonus"] if is_fastest(team, c, all_teams, arena) else 0
    return c["points"] + bonus


def nash_analysis(arena: dict, teams) -> dict:
    """One-shot first-pick congestion game. Returns the best-response profile, whether it
    is a pure Nash equilibrium, per-team regret, social welfare, the social optimum, and
    the price of anarchy. Deterministic."""
    cs = arena["challenges"]
    bonus = arena["first_blood_bonus"]
    ids = sorted(t["id"] for t in teams)
    cbyid = {c["id"]: c for c in cs}

    def br_pick(team_id):
        return sorted(cs, key=lambda c: (-expected_value({"id": team_id}, c, teams, arena),
                                         c["id"]))[0]["id"]

    first = {tid: br_pick(tid) for tid in ids}

    def payoff(team_id, cid, picks):
        c = cbyid[cid]
        contenders = [o for o in ids if picks[o] == cid]
        win = _fastest_among(team_id, c, contenders, arena)
        return c["points"] + (bonus if win else 0)

    regret = {}
    for tid in ids:
        cur = payoff(tid, first[tid], first)
        best = cur
        for c in cs:
            alt = dict(first)
            alt[tid] = c["id"]
            best = max(best, payoff(tid, c["id"], alt))
        regret[tid] = best - cur
    is_nash = all(r <= 0 for r in regret.values())

    social = sum(payoff(tid, first[tid], first) for tid in ids)
    optimum = social
    cids = [c["id"] for c in cs]
    for combo in itertools.product(cids, repeat=len(ids)):
        picks = dict(zip(ids, combo))
        optimum = max(optimum, sum(payoff(tid, picks[tid], picks) for tid in ids))
    poa = round(optimum / social, 4) if social else 1.0

    return {"first_picks": first, "is_nash": is_nash, "regret": regret,
            "social_welfare": social, "optimum": optimum, "price_of_anarchy": poa}
