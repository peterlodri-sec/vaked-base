# Time-boxed CTF simulation (design)

**Date:** 2026-06-16
**Status:** approved (brainstorm, E2E-authorized) — ready for plan
**Base:** `origin/main` @ `cbe27b5`

## One-liner

A deterministic, seeded, **replay-stable** capture-the-flag simulation in `tools/ctf/`
(pure stdlib): **2–4 teams** race to solve scored challenges within a **20 simulated-minute**
time box. Emits a ranked scoreboard + a hash-chained event timeline; the same `(seed, arena,
teams)` always produces the **identical** scoreboard and ledger chain hash.

## Determinism contract (the core property)

- **No wall-clock, no unseeded randomness.** Time is discrete **sim-minute ticks** (the engine,
  not the OS clock). Per-team/per-category *skill* is derived deterministically via `hashlib`
  from `(seed, team_id, category)` — not `random` — so it is stable across runs and machines.
- The ledger reuses `ralphcore.make_entry` (timestamp-free: `hash = chain_hash(prev, payload)`),
  so a run's **final chain hash is a pure function of its event payloads + order**.
- **Replay-stability:** two runs with the same `(seed, arena, teams)` → byte-identical scoreboard
  **and** identical ledger chain hash. This is the headline verifiable property (the dual of the
  oracle/kernel replay proofs).

## The 20-minute box

"Max running time 20m" = the **simulated** CTF duration, enforced **in-engine** as `time_box_min`
(default 20). The simulation itself executes in milliseconds; the box bounds *sim-time*, not
wall-time. No solve may be credited at a tick `> time_box_min`.

## Components / files (`tools/ctf/`, pure stdlib)

### `arena.py` — the board
- `Challenge` (dict): `{id, category, points:int, effort:int}` — `effort` = sim-minutes to solve
  at skill `1.0`.
- `Arena` (dict): `{challenges:[Challenge], time_box_min:int=20, first_blood_bonus:int=50,
  seed:int}`.
- `default_arena(seed=1337)` — a fixed 8-challenge board across `web/crypto/pwn/rev/misc`, varied
  points (100–500) and effort (3–18). Deterministic (literal, not generated).
- `validate_arena(arena)` — ids unique, points/effort positive, ≥1 challenge (raise `ValueError`).

### `team.py` — deterministic competitors
- `skill(seed, team_id, category) -> float` — `0.5 + (int(sha256(f"{seed}:{team_id}:{category}")
  [:8],16) % 1000)/1000.0` → a stable per-category multiplier in `[0.5, 1.5)`. No RNG.
