# nocturne — a nightly, GPU-rented auto-researcher loop (Karpathy `autoresearch` → Vaked fleet) (design)

> Vaked declares the experiment. Vast.ai materializes the GPU. The ledger supervises.
> The agent mutates. BPB testifies. Mastodon reveals.

## Status

Design / brainstorm (2026-06-14). **Tooling**, not the Vaked language — no grammar gate.
Owner-directed: integrate [`karpathy/autoresearch`](https://github.com/karpathy/autoresearch)
into the fleet, running **every night for ~6 hours** on a **rented Vast.ai GPU**. The Vaked
reference port is the **private** [`peterlodri-sec/vast-autoresearcher`](https://github.com/peterlodri-sec/vast-autoresearcher)
— **not yet readable from this session** (out of GitHub-tool scope; WebFetch 404 on private).
**Several items below are OPEN pending that port's actual architecture** — they are flagged
`⟨OPEN⟩` and must be reconciled before implementation.

A **third sibling** to `ralph` (nightly decision loop) and `optitron` (nightly optimization
crawl): same abstain-by-default rhythm, same hash-chained ledger, same `agent`-issue → swe_af
hand-off, same staged-toot announce — but the "finding" is a **trained model improvement**
(lower validation bits-per-byte) instead of a decision or a compiler tweak.

## Why

Karpathy's `autoresearch` is an **autonomous ML-experiment loop**, not a literature agent. One
trial is: *"It modifies the code, trains for 5 minutes, checks if the result improved, keeps or
discards, and repeats."* Three files: `prepare.py` (frozen harness: data + tokenizer + runtime),
`train.py` (the **only** file the agent edits — nanoGPT-style model + optimizer + loop), and
`program.md` (the human-written objective the agent reasons toward). ~100 five-minute trials fit
in a night on a single H100; **6 hours ⇒ ~60–70 keep/discard trials/night.**

Nothing in the fleet currently does **empirical** research — ralph reasons over structure,
optitron crawls literature, fleet-introspect mines telemetry. nocturne closes the last loop:
**run real experiments overnight, keep what measurably wins, and only escalate a confirmed
improvement to a human/swe_af.** It also dogfoods Vaked's theses on a new axis — *immutable
ledger of trials* (replayable experiment history) and *control* (stop/teardown at runtime, hard
budget cap).

The center of gravity is **GPU compute + an experiment ledger**, not search/synthesis. The GHA
side never trains — it is only the *clock, the wallet, and the scribe*; this keeps nocturne
trivially inside the project's `NEVER BUILD ON DEVELOPER MACHINE` rule (nothing compiles or
trains locally — ever).

## Constraints honoured (owner direction)

- **Nightly, ~6 hours, Vast.ai rented GPU** — provision on demand, run, **always tear down**.
- **Abstain by default** (the optitron move) — a night that beats nothing produces a
  ledger entry + digest toot and **no issue**. Silence is success; a hallucinated "win" is worse.
- **`agent`-labelled issue → swe_af** when (and only when) a trial genuinely beats the committed
  baseline, **confirmed on an independent re-run seed**.
- **Hash-chained ledger**, committed, replayable (`events --replay`) — the experiment memory and
  cross-night novelty source, exactly like optitron/ralph.
- **Double-confirmed manual dispatch** (typed `confirm: RUN` + a protected `nocturne-manual`
  Environment reviewer) — same gate as optitron, because a manual run **spends real GPU money**.
- **Non-bypassable cost caps** — max `$/hr` bid, mandatory teardown trap, monthly spend ceiling
  that disables the cron. GPU dollars are the dominant risk here, unlike the API-only siblings.

## The loop (`nocturne run` — one nightly run; abstain by default)

GHA cron (~02:00 UTC) is a **thin orchestrator** with no GPU; the rented box runs the real loop.

```
┌─ 02:00 cron fires (GHA orchestrator — no GPU, just clock+wallet+scribe) ──┐
│ 1. PROVISION  vastai search/create: cheapest GPU ≥ spec under $/hr cap;   │
│               abort cleanly if none < cap (event: `none{reason:no-gpu}`)  │
│ 2. SYNC       ssh: clone repo @ current baseline train.py + program.md    │
│ 3. RUN ≤~5.5h ssh `timeout <search-budget> <driver>` — Karpathy's         │
│               mutate→train 5min→read val BPB→keep/discard, each trial →    │
│               results.jsonl (reserve the tail of the 6h for step 4)       │
│ 4. CONFIRM    ON THE BOX, before teardown: re-train the night's best      │
│  (on GPU)     train.py on N fresh seeds; append the confirm runs to        │
│               results.jsonl. THIS is the gate's "independent re-run" — it  │
│               MUST happen here because the runner has no GPU.              │
│ 5. HARVEST    scp results.jsonl + best train.py back to the runner        │
│ 6. TEARDOWN   vastai destroy — ALWAYS (trap/finally); the cost lynchpin   │
│ 7. LEDGER     append state/events.jsonl (hash-chained), commit            │
│ 8. GATE       (pure, on runner — reads only the harvested results.jsonl)  │
│               best_bpb < committed_baseline − ε  AND  confirm seeds held?  │
│               ├─ yes → dispatch swe_af with the winning train.py diff      │
│               └─ no  → abstain (ledger-only)                              │
│ 9. ANNOUNCE   stage toot.txt + telegram.txt → push → social CI sends      │
└────────────────────────────────────────────────────────────────────────────┘
```

> **Confirmation runs on the GPU, before teardown (step 4) — not in the gate.** The seed
> re-confirmation needs a GPU, and the runner has none, so it cannot live after teardown. The box
> measures it and writes it to `results.jsonl`; the post-teardown gate (step 8) is then **pure** —
> it only *reads* already-measured numbers and never trains. The 6h wall-clock budgets the search
> (step 3) to leave room for the confirm re-runs (step 4).

### The strict gate (step 8 — pure, reads harvested results; every condition holds, else abstain)
1. **Measured, not claimed.** The improvement comes from `results.jsonl` rows the harness wrote
   from a real 5-minute training run — never from model prose. A trial with no metric is discarded.
2. **Beats the committed baseline** by ≥ `min_bpb_delta` (e.g. 0.002 BPB), not just the night's
   own running best.
3. **Confirmed on independent re-runs** — the winning `train.py`, re-trained **on the box in
   step 4** on N *different seeds*, still clears the baseline (kills lucky-seed noise; the
   empirical analogue of optitron's "≥2 independent sources"). The gate only *checks* these rows;
   it does not train.
4. **Novel** — the winning diff's `signature` isn't already in the ledger or the committed
   baseline history (`git grep` + ledger dedupe), so we don't re-surface a known win.
5. **Sane** — the run produced no NaN/divergence and stayed within the harness's fixed wall-clock
   and token budget (no "won" by changing the rules).

A survivor's swe_af request is *"promote this `train.py` diff to the baseline"* — with the BPB
delta, the diff, the seed-confirmation rows, and a link to the ledger event.

**swe_af hand-off — explicit dispatch, NOT a bare label.** `.github/workflows/swe-af.yml` gates
its `agent`-label trigger on `github.event.sender.login == github.repository_owner` (`swe-af.yml`
lines 39–42), so an `agent` label applied by a *scheduled* job (sender = `github-actions[bot]`)
will **not** fire swe_af — the confirmed win would stall at an issue. nocturne must therefore use
swe_af's owner-equivalent path. Two options:
- **(recommended) `workflow_dispatch` swe-af.yml** with the issue number — the workflow explicitly
  accepts `workflow_dispatch` with an `issue` input and bypasses the sender gate. nocturne opens
  the issue (audit trail), then dispatches swe_af against it. Clean, no extra credential.
- **Label with the owner credential** the other CI bots use (a PAT/app token whose
  `sender.login` resolves to the owner), if nocturne is given that secret — matches however
  optitron/fleet-introspect currently satisfy the same gate.

⟨VERIFY⟩ confirm which path optitron/fleet-introspect actually use today and mirror it, so the
fleet stays consistent. The earlier "no new setup" claim was wrong for a scheduled trigger — this
is the corrected hand-off.

## Mutation driver — DECIDED: OpenRouter-driven pipeline (fleet-native)

**Resolved (2026-06-14, owner).** Each trial's `train.py` mutation is proposed by an
**optitron-style OpenRouter pipeline**, not a full headless coding agent and not a fixed search.
Rationale: controllable + cheaper per call, bounded by a `--budget-total` cap like optitron, and
it **reuses the fleet's existing LLM machinery** (`tools/optitron/internal/llm` — the Eino
OpenRouter wrapper with strict `json_schema` structured output) instead of standing up a new
agent runtime. Mechanics per iteration, on the rented box:

1. The driver builds a prompt from `program.md` + the current `train.py` + recent `results.jsonl`
   trials, and asks the model (via OpenRouter) for **one structured mutation** (a diff/patch to
   `train.py` + a rationale + a `signature`).
2. The driver applies the patch and invokes the **frozen Python/PyTorch harness** for the fixed
   5-minute train + score (the *training* stays PyTorch-on-GPU; only the *mutation generation* is
   the API call).
3. It reads back val BPB from `results.jsonl`, keeps or discards, and loops.

Implications — two viable shapes (⟨OPEN, minor⟩ pick once the port's harness interface is known):
- **Go-reuse — must live INSIDE the optitron module.** Go `internal/` packages are only importable
  by code rooted under `tools/optitron/`, so to reuse `internal/llm` + `internal/ledger` the driver
  must be a **new binary in the optitron module** (`tools/optitron/cmd/nocturne` +
  `tools/optitron/internal/nocturne`) — **exactly** how `cmd/introspect` (fleet-introspect) reuses
  the same core. It would still shell out to the Python training harness on the box. A sibling
  `tools/nocturne/` tree could **not** import those `internal/` packages.
- **Python-local.** A thin Python driver co-located with PyTorch on the rented image that calls
  OpenRouter directly (own small ledger matching ralph's chain format). Simpler on the box; no Go
  module-boundary constraint; doesn't reuse optitron's wrapper.

Either way, the orchestration shell (`provision.sh`, `nocturne.yml`, `program.md`, ledger state)
can live under `tools/nocturne/`; only the **Go** driver, if chosen, must sit in the optitron
module. Models: env-overridable like optitron (a capable codegen model for the mutation, e.g. an
`anthropic/claude-fable-5` / `deepseek-v4` tier).

**Secret forwarding (both shapes).** The driver runs **on the rented box**, where the `ci`
environment's `OPENROUTER_API_KEY` (and optional `LANGFUSE_*`) do **not** exist by default — a
naive flow would provision the GPU then fail on the first mutation call. The orchestrator must
inject them into the remote command: either `ssh box OPENROUTER_API_KEY=… <driver>` (env on the
remote command, not via `~/.ssh` config), or write a **short-lived env file** to the box
(`chmod 600`, deleted on teardown). Never bake the key into the image.

## ⟨OPEN⟩ decisions — reconcile against `vast-autoresearcher` before implementing

1. **Local GPU vs. API.** Confirm the port truly trains on the rented box (PyTorch local, the
   Karpathy shape) vs. driving training through an API. Owner indicated **Vast.ai rented GPU**, so
   assume local training on the box. (The *mutation* is now decided as an OpenRouter call; this
   item is only about where *training* runs.)
2. **One objective or a rotating queue?** ralph picks a *track* each night (`tracks.json`).
   nocturne could be pinned to a single `program.md` (steady SOTA-chasing on one dataset) or carry
   an `objectives.json` queue (rotate datasets/objectives nightly). Recommend **single objective
   first**, add rotation once the loop is proven.
3. **Baseline persistence.** Each night must build on the prior night's best. Propose the winning
   `train.py` baseline is **version-controlled** (committed under `tools/nocturne/baseline/` or
   promoted via the swe_af PR), so "running best" survives the ephemeral GPU box.
4. **GPU spec + bid.** H100 vs A100, exact `$/hr` cap, on-demand vs interruptible. Karpathy tested
   H100; interruptible is cheaper but can be reclaimed mid-night (the harness must checkpoint
   `results.jsonl` so a reclaim ⇒ partial-night ledger entry, not a lost night).

## Files (proposed — mirrors the optitron module layout)

- **`tools/nocturne/`** — the orchestrator + provisioning, sibling to `tools/optitron/`:
  - `PURPOSE.md` — the abstain-by-default mission preamble (optitron/ralph pattern).
  - `provision.sh` — `vastai` search/create/destroy with `$/hr` cap + **mandatory teardown trap**.
  - the **driver** — proposes each mutation via an OpenRouter call, applies the patch, invokes the
    training harness; the on-GPU mutate→train→score→keep/discard loop writes `results.jsonl`.
    **If Go-reuse:** it is NOT a file here — it lives as `tools/optitron/cmd/nocturne` +
    `tools/optitron/internal/nocturne` (Go `internal/` can't be imported by a sibling tree), like
    `cmd/introspect`. **If Python-local:** `tools/nocturne/driver.py` co-located with PyTorch.
    ⟨OPEN, minor⟩ pick once the port's harness interface is known.
  - `program.md` — the research objective (human-edited, the only "knob" for direction).
  - `gate.py` / gate module — **pure** deterministic check over harvested `results.jsonl`:
    baseline delta, confirm-seed rows hold, novelty, sanity (never trains).
  - `ledger.*` — single-writer hash-chained appends (reuse optitron's `internal/ledger` shape if
    Go, or a small Python port matching ralph's chain format).
  - `state/events.jsonl` — append-only, hash-chained, committed. Events: `provision`, `trial`,
    `kept`, `discarded`, `found{issue,bpb,delta}`, `none{reason}`, `teardown`, `error`.
  - `state/baseline/train.py` — the current best (the running-best that survives the box).
- **`.github/workflows/nocturne.yml`** — nightly `schedule` (~02:00 UTC) + double-confirmed
  `workflow_dispatch` (`approve` job on the protected **`nocturne-manual`** Environment, then the
  run in `ci` where secrets live). `permissions: issues: write` (open the survivor issue) +
  `actions: write` (so it can `workflow_dispatch` `swe-af.yml` — the gate-satisfying hand-off, see
  the strict-gate section). Holds the cost guardrails: `$/hr` cap input, monthly-ceiling check that
  no-ops the cron when exceeded.
- **Registry/docs**: `VAKED_AGENTS.md` (add `nocturne`), `docs/agents/ci.md`, this spec, a
  `tools/nocturne/README.md`. Update root `CLAUDE.md` "CI agent fleet" + status tables.

## Economy (the dominant risk — GPU dollars, not tokens)

- **GPU:** ~6 h/night on a Vast.ai H100 ≈ **$6–18/night** (≈ **$180–540/month**) depending on
  bid and on-demand vs interruptible. This is **1–2 orders of magnitude** above the API-only
  siblings (optitron ~$1–3/day, fleet-introspect ~$0.20–0.45/run) — the cost design must be
  proportionally stricter.
- **Per-trial model spend** (decided: OpenRouter pipeline): ~60–70 trials/night × **one
  structured mutation call** each (not a multi-turn agent), so far cheaper than a headless-agent
  driver — a single bounded codegen call per trial. Still bound it with a per-night
  `--budget-total` cap like optitron, and pick a cost-appropriate codegen model; the cap is
  non-bypassable and checked before every call.
- **Hard controls:** `$/hr` bid cap (abort if no GPU under it) · mandatory teardown trap (no
  orphaned instances) · monthly spend ceiling that disables the cron · per-night model-budget cap
  · spend reported in every ledger event + digest toot + a Telegram alert on each night's total.

## One-time owner setup

- **Vast.ai:** account + `VAST_API_KEY` as a secret in the GitHub `ci` Environment; SSH key for
  the rented box. (⟨OPEN⟩ — confirm the port's expected env var names.)
- **Driver secrets forwarded to the box:** `OPENROUTER_API_KEY` (+ optional `LANGFUSE_*`) already
  live in the `ci` Environment for the siblings — no new secret, but the orchestrator must
  **inject** them into the remote SSH command / a short-lived env file (see the mutation-driver
  section); they are not on the rented box otherwise.
- **GitHub** → Settings → Environments → create **`nocturne-manual`** → add yourself as a Required
  reviewer (no secrets — purely the manual-run approval gate, like `optitron-manual`).
- **Monthly ceiling:** set the spend cap value (workflow input/secret) the cron checks before
  provisioning.
- Social plumbing is **already live** — reuses `social-post.yml` / `telegram-post.yml` (staging
  files); no new setup there.
- **swe_af hand-off:** the bare `agent` label does **not** trigger swe_af from a scheduled job
  (owner-sender gate, `swe-af.yml` 39–42). nocturne `workflow_dispatch`es `swe-af.yml` instead —
  so the only setup is granting the workflow `actions: write` (above). ⟨VERIFY⟩ mirror whatever
  optitron/fleet-introspect do today.

## Verification

- `bash tools/nocturne/provision.sh --dry-run` — print the `vastai` search/create/destroy plan +
  `$/hr` cap + estimated nightly cost, **no GPU rented, $0**.
- `NOCTURNE_DRY_ACT=1 nocturne run --once` — full pipeline on a tiny CPU smoke config (or a
  short-rented box), but issue/toot only **drafted**, not sent.
- `nocturne events --replay` — verify the hash chain + list nights/findings.
- Teardown safety drill: kill the orchestrator mid-run ⇒ confirm the `vastai destroy` trap fired
  and no instance is left billing.
- Dispatch `nocturne.yml` with `confirm=RUN` ⇒ pauses on the `nocturne-manual` approval **before**
  any spend.

## Build order (design → plan → implement, per project convention)

1. Reconcile the ⟨OPEN⟩ items against `vast-autoresearcher` (add it to session scope or paste
   `program.md` + the driver + env contract).
2. Provisioning shell first (`provision.sh` + teardown trap + `nocturne.yml` dry-run) — prove
   rent/teardown/cost-cap in isolation, no training, before any model or GPU spend.
3. Port/adapt the on-GPU loop + `results.jsonl` contract.
4. Gate + ledger (reuse optitron's hash-chain).
5. Announce + `agent`-issue hand-off; register in the fleet docs.
