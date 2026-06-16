"""The CTF stepper: a deterministic, time-boxed tick loop over the arena.

run_ctf(arena, teams) → a ranked scoreboard + game-theoretic analysis + a non-currency
champion trophy + the hash-chained timeline. Deterministic: same (seed, arena, teams) →
identical scoreboard AND identical chain hash (replay-stable).
"""
from __future__ import annotations

import arena as arena_mod
import game
import reward
import team as team_mod
from ledger import Ledger


def run_ctf(arena: dict, teams: list[dict], ledger_path: str | None = None) -> dict:
    """`teams` = [{id, strategy (name), pick_fn (callable)}]. Pure given the inputs."""
    arena_mod.validate_arena(arena)
    if arena.get("mode", "jeopardy") == "koth":
        return _run_koth(arena, teams, ledger_path)
    seed, box, bonus = arena["seed"], arena["time_box_min"], arena["first_blood_bonus"]
    by_id = {c["id"]: c for c in arena["challenges"]}
    lg = Ledger(ledger_path)

    state = {}
    for t in teams:
        state[t["id"]] = {"id": t["id"], "strategy": t["strategy"], "pick_fn": t["pick_fn"],
                          "points": 0, "solves": [], "first_bloods": 0,
                          "current": None, "accrued": 0.0}
    order = sorted(state.keys())                     # deterministic team order
    teams_for_game = [{"id": tid} for tid in order]  # game/skill need only ids
    solved_global: dict[str, str] = {}               # challenge id → first solver

    for tick in range(1, box + 1):
        for tid in order:
            s = state[tid]
            if s["current"] is None:
                done = set(s["solves"])
                remaining = sorted((c for c in arena["challenges"] if c["id"] not in done),
                                   key=lambda c: c["id"])
                cid = s["pick_fn"](s, remaining, arena, teams_for_game,
                                   {"tick": tick, "box_min": box})
                if cid is None:
                    continue                          # nothing left for this team
                s["current"], s["accrued"] = cid, 0.0
            c = by_id[s["current"]]
            s["accrued"] += team_mod.skill(seed, tid, c["category"])
            if s["accrued"] >= c["effort"]:
                fb = c["id"] not in solved_global
                awarded = c["points"] + (bonus if fb else 0)
                s["points"] += awarded
                s["solves"].append(c["id"])
                if fb:
                    solved_global[c["id"]] = tid
                    s["first_bloods"] += 1
                lg.append({"kind": "solve", "tick": tick, "team": tid, "challenge": c["id"],
                           "points": c["points"], "first_blood": fb, "awarded": awarded})
                s["current"], s["accrued"] = None, 0.0

    scoreboard = [{"team": state[tid]["id"], "strategy": state[tid]["strategy"],
                   "points": state[tid]["points"], "solves": len(state[tid]["solves"]),
                   "first_bloods": state[tid]["first_bloods"]} for tid in order]
    ranking = [r["team"] for r in sorted(
        scoreboard, key=lambda r: (-r["points"], -r["solves"], -r["first_bloods"], r["team"]))]
    lg.append({"kind": "final", "scoreboard": scoreboard, "ranking": ranking})

    nash = game.nash_analysis(arena, teams_for_game)
    lg.append({"kind": "nash", **nash})

    champion = ranking[0]
    trophy = reward.mint_trophy(champion, lg.head(), nash["social_welfare"])
    lg.append(trophy)

    return {"scoreboard": scoreboard, "ranking": ranking, "nash": nash, "trophy": trophy,
            "timeline": lg.entries(), "chain_ok": lg.verify(), "chain_hash": lg.head(),
            "mode": "jeopardy"}


def _run_koth(arena: dict, teams: list[dict], ledger_path: str | None) -> dict:
    """King-of-the-hill: solving a challenge makes you its HOLDER; each subsequent tick the
    holder earns the challenge's `points`; a rival can re-solve to STEAL the hold. Score
    accrues over time → a contested, time-dynamic game. Deterministic (same inputs → same
    scoreboard + chain hash). Strategies/skill/ledger are reused unchanged."""
    seed, box = arena["seed"], arena["time_box_min"]
    by_id = {c["id"]: c for c in arena["challenges"]}
    lg = Ledger(ledger_path)
    state = {}
    for t in teams:
        state[t["id"]] = {"id": t["id"], "strategy": t["strategy"], "pick_fn": t["pick_fn"],
                          "points": 0, "captures": 0, "current": None, "accrued": 0.0}
    order = sorted(state.keys())
    teams_for_game = [{"id": tid} for tid in order]
    holder = {c["id"]: None for c in arena["challenges"]}   # challenge id → holding team id

    for tick in range(1, box + 1):
        # 1) hold income: each held challenge pays its holder (holdings from prior ticks).
        for cid in sorted(holder):
            if holder[cid] is not None:
                state[holder[cid]]["points"] += by_id[cid]["points"]
        # 2) work: each team attacks a challenge it does NOT currently hold (unheld or a rival's).
        for tid in order:
            s = state[tid]
            if s["current"] is None:
                pool = sorted((c for c in arena["challenges"] if holder[c["id"]] != tid),
                              key=lambda c: c["id"])
                cid = s["pick_fn"](s, pool, arena, teams_for_game, {"tick": tick, "box_min": box})
                if cid is None:
                    continue
                s["current"], s["accrued"] = cid, 0.0
            c = by_id[s["current"]]
            s["accrued"] += team_mod.skill(seed, tid, c["category"])
            if s["accrued"] >= c["effort"]:
                prev = holder[c["id"]]
                if prev != tid:
                    holder[c["id"]] = tid
                    s["captures"] += 1
                    lg.append({"kind": "capture", "tick": tick, "team": tid,
                               "challenge": c["id"], "stolen_from": prev})
                s["current"], s["accrued"] = None, 0.0

    scoreboard = [{"team": state[tid]["id"], "strategy": state[tid]["strategy"],
                   "points": state[tid]["points"], "captures": state[tid]["captures"]} for tid in order]
    ranking = [r["team"] for r in sorted(
        scoreboard, key=lambda r: (-r["points"], -r["captures"], r["team"]))]
    lg.append({"kind": "final", "mode": "koth", "scoreboard": scoreboard, "ranking": ranking})
    nash = game.nash_analysis(arena, teams_for_game)
    lg.append({"kind": "nash", **nash})
    champion = ranking[0]
    trophy = reward.mint_trophy(champion, lg.head(), nash["social_welfare"])
    lg.append(trophy)
    return {"scoreboard": scoreboard, "ranking": ranking, "nash": nash, "trophy": trophy,
            "timeline": lg.entries(), "chain_ok": lg.verify(), "chain_hash": lg.head(),
            "mode": "koth"}
