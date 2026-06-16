# tools/ctf — deterministic time-boxed CTF simulation

2–4 teams race to solve scored challenges within a 20 simulated-minute box. Pure stdlib,
seeded, **replay-stable** (same seed+config → identical scoreboard + ledger chain hash),
game-theoretic (Nash / price-of-anarchy), with a **non-currency** codename-trophy reward.

```bash
python3 tools/ctf/ctf.py run                      # default: 4 teams, seed 1337, 20-min box (jeopardy)
python3 tools/ctf/ctf.py run --mode koth          # king-of-the-hill: hold-and-steal, per-tick income
python3 tools/ctf/ctf.py run --teams 2 --seed 7   # 2 teams
python3 tools/ctf/ctf.py run --json --out t.jsonl # machine-readable + persist the timeline
python3 tools/ctf/ctf.py replay --events t.jsonl  # verify the chain + recompute the scoreboard
python3 tools/ctf/ctf.py tournament --seeds 20    # round-robin sweep → strategy leaderboard
python3 tools/ctf/ctf.py season                   # group stage → knockout bracket → champion
python3 tools/ctf/test_ctf.py                     # 34 stdlib tests
```

| File | Role |
|------|------|
| `arena.py` | challenge board + config + `mode` (`jeopardy`/`koth`) (`default_arena`, `validate_arena`) |
| `team.py` | deterministic skill + selection strategies (incl. `best_response`, `box_aware_response`) |
| `game.py` | congestion-game analysis: `expected_value`, `nash_analysis` (Nash/regret/PoA) |
| `engine.py` | `run_ctf` (jeopardy) + `_run_koth` (king-of-the-hill) — time-boxed tick loops → scoreboard + game analysis + trophy |
| `reward.py` | the non-currency winner reward (codename + chained trophy attestation) |
| `tournament.py` | deterministic round-robin sweep (seeds × slot-rotations) → strategy leaderboard |
| `season.py` | group stage → single-elimination bracket → season champion |
| `ledger.py` | hash-chained event timeline (reuses `tools/ralph/ralphcore`) |
| `ctf.py` | CLI (`run` / `replay` / `tournament` / `season`) |

Design: `docs/superpowers/specs/2026-06-16-ctf-simulation-design.md` · overview: `docs/ctf/v0.md`.
Determinism: no wall-clock, no unseeded RNG; the "20 minutes" is the simulated box, not wall-time.
