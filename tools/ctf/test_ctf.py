#!/usr/bin/env python3
"""CTF simulation tests (stdlib only; run: python3 tools/ctf/test_ctf.py)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import arena as A      # noqa: E402
import team as T       # noqa: E402
import game as G       # noqa: E402
import reward as R     # noqa: E402
import engine as E     # noqa: E402

DEF = ["greedy_points", "greedy_easy", "ratio_balanced", "best_response"]


def _teams(strats):
    return [{"id": "team-%d" % (i + 1), "strategy": s, "pick_fn": T.resolve_strategy(s)}
            for i, s in enumerate(strats)]


# ---- skill ----
def test_skill_deterministic_and_ranged():
    a = T.skill(1337, "team-1", "web")
    assert a == T.skill(1337, "team-1", "web")
    assert 0.5 <= a < 1.5


# ---- strategies ----
def test_strategies_deterministic_and_ordered():
    ar = A.default_arena()
    rem = sorted(ar["challenges"], key=lambda c: c["id"])
    s, tt = {"id": "team-1"}, [{"id": "team-1"}]
    assert T.greedy_points(s, rem, ar, tt) == T.greedy_points(s, rem, ar, tt)
    assert T.greedy_points(s, rem, ar, tt) == "crypto-500"   # highest points (500)
    assert T.greedy_easy(s, rem, ar, tt) == "web-100"        # lowest effort (3)


def test_resolve_strategy_category_focus():
    f = T.resolve_strategy("category_focus:crypto")
    ar = A.default_arena()
    rem = sorted(ar["challenges"], key=lambda c: c["id"])
    assert f({"id": "team-1"}, rem, ar, [{"id": "team-1"}]) == "crypto-500"  # highest-pts crypto


def test_resolve_strategy_unknown_raises():
    try:
        T.resolve_strategy("nope")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---- arena validation ----
def test_validate_arena_rejects_bad():
    bad = [
        {"challenges": [], "time_box_min": 20, "first_blood_bonus": 50, "seed": 1},
        {"challenges": [A.challenge("x", "w", 0, 3)], "time_box_min": 20, "first_blood_bonus": 50, "seed": 1},
        {"challenges": [A.challenge("x", "w", 100, 3), A.challenge("x", "w", 100, 3)],
         "time_box_min": 20, "first_blood_bonus": 50, "seed": 1},
        {"challenges": [A.challenge("x", "w", 100, 3)], "time_box_min": 0, "first_blood_bonus": 50, "seed": 1},
    ]
    for b in bad:
        try:
            A.validate_arena(b)
            assert False, "expected ValueError"
        except ValueError:
            pass
    A.validate_arena(A.default_arena())   # the default is valid


# ---- engine: first-blood + time box ----
def test_first_blood_credited_once():
    res = E.run_ctf(A.default_arena(), _teams(DEF))
    fb = [e["payload"]["challenge"] for e in res["timeline"]
          if e["payload"].get("kind") == "solve" and e["payload"]["first_blood"]]
    assert len(fb) == len(set(fb))                                   # at most once per challenge
    assert sum(r["first_bloods"] for r in res["scoreboard"]) == len(set(fb))


def test_time_box_enforced():
    res = E.run_ctf(A.default_arena(), _teams(DEF))
    ticks = [e["payload"]["tick"] for e in res["timeline"] if e["payload"].get("kind") == "solve"]
    assert all(1 <= t <= 20 for t in ticks)
    small = E.run_ctf(dict(A.default_arena(), time_box_min=1), _teams(DEF))
    big = E.run_ctf(dict(A.default_arena(), time_box_min=20), _teams(DEF))
    n_small = sum(r["solves"] for r in small["scoreboard"])
    n_big = sum(r["solves"] for r in big["scoreboard"])
    assert n_small < n_big                                           # the box bounds solves


def test_ranking_tiebreak_by_id():
    ar = {"challenges": [A.challenge("z", "web", 100, 9999)],
          "time_box_min": 2, "first_blood_bonus": 50, "seed": 1}
    res = E.run_ctf(ar, _teams(["greedy_points", "greedy_points"]))
    assert all(r["points"] == 0 for r in res["scoreboard"])          # nobody can solve
    assert res["ranking"] == ["team-1", "team-2"]                    # tie → id ascending


# ---- replay-stability ----
def test_replay_stable_scoreboard_and_hash():
    r1 = E.run_ctf(A.default_arena(), _teams(DEF))
    r2 = E.run_ctf(A.default_arena(), _teams(DEF))
    assert r1["scoreboard"] == r2["scoreboard"]
    assert r1["chain_hash"] == r2["chain_hash"]
    assert r1["chain_ok"] and r2["chain_ok"]


def test_two_three_four_team_runs():
    for n in (2, 3, 4):
        res = E.run_ctf(A.default_arena(), _teams(DEF[:n]))
        assert len(res["scoreboard"]) == n and len(res["ranking"]) == n and res["chain_ok"]


def test_replay_recompute_matches_final():
    import ralphcore
    p = tempfile.mktemp(suffix=".jsonl")
    E.run_ctf(A.default_arena(), _teams(DEF), ledger_path=p)
    entries = [json.loads(line) for line in open(p) if line.strip()]
    assert ralphcore.verify_chain(entries)
    final = next(e["payload"] for e in entries if e["payload"].get("kind") == "final")
    pts = {}
    for e in entries:
        q = e["payload"]
        if q.get("kind") == "solve":
            pts[q["team"]] = pts.get(q["team"], 0) + q["awarded"]
    for r in final["scoreboard"]:
        assert pts.get(r["team"], 0) == r["points"]
    os.remove(p)


# ---- game theory ----
def test_best_response_deterministic():
    ar = A.default_arena()
    rem = sorted(ar["challenges"], key=lambda c: c["id"])
    tt = [{"id": "team-1"}, {"id": "team-2"}]
    assert T.best_response({"id": "team-1"}, rem, ar, tt) == T.best_response({"id": "team-1"}, rem, ar, tt)


def test_nash_deterministic_and_poa_ge_one():
    ar = A.default_arena()
    ts = [{"id": "team-%d" % i} for i in range(1, 5)]
    n = G.nash_analysis(ar, ts)
    assert n == G.nash_analysis(ar, ts)
    assert n["price_of_anarchy"] >= 1.0
    assert set(n["first_picks"].keys()) == {"team-1", "team-2", "team-3", "team-4"}


def test_nash_equilibrium_and_deviation_controlled():
    orig = T.skill
    try:
        # Case 1 — equilibrium: each team fastest on a different challenge → uncontested.
        T.skill = lambda seed, tid, cat: {("team-1", "x"): 1.4, ("team-2", "x"): 0.6,
                                          ("team-1", "y"): 0.6, ("team-2", "y"): 1.4}[(tid, cat)]
        ar = {"challenges": [A.challenge("a", "x", 100, 5), A.challenge("b", "y", 100, 5)],
              "time_box_min": 20, "first_blood_bonus": 50, "seed": 1}
        ts = [{"id": "team-1"}, {"id": "team-2"}]
        n = G.nash_analysis(ar, ts)
        assert n["first_picks"] == {"team-1": "a", "team-2": "b"}
        assert n["is_nash"] is True and all(r <= 0 for r in n["regret"].values())

        # Case 2 — profitable deviation: team-1 fastest on BOTH, equal points, large bonus →
        # both best-respond to 'a' (tie→id), but team-2 should deviate to the uncontested 'b'.
        T.skill = lambda seed, tid, cat: 1.4 if tid == "team-1" else 0.6
        ar2 = {"challenges": [A.challenge("a", "x", 100, 5), A.challenge("b", "y", 100, 5)],
               "time_box_min": 20, "first_blood_bonus": 1000, "seed": 1}
        n2 = G.nash_analysis(ar2, ts)
        assert n2["first_picks"] == {"team-1": "a", "team-2": "a"}
        assert n2["is_nash"] is False
        assert n2["regret"]["team-2"] > 0
    finally:
        T.skill = orig


# ---- reward (non-currency trophy) ----
def test_champion_is_rank1_and_codename_replay_stable():
    res = E.run_ctf(A.default_arena(), _teams(DEF))
    assert res["trophy"]["champion"] == res["ranking"][0]
    assert res["trophy"]["codename"] in R.CODENAMES
    res2 = E.run_ctf(A.default_arena(), _teams(DEF))
    assert res["trophy"]["codename"] == res2["trophy"]["codename"]          # replay-stable
    assert R.codename_for(res["trophy"]["bound_to"]) == res["trophy"]["codename"]  # re-derivable


def test_codename_bound_to_hash():
    assert R.codename_for("0" * 64) == R.CODENAMES[0]
    assert R.codename_for("%064x" % 5) == R.CODENAMES[5]


def test_trophy_is_chained_and_verifies():
    res = E.run_ctf(A.default_arena(), _teams(DEF))
    assert res["timeline"][-1]["payload"]["kind"] == "trophy"
    assert res["chain_ok"] is True


# ---- box-aware best-response (v0.1) ----
def test_box_aware_deterministic():
    ar = A.default_arena()
    rem = sorted(ar["challenges"], key=lambda c: c["id"])
    tt = [{"id": "team-1"}, {"id": "team-2"}]
    ctx = {"tick": 1, "box_min": 20}
    assert T.box_aware_response({"id": "team-1"}, rem, ar, tt, ctx) == \
        T.box_aware_response({"id": "team-1"}, rem, ar, tt, ctx)


def test_box_aware_respects_feasibility():
    # one cheap finishable challenge + one rich UNfinishable one; little time left → pick the cheap.
    ar = {"challenges": [A.challenge("cheap", "web", 100, 2), A.challenge("rich", "crypto", 999, 50)],
          "time_box_min": 20, "first_blood_bonus": 50, "seed": 1}
    tt = [{"id": "team-1"}]
    ctx = {"tick": 18, "box_min": 20}      # 3 ticks left → 'rich' (effort 50) cannot finish
    assert T.box_aware_response({"id": "team-1"}, ar["challenges"], ar, tt, ctx) == "cheap"
    # box-blind best_response chases the rich one regardless
    assert T.best_response({"id": "team-1"}, ar["challenges"], ar, tt, ctx) == "rich"


def test_box_aware_beats_box_blind_head_to_head():
    # team-4 was 0 with box-blind best_response; box_aware lets it bank finishable points.
    blind = E.run_ctf(A.default_arena(), _teams(["greedy_points", "greedy_easy", "ratio_balanced", "best_response"]))
    aware = E.run_ctf(A.default_arena(), _teams(["greedy_points", "greedy_easy", "ratio_balanced", "box_aware_response"]))
    blind_t4 = next(r for r in blind["scoreboard"] if r["team"] == "team-4")["points"]
    aware_t4 = next(r for r in aware["scoreboard"] if r["team"] == "team-4")["points"]
    assert blind_t4 == 0 and aware_t4 > 0 and aware_t4 >= blind_t4
    assert aware["chain_ok"]


def test_box_aware_run_replay_stable():
    strategies = ["greedy_points", "greedy_easy", "ratio_balanced", "box_aware_response"]
    r1 = E.run_ctf(A.default_arena(), _teams(strategies))
    r2 = E.run_ctf(A.default_arena(), _teams(strategies))
    assert r1["scoreboard"] == r2["scoreboard"] and r1["chain_hash"] == r2["chain_hash"]


if __name__ == "__main__":
    tests = sorted((n, f) for n, f in dict(globals()).items()
                   if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS  %s" % name)
            passed += 1
        except Exception as e:  # noqa: BLE001
            print("FAIL  %s: %s: %s" % (name, type(e).__name__, e))
            failed += 1
    print("\n%d passed, %d failed" % (passed, failed))
    raise SystemExit(1 if failed else 0)
