# nocturne — the nightly GPU auto-researcher

A nightly, **abstain-by-default** agent that rents a single **Vast.ai** GPU, runs Karpathy's
`autoresearch` **mutate→train 5min→read `val_bpb`→keep/discard** loop for a bounded budget, and
escalates **only** a re-run-confirmed, novel improvement to `swe_af` — else it stays silent. Third
sibling to `ralph` and `optitron`. Design:
[`docs/superpowers/specs/2026-06-14-nocturne-autoresearch-design.md`](../../docs/superpowers/specs/2026-06-14-nocturne-autoresearch-design.md).

> The GHA side is only the **clock, wallet, and scribe** — it never trains (keeps nocturne inside
> the `NEVER BUILD ON DEVELOPER MACHINE` rule). The rented box does the work, behind a `$/hr` cap +
> a `watch-and-destroy` self-destruct.

## Layout

```
tools/nocturne/
  nocturne.py     orchestrator (runs on GHA/dev, NO GPU): provision→drive→harvest→teardown→gate→escalate
  provision.sh    vastai rent/ssh/destroy under a $/hr cap + the watch-and-destroy watchdog
  onstart.sh      box bootstrap: install uv, `uv sync`, one-time `uv run prepare.py`
  driver.py       runs ON the box: the OpenRouter mutation→train→score→keep/discard loop → results.jsonl
  gate.py         PURE verdict over harvested results.jsonl (never trains)
  ledger.py       single-writer SHA256 hash-chained event log (ralph-compatible)
  program.md      the research objective (the only steering knob)
  harness/        vendored karpathy/autoresearch (MIT) — train.py, prepare.py, … (see harness/VENDORED.md)
  state/
    events.jsonl        the hash-chained ledger (committed)
    baseline/train.py   the running-best (committed; promoted via swe_af PR)
    baseline/val_bpb    the committed baseline metric the gate compares against (created on first win)
```

## Commands

```bash
# no-spend validations (run anywhere — no GPU, no money):
bash tools/nocturne/provision.sh --dry-run rent          # print the rent plan + cost ceiling, $0
NOCTURNE_DRY_ACT=1 python3 tools/nocturne/nocturne.py run # full pipeline on synthetic results, drafts not sent
python3 tools/nocturne/nocturne.py events                 # verify + print the hash chain

# real night (needs secrets — spends GPU $):
python3 tools/nocturne/nocturne.py run                    # provision → drive → ALWAYS teardown → gate
```

## Config (env)

| var | default | meaning |
|-----|---------|---------|
| `VAST_API_KEY` | — | Vast.ai key (orchestrator runs `vastai set api-key`) |
| `OPENROUTER_API_KEY` | — | forwarded to the box as **`LLM_API_KEY`** (the port's var name) |
| `LLM_MODEL` | `deepseek/deepseek-chat` | mutation model (OpenRouter) |
| `GPU_NAME` / `MAX_DPH` | `H100_SXM` / `3.0` | GPU tier + `$/hr` bid cap |
| `MAX_MINUTES` | `150` | hard self-destruct deadline (the cost lynchpin) |
| `NOCTURNE_WALL_SECS` / `NOCTURNE_MAX_TRIALS` | `6600` / `60` | on-box search budget |
| `NOCTURNE_CONFIRM_SEEDS` | `2` | independent re-run seeds the gate requires |
| `NOCTURNE_DRY_ACT=1` | — | whole pipeline, **no GPU / no money / drafts not sent** |

## Cost

A real night ≈ **$6–18** on an H100 (the dominant risk — 1–2 orders above the API-only siblings).
Hard controls: `$/hr` bid cap (abort if nothing under it) · `watch-and-destroy` self-destruct ·
`NOCTURNE_MAX_TRIALS` / `NOCTURNE_WALL_SECS` · per-trial OpenRouter cost is tiny (one structured
call/trial). The first validation is a ~2h karpathy-matched H100 run after a sub-$1 smoke.

## Secret forwarding

The box needs the OpenRouter key as **`LLM_API_KEY`** (not `OPENROUTER_API_KEY`). Preferred: stage
it in OpenBao and pass the box a scoped `BAO_TOKEN`. Fallback (what the orchestrator does today):
inject `LLM_API_KEY=… LLM_BASE_URL=…` on the remote SSH command. Never bake a key into the image.

## Status

Scaffold complete + the **no-spend path is validated** (DRY_ACT pipeline, gate, ledger, novelty).
The vendored `harness/` (PyTorch/GPU) is **unproven** until the first real H100 run.
Scheduled/gated by `.github/workflows/nocturne.yml`.
