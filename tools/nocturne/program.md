# nocturne — research objective

> This is the single knob that steers the night. The driver feeds this file to the model as the
> standing objective before every mutation. Edit this to redirect the research; everything else is
> mechanism.

## Goal

**Lower `val_bpb`** (validation bits-per-byte) of the single-GPU nanochat model in `train.py`,
under the harness's **fixed 5-minute** training budget. Lower is better.

## Rules (the harness enforces these — do not fight them)

- **Only `train.py` may change.** `prepare.py` (data, tokenizer, the `evaluate_bpb` metric) is
  frozen and is the ground truth. Do not attempt to modify it or the evaluation.
- **No new dependencies.** Use only what is already in `harness/pyproject.toml`.
- The script must **run without crashing** and **finish within the time budget**. A crash scores
  nothing.
- **VRAM** is a soft constraint — modest increases are fine for real gains; do not blow it up.

## What to try (everything here is fair game)

Architecture (depth/width, attention variants, normalization, activations), optimizer (Muon/AdamW
hyperparameters, schedules — e.g. WSD vs cosine), batch size, sequence packing, initialization,
the training loop itself. **One coherent change per trial**, named by a short kebab-case
`signature`.

## Taste

**Simplicity wins ties.** A small `val_bpb` gain that adds ugly complexity is usually not worth it;
an equal-or-better result from *removing* code is a great outcome. Weigh complexity cost against the
improvement magnitude. Prefer defensible, general changes over overfit hacks.

## Output contract

Return STRICT JSON: `{"signature":"<short-kebab-id>","description":"<one line>","train_py":"<the
COMPLETE updated train.py>"}`. The `signature` must uniquely name the idea so the ledger can dedupe
it across nights.
