# nocturne — a nightly, GPU-rented auto-researcher loop (Karpathy `autoresearch` → Vaked fleet) (design)

> Vaked declares the experiment. Vast.ai materializes the GPU. The ledger supervises.
> The agent mutates. BPB testifies. Mastodon reveals.

## Status

Design / brainstorm (2026-06-14). **Tooling**, not the Vaked language — no grammar gate.
Owner-directed: integrate [`karpathy/autoresearch`](https://github.com/karpathy/autoresearch)
into the fleet, running **every night for ~6 hours** on a **rented Vast.ai GPU**.

> **Reconciled against the reference port (2026-06-14).** The `⟨OPEN⟩`/`⟨VERIFY⟩` items below were
> flagged when the private [`peterlodri-sec/vast-autoresearcher`](https://github.com/peterlodri-sec/vast-autoresearcher)
> couldn't be read. It has since been read, and every marker is now resolved inline.
> **One premise was wrong and is corrected throughout:** `vast-autoresearcher` is **not** a port of
> the `autoresearch` BPB loop. It is a *separate, simpler* vast.ai box — a single-shot
> `arXiv → LLM-designs-one-experiment → run → report → ntfy` pipeline (stdlib harness, one LLM pass,
> **no `train.py`, no BPB, no baseline**). What it actually contributes is **proven scaffolding**:
> on-demand vast rent + mandatory teardown (`watch-and-destroy`), OpenBao / credential-scrubbed-env
> secret handling, and an **OpenRouter** driver (`LLM_API_KEY` + `LLM_BASE_URL=https://openrouter.ai/api/v1`,
> default `deepseek/deepseek-chat`). The **BPB mutate→train→keep/discard loop itself comes from the
> now-public [`karpathy/autoresearch`](https://github.com/karpathy/autoresearch)** (AI agents running
> research on single-GPU nanochat training; metric `val_bpb`), which nocturne ports onto that
> scaffolding.

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

Nothing in the fleet currently does **empirical** research — ralph reasons over structure and
optitron crawls literature (a planned `fleet-introspect` would mine telemetry, but is **not in the
tree** yet). nocturne closes the last loop:
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
│ 9. ANNOUNCE   stage toot.txt + telegram.txt → post inline, or push with a │
│               PAT (a GITHUB_TOKEN push alone won't trigger the social CI)  │
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

**swe_af hand-off — `workflow_dispatch`, not a bare label (verified).**
`.github/workflows/swe-af.yml` gates its `agent`-label trigger on
`github.event.sender.login == github.repository_owner` (lines ~37–42) and otherwise only runs on an
explicit `workflow_dispatch` whose single input is the `issue` number. **Verified against optitron
(`origin/claude/vaked-optitron`):** optitron files a **bare `agent` label** via
`gh issue create … --label agent` (`tools/optitron/internal/run/act.go`) using the default
`GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` (`optitron-crawl.yml`). That path does **not** auto-fire
swe_af from a scheduled run — twice over: (a) the sender is `github-actions[bot]`, not the owner, so
the gate fails; and (b) GitHub suppresses workflow triggers from events created with the default
`GITHUB_TOKEN`. So optitron's scheduled finding lands a **labelled issue the owner then picks up**;
it does not chain into swe_af automatically. (`fleet-introspect` is named in the fleet vision but is
**not in the tree**, so there is no second precedent to mirror.)

nocturne therefore **improves on the bare-label path deliberately**: it opens the issue (audit
trail) and then **`workflow_dispatch`es `swe-af.yml`** against that issue number — the one path that
actually clears both the sender gate and the `GITHUB_TOKEN` trigger-suppression. This is a justified
divergence from optitron, not an inconsistency; mirroring optitron's bare label (and letting the
owner hand-pick the issue) stays available if auto-chaining is unwanted.

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

Implications — two viable shapes (**resolved: the port's harness is stdlib Python with an
OpenAI-compatible client, so Python-local is the natural fit**; Go-reuse stays available if optitron
lands on `main` first and tighter wrapper reuse is wanted):
- **Go-reuse — must live INSIDE the optitron module.** Go `internal/` packages are only importable
  by code rooted under `tools/optitron/`, so to reuse `internal/llm` + `internal/ledger` the driver
  must be a **new binary in the optitron module** (`tools/optitron/cmd/nocturne` +
  `tools/optitron/internal/nocturne`) — and optitron must land on `main` first (it currently lives
  only on `origin/claude/vaked-optitron`; there is no `cmd/introspect` precedent in-tree). It would
  still shell out to the Python training harness on the box. A sibling `tools/nocturne/` tree could
  **not** import those `internal/` packages.
- **Python-local.** A thin Python driver co-located with PyTorch on the rented image that calls
  OpenRouter directly (own small ledger matching ralph's chain format). Simpler on the box; no Go
  module-boundary constraint; doesn't reuse optitron's wrapper.

Either way, the orchestration shell (`provision.sh`, `nocturne.yml`, `program.md`, ledger state)
can live under `tools/nocturne/`; only the **Go** driver, if chosen, must sit in the optitron
module. Models: env-overridable like optitron (a capable codegen model for the mutation, e.g. an
`anthropic/claude-fable-5` / `deepseek-v4` tier).

**Secret forwarding (verified against the port's contract).** The driver runs **on the rented
box**, where the `ci` environment's OpenRouter key does **not** exist by default — a naive flow
would provision the GPU then fail on the first mutation call. The port already solves this two ways,
and nocturne should reuse them rather than invent a third:
- **Preferred — OpenBao (the port's default).** Stage the OpenRouter key in OpenBao and pass the box
  only a **scoped, revocable `BAO_TOKEN`** (+ `BAO_ADDR` / `BAO_SECRET_PATH`); the harness pulls the
  real key at startup into the pipeline process only, so the vast template never holds a raw key.
- **Fallback — inject at dispatch.** `ssh box LLM_API_KEY=… LLM_BASE_URL=https://openrouter.ai/api/v1
  <driver>` on the remote command (not via `~/.ssh`), or a **short-lived env file** (`chmod 600`,
  deleted on teardown).

The port's var name is **`LLM_API_KEY`** (it holds the OpenRouter key), not `OPENROUTER_API_KEY` —
mirror that on the box. The port additionally **scrubs every credential-looking var from the
untrusted experiment's subprocess env** and can drop it to an unprivileged `EXPERIMENT_USER`; keep
both, since the mutated `train.py` is model-written code. Never bake any key into the image.

## Reconciled decisions (were `⟨OPEN⟩` — now resolved against `vast-autoresearcher`)

1. **Local GPU vs. API — RESOLVED: local on the box.** The port runs its experiment on the rented
   GPU (PyTorch image), confirming the local-training shape. **Caveat captured above:** the port
   executes a *one-shot LLM-written experiment script*, not a persistent `train.py` BPB loop — so
   nocturne's mutate→train→keep/discard loop is **ported from `karpathy/autoresearch`, not inherited
   from the port.** The port only proves local-GPU execution + the rent/secrets/teardown scaffolding.
2. **One objective or a rotating queue — RESOLVED: single `program.md` first.** The port already
   supports batching (`RESEARCH_QUEUE_FILE`, newline-delimited, crash-skipped), so an
   `objectives.json` rotation (ralph's `tracks.json` shape) is cheap to add later. Start pinned to
   one objective; add rotation once the loop is proven.
3. **Baseline persistence — RESOLVED: net-new, version-controlled.** The port keeps **no** baseline
   (it is stateless — output is pulled off `/workspace/output`, then the box is destroyed). So
   nocturne must **add** persistence: the winning `train.py` is committed under
   `tools/nocturne/state/baseline/train.py` (promoted via the swe_af PR), so the running-best
   survives the ephemeral GPU box. This is nocturne's own design, not inherited.
4. **GPU spec + bid — DECIDED (owner): H100, karpathy-matched.** A single **H100** under a `$/hr`
   bid cap, on-demand by default (~$6–18/night; the cost-guards below are sized for this tier). The
   port's RTX 4090 @ `dph<0.4` is its own cheaper profile, not nocturne's target. **Interruptible**
   stays a cheaper option **only with** the checkpoint rule: `results.jsonl` is flushed per-trial so
   a mid-night reclaim yields a partial-night ledger entry, not a lost night.

## Files (proposed — mirrors the optitron module layout)

- **`tools/nocturne/`** — the orchestrator + provisioning, sibling to `tools/optitron/`:
  - `PURPOSE.md` — the abstain-by-default mission preamble (optitron/ralph pattern).
  - `provision.sh` — `vastai` search/create/destroy with `$/hr` cap + **mandatory teardown trap**.
  - the **driver** — proposes each mutation via an OpenRouter call, applies the patch, invokes the
    training harness; the on-GPU mutate→train→score→keep/discard loop writes `results.jsonl`.
    **Resolved: Python-local** — `tools/nocturne/driver.py` co-located with PyTorch on the rented
    image (matches the port's stdlib-Python harness; no Go module-boundary constraint). The
    Go-reuse alternative (`tools/optitron/cmd/nocturne` + `tools/optitron/internal/nocturne`, since
    Go `internal/` can't be imported by a sibling tree) stays open only if optitron merges to
    `main` first and reusing its `internal/llm` + `internal/ledger` is preferred.
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
  sibling (optitron ~$1–3/day) — the cost design must be proportionally stricter.
- **Per-trial model spend** (decided: OpenRouter pipeline): ~60–70 trials/night × **one
  structured mutation call** each (not a multi-turn agent), so far cheaper than a headless-agent
  driver — a single bounded codegen call per trial. Still bound it with a per-night
  `--budget-total` cap like optitron, and pick a cost-appropriate codegen model; the cap is
  non-bypassable and checked before every call.
- **Hard controls:** `$/hr` bid cap (abort if no GPU under it) · mandatory teardown trap (no
  orphaned instances) · monthly spend ceiling that disables the cron · per-night model-budget cap
  · spend reported in every ledger event + digest toot + a Telegram alert on each night's total.

## One-time owner setup

- **Vast.ai:** account + the vast API key as a secret in the GitHub `ci` Environment (the
  orchestrator runs `vastai set api-key` from it — the port authenticates the CLI that way, not via
  a box-side env var); SSH key for the rented box. **Box-side env contract (verified from the
  port):** `LLM_API_KEY` (holds the OpenRouter key), `LLM_BASE_URL=https://openrouter.ai/api/v1`,
  `LLM_MODEL`, `RESEARCH_*` / `OUTPUT_DIR` / `EXPERIMENT_USER`, and OpenBao
  `BAO_ADDR` / `BAO_TOKEN` / `BAO_SECRET_PATH`.
- **Driver secrets forwarded to the box:** the OpenRouter key already lives in the `ci` Environment
  for the siblings — no new secret, but the orchestrator must get it onto the box as **`LLM_API_KEY`**
  (the port's var), preferably via a scoped OpenBao `BAO_TOKEN`, else injected on the remote SSH
  command / a short-lived env file (see the mutation-driver section). It is not on the rented box
  otherwise.
- **GitHub** → Settings → Environments → create **`nocturne-manual`** → add yourself as a Required
  reviewer (no secrets — purely the manual-run approval gate, like `optitron-manual`).
- **Monthly ceiling:** set the spend cap value (workflow input/secret) the cron checks before
  provisioning.
- **Social plumbing — verified, and it needs care.** nocturne reuses `social-post.yml` /
  `telegram-post.yml`, but both are **`on: push` (paths-triggered)** by design — their headers note
  `workflow_dispatch` *can't fire from a feature branch*, so adding a `workflow_dispatch:` trigger
  would not help. The catch: **a push made by a scheduled job's `GITHUB_TOKEN` does not trigger
  another workflow** (GitHub recursion prevention), so a staged-then-pushed digest is committed but
  never posted. **How the siblings post today (verified):** ralph stages `toot.txt` and `git push`es,
  relying on the push trigger; optitron stages + pushes for Mastodon **but posts Telegram inline** via
  `appleboy/telegram-action` in its own job (`optitron-crawl.yml`), sidestepping the trigger. nocturne
  should mirror that — **post inline** (Mastodon `cbrgm/mastodon-github-action` + Telegram
  `appleboy/telegram-action`) from its own job, **or** push the staging commit with a **PAT/App
  token** so the push trigger fires. (`workflow_dispatch`-ing the social workflows is not an option —
  they carry no such trigger by design.)
- **swe_af hand-off:** the bare `agent` label does **not** trigger swe_af from a scheduled job —
  both the owner-sender gate (`swe-af.yml` ~37–42) and GitHub's `GITHUB_TOKEN` trigger-suppression
  block it (verified: optitron files a bare `agent` label with the default `GITHUB_TOKEN`, so its
  scheduled findings wait for the owner). nocturne instead opens the issue and `workflow_dispatch`es
  `swe-af.yml` against it (it is on the default branch and accepts a `workflow_dispatch` `issue`
  input) — so the only setup is granting the workflow `actions: write` (above).

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

1. ~~Reconcile the `⟨OPEN⟩` items against `vast-autoresearcher`~~ — **done (2026-06-14; see the
   reconciliation note + resolved-decisions section above).** Adapt the port's proven scaffolding:
   `onstart.sh` (box bootstrap), `watch-and-destroy` (teardown trap), the OpenBao / scrubbed-env
   secret handling, and the `LLM_*` OpenRouter env contract.
2. Provisioning shell first (`provision.sh` + teardown trap + `nocturne.yml` dry-run) — prove
   rent/teardown/cost-cap in isolation, no training, before any model or GPU spend.
3. Port/adapt the on-GPU loop + `results.jsonl` contract.
4. Gate + ledger (reuse optitron's hash-chain).
5. Announce + `agent`-issue hand-off; register in the fleet docs.
