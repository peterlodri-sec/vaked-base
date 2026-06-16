"""CTF strategy tournament: a deterministic round-robin sweep → a strategy leaderboard.

Per-team `skill` depends on the team slot (id), so a single match is slot-biased. We
neutralize that by playing every seed under all `n` cyclic slot-rotations (each strategy
occupies each slot once per seed), then aggregate win-rate + mean points + first-bloods.
Pure/deterministic: same `(strategies, seeds, box)` → identical leaderboard.
"""
from __future__ import annotations

import arena as arena_mod
import engine
import team as team_mod


def run_tournament(strategy_names, seeds, box_min: int = 20) -> dict:
    """`strategy_names` = the distinct competitors (2–4); `seeds` = iterable of ints.
    Returns {leaderboard, seeds, rotations, matches_per_strategy}."""
    names = list(strategy_names)
    seeds = list(seeds)
    n = len(names)
    if not (2 <= n <= 4):
        raise ValueError("a CTF match seats 2–4 teams; got %d strategies" % n)
    if len(set(names)) != n:
        raise ValueError("tournament strategies must be distinct (leaderboard is keyed by name)")

    stats = {s: {"wins": 0, "podium": 0, "matches": 0, "points": 0, "first_bloods": 0} for s in names}
    podium_cut = max(1, n // 2)

    for seed in seeds:
        for rot in range(n):                                   # cyclic slot rotation
            order = [names[(i + rot) % n] for i in range(n)]
            teams = [{"id": "team-%d" % (i + 1), "strategy": order[i],
                      "pick_fn": team_mod.resolve_strategy(order[i])} for i in range(n)]
            ar = arena_mod.default_arena(seed=seed)
            ar["time_box_min"] = box_min
            res = engine.run_ctf(ar, teams)
            podium_ids = set(res["ranking"][:podium_cut])
            winner = res["ranking"][0]
            sb = {r["team"]: r for r in res["scoreboard"]}
            for t in teams:
                r = sb[t["id"]]
                st = stats[t["strategy"]]
                st["matches"] += 1
                st["points"] += r["points"]
                st["first_bloods"] += r["first_bloods"]
                if t["id"] == winner:
                    st["wins"] += 1
                if t["id"] in podium_ids:
                    st["podium"] += 1

    board = []
    for s in names:
        st = stats[s]
        m = st["matches"] or 1
        board.append({"strategy": s, "wins": st["wins"], "podium": st["podium"],
                      "matches": st["matches"], "win_rate": round(st["wins"] / m, 4),
                      "mean_points": round(st["points"] / m, 2),
                      "mean_first_bloods": round(st["first_bloods"] / m, 4)})
    board.sort(key=lambda r: (-r["win_rate"], -r["mean_points"], r["strategy"]))
    return {"leaderboard": board, "seeds": seeds, "rotations": n,
            "matches_per_strategy": board[0]["matches"] if board else 0}
