# COST_ANALYSIS — vaked-oracle reverser team (slice 4)

**Analytical estimate — NO real API calls.** Per-"experiment" cost of one `oracle team`
run, default roster (2 local panelists FREE + 1 flash panelist + 1 **deepseek-v4-pro**
judge). Prices from OpenRouter (2026-06-15).

## Prices (per 1M tokens)

| model | role (codename) | $ in | $ out |
|---|---|---|---|
| `qwen2.5-coder-3b` (local :8091) | panelist **infra-light** | 0 | 0 |
| `llm4decompile` (local :8090) | panelist **static-armor** | 0 | 0 |
| `deepseek-v4-flash` | panelist **feketecs** | 0.098 | 0.196 |
| `deepseek-v4-pro` | judge **anstetten** | **0.435** | **0.870** |

## Token assumptions (per function, one debate round)

Grounded in the oracle: Ghidra pseudo-C is verbose; refined-C is short; the judge's
**reasoning tokens** (effort=high) dominate and are billed as output.

| call | in tok | out tok | note |
|---|---|---|---|
| flash panelist (feketecs) | 2,000 | 500 | pseudo-C ~1.5k + prompt ~0.3k + investigate ~0.2k; refined-C out |
| **pro judge (anstetten)** | 3,400 | **3,200** | pseudo-C + 3 candidates + instr; out = ~200 verdict + **~3,000 reasoning** |
| local panelists ×2 | — | — | FREE |

## Per-call → per-function

```
flash panelist = (2000·0.098 + 500·0.196)/1e6           = $0.000294
pro judge      = (3400·0.435 + 3200·0.870)/1e6           = $0.004263
local ×2                                                 = $0
-----------------------------------------------------------------
per function (1 round)                                   ≈ $0.00456
   └─ the pro judge is ~93% of paid spend (reasoning tokens drive it)
```

## Per-experiment (1 panel round per function)

| functions (N) | cost | + refine ×2 |
|---|---|---|
| 3 (slice-1 scale) | **$0.014** | $0.027 |
| 10 | **$0.046** | $0.091 |
| 25 | $0.114 | $0.228 |
| 50 | **$0.228** | $0.456 |

## Sensitivity — the swing factor is judge reasoning volume

- **effort=high** (~3k reasoning tok, assumed above) → per-fn $0.0046.
- **effort=max** (~10k reasoning tok) → pro judge $0.0104/fn → per-fn ≈ $0.0107.
  N=50 × refine×2 × max ≈ **~$1.07** (the realistic upper bound).
- **pro as a panelist too** (pro-heavy diverse panel) → +~$0.0043/fn per pro panelist.

## Headline

> **One experiment ≈ 1–25 cents.** Even a heavy run (50 functions × 2 refine rounds ×
> max-reasoning judge) stays **~$1**. The two local panelists are free; the flash panelist
> is rounding error; **the deepseek-v4-pro judge's reasoning tokens are ~90% of every
> dollar.** Cost is not a constraint at this scale — quality/latency are.

## Levers (if cost ever matters)

1. Judge `reasoning_effort` high→non-think on easy functions (biggest lever, ~10×).
2. Cache the pseudo-C across refine rounds (don't resend) — cuts judge input.
3. Swap the pro judge → flash judge for routine functions; reserve pro for low-fidelity ties.
4. All-local panel + local judge (qwen) = **$0** (lower quality ceiling).

## Formula (plug real numbers)

```
per_fn = Σ_panelists (in·p_in + out·p_out)/1e6  +  (judge_in·j_in + judge_out·j_out)/1e6
experiment = per_fn · N · refine_rounds
```

**Validate against reality:** once the Langfuse MCP is wired (`langfuse.crabcc.app`), real
per-run token counts + cost replace these estimates — this doc is the pre-flight bound.

---
Sources: OpenRouter [deepseek-v4-pro](https://openrouter.ai/deepseek/deepseek-v4-pro) ·
[deepseek-v4-flash](https://openrouter.ai/deepseek/deepseek-v4-flash) (prices 2026-06-15).
