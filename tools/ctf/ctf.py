#!/usr/bin/env python3
"""CTF simulation CLI.

  ctf run   [--teams N] [--seed S] [--box-min M] [--strategies a,b,c,d] [--json] [--out PATH]
  ctf replay --events PATH
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import arena as arena_mod  # noqa: E402
import engine  # noqa: E402
import reward  # noqa: E402
import team as team_mod  # noqa: E402
from ledger import GENESIS_HASH  # noqa: E402
import ralphcore  # noqa: E402  (path inserted by ledger import)

DEFAULT_STRATEGIES = ["greedy_points", "greedy_easy", "ratio_balanced", "best_response"]


def build_teams(n: int, strategies: list[str]) -> list[dict]:
    teams = []
    for i in range(n):
        name = strategies[i % len(strategies)]
        teams.append({"id": "team-%d" % (i + 1), "strategy": name,
                      "pick_fn": team_mod.resolve_strategy(name)})
    return teams


def cmd_run(ns: argparse.Namespace) -> int:
    ar = arena_mod.default_arena(seed=ns.seed)
    ar["time_box_min"] = ns.box_min
    strategies = [s for s in ns.strategies.split(",") if s] if ns.strategies else DEFAULT_STRATEGIES
    if not strategies:
        print("ctf: --strategies had no usable names"); return 2
    teams = build_teams(ns.teams, strategies)
    res = engine.run_ctf(ar, teams, ledger_path=ns.out)
    if ns.json:
        view = {k: res[k] for k in ("scoreboard", "ranking", "nash", "trophy", "chain_ok", "chain_hash")}
        print(json.dumps(view, indent=2, sort_keys=True))
        return 0
    print("=== CTF scoreboard (seed=%d, box=%dmin, %d teams) ===" % (ns.seed, ns.box_min, ns.teams))
    sb = {r["team"]: r for r in res["scoreboard"]}
    for rank, tid in enumerate(res["ranking"], 1):
        r = sb[tid]
        print("  %d. %-8s %-18s %4d pts  %d solves  %d first-blood"
              % (rank, tid, r["strategy"], r["points"], r["solves"], r["first_bloods"]))
    n = res["nash"]
    print("game theory: nash_equilibrium=%s  price_of_anarchy=%s  welfare=%d (optimum %d)"
          % (n["is_nash"], n["price_of_anarchy"], n["social_welfare"], n["optimum"]))
    t = res["trophy"]
    print('reward: %s -> codename "%s" (non-currency; bound to %s)'
          % (t["champion"], t["codename"], t["bound_to"][:16]))
    print("chain_ok=%s  chain_hash=%s" % (res["chain_ok"], res["chain_hash"][:16]))
    return 0


def cmd_replay(ns: argparse.Namespace) -> int:
    entries = [json.loads(line) for line in open(ns.events, encoding="utf-8") if line.strip()]
    if not ralphcore.verify_chain(entries):
        print("REPLAY FAIL: chain does not verify")
        return 1
    pts: dict[str, int] = {}
    solves: dict[str, int] = {}
    fbs: dict[str, int] = {}
    recorded_final = None
    trophy = None
    for e in entries:
        p = e["payload"]
        k = p.get("kind")
        if k == "solve":
            tid = p["team"]
            pts[tid] = pts.get(tid, 0) + p["awarded"]
            solves[tid] = solves.get(tid, 0) + 1
            fbs[tid] = fbs.get(tid, 0) + (1 if p["first_blood"] else 0)
        elif k == "final":
            recorded_final = p
        elif k == "trophy":
            trophy = p
    if recorded_final is None:
        print("REPLAY FAIL: no final entry")
        return 1
    for r in recorded_final["scoreboard"]:
        tid = r["team"]
        if (pts.get(tid, 0), solves.get(tid, 0), fbs.get(tid, 0)) != (r["points"], r["solves"], r["first_bloods"]):
            print("REPLAY FAIL: recomputed scoreboard for %s != recorded" % tid)
            return 1
    if trophy is not None:
        if reward.codename_for(trophy["bound_to"]) != trophy["codename"]:
            print("REPLAY FAIL: codename does not re-derive from bound hash")
            return 1
        print('REPLAY OK: %d events verified; champion %s codename "%s" confirmed'
              % (len(entries), trophy["champion"], trophy["codename"]))
    else:
        print("REPLAY OK: %d events verified; scoreboard recomputed" % len(entries))
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(prog="ctf")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a time-boxed CTF simulation")
    r.add_argument("--teams", type=int, default=4)
    r.add_argument("--seed", type=int, default=1337)
    r.add_argument("--box-min", dest="box_min", type=int, default=20)
    r.add_argument("--strategies", default=None, help="comma list; default cycles 4 strategies")
    r.add_argument("--json", action="store_true")
    r.add_argument("--out", default=None, help="persist the timeline JSONL here")
    rp = sub.add_parser("replay", help="verify + recompute a persisted timeline")
    rp.add_argument("--events", required=True)
    return p.parse_args(argv)


def main(argv) -> int:
    ns = parse_args(argv)
    if ns.cmd == "run":
        return cmd_run(ns)
    if ns.cmd == "replay":
        return cmd_replay(ns)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
