# tools/ctf — a self-hostable CTF sim + game

A small, **open-source, self-hostable CTF project** in pure Python standard library — no
dependencies, no database, no build step, MIT-licensed (repo root [`LICENSE`](../../LICENSE)):

- a **deterministic simulation** — strategy bots race scored challenges in a time box;
- **real vulnerable boxes** ([`vulnbox/`](vulnbox/)) — intentionally-vulnerable, contained,
  loopback-only practice targets;
- a tailnet-only **web UI** (watch the sim) and a **live playable arena** (humans/bots solve
  + submit flags, hash-chained scoreboard).

The simulation half: 2–4 teams race to solve scored challenges within a 20 simulated-minute
box. Seeded, **replay-stable** (same seed+config → identical scoreboard + ledger chain hash),
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

### Live playable arena (self-hostable, open-source)

A standalone, **self-hostable CTF game** — humans or bots on your tailnet pick a handle,
solve the challenges (two are the *real* vulnbox targets, three are self-contained puzzles),
and submit flags. Correct flags are scored (first-blood bonus, deduped) and appended to a
**hash-chained submission ledger**; the live scoreboard is a deterministic fold over it.

```bash
python3 tools/ctf/ctf.py arena --with-boxes               # → http://127.0.0.1:8099 (loopback)
python3 tools/ctf/ctf.py arena --with-boxes --tailnet     # bind this host's tailnet (100.x) IP
python3 tools/ctf/ctf.py arena --with-boxes --tailnet --ledger /var/lib/ctf/sub.jsonl  # persist + replay
python3 tools/ctf/test_live.py                            # 15 stdlib tests (incl. full real-box loop)
```

Pure stdlib, no deps, no build, MIT-licensed. Routes: `GET /` · `POST /submit` ·
`GET /scoreboard.json` (bot API) · `GET /healthz`. Same tailnet-only bind guard as the web
UI. **Full self-host guide:** [`docs/ctf/self-host.md`](../../docs/ctf/self-host.md)
(quickstart, systemd unit, persistence, adding challenges).

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
| `live_challenges.py` | live-arena challenge catalog (flags + derived puzzle artifacts + box bindings) |
| `live_scoreboard.py` | deterministic, replay-stable fold of the submission ledger → ranked board |
| `live_server.py` | the live playable arena server (submit + scoreboard + box launch; tailnet-only) |
| `ctf-arena.service` | hardened systemd unit for self-hosting the arena |

Design: `docs/superpowers/specs/2026-06-16-ctf-simulation-design.md` · overview: `docs/ctf/v0.md`.
Determinism: no wall-clock, no unseeded RNG; the "20 minutes" is the simulated box, not wall-time.
