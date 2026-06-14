# Vendored: `karpathy/autoresearch`

This directory vendors the training harness from
**[karpathy/autoresearch](https://github.com/karpathy/autoresearch)** (MIT).

| | |
|---|---|
| Upstream | https://github.com/karpathy/autoresearch |
| Pinned commit | `228791fb499afffb54b46200aca536f79142f117` |
| Vendored on | 2026-06-14 |
| License | MIT — see `LICENSE` (© Andrej Karpathy) |

## Files

| File | Role | nocturne treats it as |
|------|------|-----------------------|
| `prepare.py` | fixed constants, data prep, BPE tokenizer, dataloader, **`evaluate_bpb` ground-truth metric** | **FROZEN — never mutated** |
| `train.py` | the GPT model + optimizer (Muon + AdamW) + training loop | **the mutation target** (copied to `../state/baseline/train.py` as the running baseline) |
| `program.md` | upstream's agent instructions + the output/metric contract | reference; nocturne's own objective lives in `../program.md` |
| `pyproject.toml`, `.python-version` | uv project + deps (torch 2.9.1 cu128) | box bootstrap (`uv sync`) |

## The harness contract (what the driver relies on)

- A trial is **`uv run train.py`** — fixed **5-minute** wall-clock training budget.
- On completion it prints a summary; the metric is the line **`val_bpb: <float>`** (lower is better),
  extracted with `grep "^val_bpb:" run.log`.
- Data is prepared once with **`uv run prepare.py`** into `~/.cache/autoresearch/`.
- `evaluate_bpb` in `prepare.py` is the ground truth — nocturne must not touch `prepare.py`.

> ⚠️ **Unproven in-repo.** This is PyTorch/GPU code; per the project's `NEVER BUILD ON DEVELOPER
> MACHINE` rule it is **not** executed in CI or on a dev box. It is validated only on a rented
> Vast.ai H100 during a real nocturne run. Treat it as vendored-as-is until that first GPU run.

## Updating

Re-fetch from the pinned upstream and bump the commit SHA above:
```
BASE=https://raw.githubusercontent.com/karpathy/autoresearch/<sha>
for f in train.py prepare.py program.md pyproject.toml .python-version; do curl -fsSO "$BASE/$f"; done
```
