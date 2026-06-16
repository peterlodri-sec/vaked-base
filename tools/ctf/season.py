"""CTF season: a group stage (round-robin) → single-elimination bracket → season champion.

Composes `tournament.run_tournament`: the group stage ranks the field; the bracket seeds the
top strategies (1v4, 2v3 → final for 4; top-2 final otherwise), each bracket "match" being a
head-to-head sub-tournament whose higher win-rate advances. Pure/deterministic: same
`(strategies, group_seeds, bracket_seeds, box)` → identical season.
"""
from __future__ import annotations

import tournament as tournament_mod


def _match(a: str, b: str, seeds, box_min: int) -> dict:
    """A head-to-head bracket match: a 2-strategy sub-tournament; higher win-rate advances
    (tie → mean_points, then name — the leaderboard's own total order)."""
    board = tournament_mod.run_tournament([a, b], seeds, box_min=box_min)["leaderboard"]
    winner, loser = board[0]["strategy"], board[1]["strategy"]
    return {"a": a, "b": b, "winner": winner, "loser": loser,
            "win_rate": board[0]["win_rate"]}


def run_season(strategy_names, group_seeds, bracket_seeds, box_min: int = 20) -> dict:
    """Group stage + knockout bracket. `strategy_names` = 2–4 distinct competitors."""
    group = tournament_mod.run_tournament(strategy_names, group_seeds, box_min=box_min)
    rank = [r["strategy"] for r in group["leaderboard"]]   # group seeds 1..n by standing
    n = len(rank)
    bracket = {"semifinals": [], "final": None}
    if n >= 4:
        sf1 = _match(rank[0], rank[3], bracket_seeds, box_min)   # 1 v 4
        sf2 = _match(rank[1], rank[2], bracket_seeds, box_min)   # 2 v 3
        bracket["semifinals"] = [sf1, sf2]
        final = _match(sf1["winner"], sf2["winner"], bracket_seeds, box_min)
    else:                                                        # n in {2, 3}: top-2 contest the final
        final = _match(rank[0], rank[1], bracket_seeds, box_min)
    bracket["final"] = final
    return {"group_standings": group["leaderboard"], "bracket": bracket,
            "champion": final["winner"], "runner_up": final["loser"],
            "group_seeds": list(group_seeds), "bracket_seeds": list(bracket_seeds)}
