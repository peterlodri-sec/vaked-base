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
python3 tools/ctf/test_ctf.py                     # 36 stdlib tests
```

### Web UI (tailnet-only)

```bash
python3 tools/ctf/web.py                          # binds 127.0.0.1:8088 (safe default)
python3 tools/ctf/web.py --tailnet                # binds the host's tailnet (100.x) IP
python3 tools/ctf/web.py --host 100.105.72.88     # bind an explicit tailnet IP
python3 tools/ctf/test_web.py                     # 11 stdlib tests
```

Server-rendered (no JS framework). `GET /` is a run-form that renders the deterministic
result: scoreboard, ranking, trophy, and the event feed (first-bloods / captures). Pick
`board=vuln` to run against the real [`vulnbox/`](vulnbox/) targets. **Not public-facing:**
`validate_bind_host` refuses `0.0.0.0` and any public/LAN address — only loopback or the
Tailscale CGNAT range `100.64.0.0/10` may bind.

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
| `web.py` | tailnet-only server-rendered web UI (`validate_bind_host` gates the bind to loopback/100.64.0.0/10) |

Design: `docs/superpowers/specs/2026-06-16-ctf-simulation-design.md` · overview: `docs/ctf/v0.md`.
Determinism: no wall-clock, no unseeded RNG; the "20 minutes" is the simulated box, not wall-time.