- **Strategies** (pure `pick(team, remaining, arena) -> challenge_id | None`):
  - `greedy_points` — highest `points`, tie → lowest `id` (lexicographic).
  - `greedy_easy` — lowest `effort`, tie → highest `points`, tie → lowest `id`.
  - `ratio_balanced` — highest `points/effort`, tie → lowest `id`.
  - `category_focus(cat)` — prefer `category == cat` (then `greedy_points`), else `greedy_points`.
  - `best_response` — the **game-theoretic** strategy (see Game theory below): pick the challenge
    maximizing this team's *contention-adjusted* expected value `points + (first_blood_bonus if
    this team is the fastest solver among all teams for that challenge else 0)`, where "fastest" =
    lowest `effort / skill(seed, team, category)`, ties by `id`. Best-responds to opponents' known
    skills — a team only chases a first-blood it can actually win, else takes guaranteed points.
  All ties broken deterministically by `id` so picks are total-ordered.
- `STRATEGIES` registry (name → fn) for the CLI; `make_team(id, strategy_name, seed)` builds a
  team state `{id, strategy, points:0, solves:[], current:None, accrued:0.0}`.

### `engine.py` — the stepper
`run_ctf(arena, teams) -> result`:
1. `validate_arena`; init a `Ledger`; `solved_global = {}` (challenge_id → first-solver team id).
2. For `tick` in `1..=time_box_min`, for each team in **sorted `id` order**:
   - if no `current`, `pick` from `remaining` (challenges not solved *by this team*); set
     `current`, reset `accrued`.
   - advance: `accrued += skill(seed, team.id, challenge.category)` (one sim-minute of work).
   - if `accrued >= challenge.effort`: credit `points`; if `challenge.id` not in `solved_global`
     → `solved_global[id]=team.id` + add `first_blood_bonus` (first-blood); record the solve on
     the team; `ledger.append({kind:"solve", tick, team, challenge, points, first_blood:bool})`;
     clear `current`.
   - A challenge whose `effort/skill` exceeds the remaining box is simply never completed (partial
     work is discarded at expiry — no partial credit).
3. After the loop: `ledger.append({kind:"final", scoreboard, ranking})`.
4. **Ranking:** sort teams by `(points desc, solves desc, first_bloods desc, id asc)` — fully
   deterministic tie-break.
5. **Game-theoretic analysis** (`game.nash_analysis`, see below) appended as a
   `{kind:"nash", ...}` event.
6. **Reward** (`reward.mint_trophy`, see below): the rank-1 champion earns a codename trophy,
   appended as the final `{kind:"trophy", ...}` event (chained — so the trophy is itself
   tamper-evident).
7. Return `{scoreboard:[{team,strategy,points,solves:int,first_bloods:int}], ranking:[team_ids],
   nash:{...}, trophy:{...}, timeline:[ledger events], chain_ok:bool, chain_hash:str}` (`chain_hash`
   = last entry's hash). Note: the `nash`/`trophy` events are appended *before* `chain_hash` is
   read, so they are inside the verified chain; replay-stability still holds (all payloads are pure
   functions of `(seed, arena, teams)`).

Edge cases: a team that solves everything stops picking (`pick` returns `None` → idle). Two teams
solving the same challenge on the **same tick** → first-blood goes to the lower `id` (team order
within the tick is sorted by id). Determinism holds because tick order is fixed.

### `game.py` — the game-theoretic layer
First-blood is a **contested resource**, so challenge selection is a *congestion game*. We analyze
the abstracted **one-shot first-pick game**: each team simultaneously chooses one challenge (its
first target); its payoff is `points + (first_blood_bonus if it is the fastest among teams that
chose the same challenge else 0)`, "fastest" = lowest `effort / skill`, ties by `id`.
- `expected_value(team, challenge, all_teams, arena) -> int` — the contention-adjusted payoff above
  (this is exactly what the `best_response` strategy maximizes).
- `nash_analysis(arena, teams) -> {first_picks:{team:challenge}, is_nash:bool,
  regret:{team:int}, social_welfare:int, optimum:int, price_of_anarchy:float}`:
  - `first_picks` = each team's `best_response` first choice.
  - For each team, compute `regret` = (best payoff over ALL its alternative single picks, holding
    others' `first_picks` fixed) − (its payoff at `first_picks`). `is_nash` = every regret ≤ 0
    (no team profits by unilaterally deviating — a pure-strategy Nash equilibrium of the one-shot
    game).
  - `social_welfare` = Σ payoffs at `first_picks`; `optimum` = max Σ payoffs over all *distinct*
    assignments (small N, brute-force ≤ teams!·challenges); `price_of_anarchy = optimum /
    social_welfare` (1.0 = efficient). Pure, deterministic, fast (N≤4, ≤8 challenges).
- **Note (no overclaim):** `best_response` best-responds to *pessimistic* (all-team) contention,
  whereas the one-shot Nash payoff uses *actual-picker* contention — different payoff models, so the
  best-response first-pick profile is **not guaranteed** to be a Nash equilibrium. `nash_analysis`
  honestly reports whether *this run's* profile is an equilibrium (it may be False) + the regrets +
  the price of anarchy. Correctness is tested on **constructed** cases (a known equilibrium →
  `is_nash` True; a known profitable deviation → `is_nash` False with positive `regret`).

### `reward.py` — the non-currency winner reward (a codename trophy)
The champion is **not** paid currency — they earn a **codename honorific + a verifiable trophy
attestation** (recognition + a tamper-evident bragging right; on-brand with the lore codenames and
the hash-chain ethos).
- `CODENAMES` — a fixed ASCII lore pool (`brett-shaw, anstetten, praetorian, infra-light,
  feketecs, sherlock, katedralis, bolygorozsa, opium-waltz, the-cordon, static-armor, the-dossier`).
- `mint_trophy(champion_id, prior_hash, welfare) -> {kind:"trophy", champion, codename,
  bound_to:prior_hash, welfare, citation}` — `codename = CODENAMES[int(prior_hash,16) % len]`
  (deterministic, run-bound: the codename is a function of the run's pre-trophy chain hash, so it
  is unforgeable + replay-stable). `citation` = a short honorific string. The engine appends this
  as the final ledger entry, so the trophy is **chained** (verifiable; a third party can confirm
  `champion` earned `codename` for the run whose hash is `bound_to`).
- Reward is **non-currency**: a title + a cryptographic certificate, not points/money. (The optional
  `ctf-arena.vaked` dogfood additionally grants the champion node an attenuated bonus *capability* —
  authority as reward, the repo's "currency isn't money" stance.)

### `ledger.py` — hash-chained timeline
Mirror `tools/oracle/ledger.py`: reuse `ralphcore.{make_entry, verify_chain, GENESIS_HASH}`.
Support an **in-memory** ledger (no file) for the engine/tests + an optional path for persistence.
`append/entries/verify`. (Timestamp-free → replay-stable.)

### `ctf.py` — CLI
`ctf run [--teams N=4] [--seed S=1337] [--box-min 20] [--strategies a,b,c,d] [--json] [--out PATH]`
— build N teams (default strategies cycle `greedy_points, greedy_easy, ratio_balanced,
best_response`), `run_ctf`, print the scoreboard table + ranking + the **Nash verdict**
(`equilibrium: yes/no`, `price_of_anarchy`) + the **champion trophy** (`🏆 <team> → codename
"<codename>"`) + `chain_ok` + `chain_hash` (or `--json`). `ctf replay --events PATH` — reload a
persisted timeline, `verify_chain`, recompute the scoreboard from the `solve` events, confirm it
matches the recorded `final`, and re-derive the codename from the bound hash → prints `REPLAY OK` /
mismatch.

## Tests (`tools/ctf/test_ctf.py`, pure stdlib, module-level `test_*` + `assert`, M3-runnable)
- `skill` deterministic + in `[0.5,1.5)`; each strategy's `pick` is deterministic + respects its
  ordering + tie-break.
- `validate_arena` rejects dup ids / non-positive / empty.
- first-blood credited **once** (the second solver of a challenge gets points but no bonus).
- **time-box enforced:** no `solve` event has `tick > box`; a box of `1` yields few/no solves.
- ranking + deterministic tie-break (construct a tie, assert id-order).
- **replay-stability:** `run_ctf` twice on the same `(seed, arena, teams)` → identical scoreboard
  **and** identical `chain_hash`; and `verify_chain` is True.
- 2-team and 4-team runs both produce a coherent scoreboard; `chain_ok` True.
- `replay` recomputes the same scoreboard from a persisted timeline.
- **Game theory:** `best_response.pick` deterministic + maximizes contention-adjusted value;
  `nash_analysis` flags a profitable deviation on a constructed non-equilibrium case (`is_nash`
  False, positive `regret` for the deviator) and returns `is_nash` True on a constructed
  equilibrium (all `regret ≤ 0`); `price_of_anarchy ≥ 1.0` always; `nash_analysis` is deterministic.
- **Reward:** champion == `ranking[0]`; `codename` is deterministic + **replay-stable** (same run →
  same codename) and changes with the bound hash; the `trophy` entry is chained and `verify_chain`
  stays True after it; `replay` re-derives the same codename from `bound_to`.

## Verify (acceptance — M3, no deps)
`python3 tools/ctf/test_ctf.py` green; then `ctf run` (default 4-team) **twice** → byte-identical
scoreboard + identical `chain_hash` + `chain_ok=True` + max solve tick ≤ 20. Record in the doc: the
demo scoreboard, the two identical hashes (replay-stability), the **Nash verdict + price-of-anarchy**,
and the **champion's codename trophy** (with its `bound_to` hash, re-derivable on replay).

## Docs
`docs/ctf/v0.md` (design, the demo scoreboard, the replay-stability proof) + `tools/ctf/README.md`
(usage). **Optional dogfood:** `vaked/examples/ctf-arena.vaked` — the arena as a Vaked capability
graph (an `operator` + N team `meshNode`s with a `strategy` open field + a `catalog` of challenges),
mirroring `redteam-swarm.vaked`; must pass `vakedc check`. Include only if it lands clean.

## Out of scope (follow-ups)
- Agent/LLM-driven teams (real solving) — a separate cycle; this is the deterministic strategy sim.
- Live network/challenge infra. Inter-team interaction (sabotage/steals). A surface/TUI scoreboard.

## Constraints
Pure stdlib; M3-safe (no compile, no box, no LLM); deterministic (no wall-clock / unseeded RNG);
reuse `ralphcore` chain read-only; Snyk OFF.
