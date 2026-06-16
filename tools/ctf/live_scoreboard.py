"""Live scoreboard — a deterministic fold over the submission ledger.

The ledger is the source of truth: folding its `solve` events (in append/seq order) yields
the board. First-blood = the earliest solver of each challenge (gets the bonus). Duplicate
(handle, challenge) solves are ignored. Same ledger → same board (replay-stable)."""
from __future__ import annotations


def fold(entries: list[dict], challenges_by_id: dict, first_blood_bonus: int = 50) -> dict:
    """Fold ledger entries into {scoreboard, ranking}. `entries` are in chain order."""
    board: dict[str, dict] = {}
    first_blooded: set[str] = set()      # challenge ids whose first blood is taken
    seen: set[tuple] = set()             # (handle, challenge) already counted
    for e in entries:
        p = e.get("payload", e)
        if p.get("kind") != "solve":
            continue
        handle, cid = p.get("handle"), p.get("challenge")
        c = challenges_by_id.get(cid)
        if not c or not handle or (handle, cid) in seen:
            continue
        seen.add((handle, cid))
        rec = board.setdefault(handle, {"handle": handle, "points": 0,
                                        "solves": [], "first_bloods": 0})
        pts = c["points"]
        if cid not in first_blooded:
            first_blooded.add(cid)
            pts += first_blood_bonus
            rec["first_bloods"] += 1
        rec["points"] += pts
        rec["solves"].append(cid)
    scoreboard = [{"handle": r["handle"], "points": r["points"],
                   "solves": len(r["solves"]), "first_bloods": r["first_bloods"],
                   "solved": list(r["solves"])} for r in board.values()]
    ranking = [r["handle"] for r in sorted(
        scoreboard, key=lambda r: (-r["points"], -r["first_bloods"], -r["solves"], r["handle"]))]
    scoreboard.sort(key=lambda r: ranking.index(r["handle"]))
    return {"scoreboard": scoreboard, "ranking": ranking}


def already_solved(entries: list[dict], handle: str, cid: str) -> bool:
    """True if this handle already has a recorded solve for this challenge."""
    for e in entries:
        p = e.get("payload", e)
        if p.get("kind") == "solve" and p.get("handle") == handle and p.get("challenge") == cid:
            return True
    return False
