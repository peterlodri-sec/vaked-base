# SWE economic-research deployment (design)

## Status

Design / experiment (2026-06-13). The empirical complement to the
[swe-x402 service design](./2026-06-13-vaked-swe-x402-service-design.md): a dedicated,
cheap, isolated deployment whose job is to **replace the back-of-envelope economics
with measured data** — real unit costs and, above all, real **demand**. Convention:
design → plan → impl; this is the design.

## Purpose

The swe-x402 spec's "Economics (pessimistic projection)" is a guess. The dominant
unknown is **demand** (jobs/week via word-of-mouth, price elasticity), *not* compute —
a `swe` job's cost is almost entirely **remote** model inference, so local hardware
barely moves the result at research volume. This experiment measures the real curve at
**~zero capex**, and only stages hardware *after* demand is shown.

Guiding rule: **spend nothing on the box until the demand question is answered.**

## Deployment target (decision)

- **Now → a dedicated, cheap Linux/NixOS VM** (Hetzner/Vultr, ~$5–20/mo). A *dedicated*
  box (not co-tenant with dev infra — that idea was rejected for the untrusted-code
  blast radius) gives a **clean P&L boundary** (its own wallet, its own ledger, nothing
  commingled) and isolation. Disposable and reproducible (NixOS).
- **macOS → not a host.** The eventual Vaked runtime needs **NixOS + eBPF** (BTF/CO-RE
  kernel; see [`hosts/vakedos`](../../../hosts/vakedos/README.md)). macOS earns a place
  only later as a **job *worker*** for Mac/iOS-specific tasks (a premium tier reached
  over the mesh), never the control plane.
- **Bare metal (the EPYC `vakedos` target) → later, at proven volume**, when concurrency
  /margin justify it and the *full* Vaked isolation runtime (sandboxd/agent-guardd/wasm)
  becomes the product. Do not start here.

Staging path: **cheap VM → (demand proven) → bare-metal `vakedos` → (Mac demand) → add
a macOS worker.**

## Harness, not the full runtime (honesty)

The Vaked runtime is still a **stub** (sandboxd / agent-guardd / memoryd unimplemented),
so economic research today runs a **minimal harness**, not the enforcement plane:

```
x402 ingress  →  run a coding agent on <prompt> at <scale>  →  settle + (later) anchor
   (HTTP 402)     (crib agentfield-swe's plan→code→review shape +        (Base; testnet
                   the pr-review agent's gh/model/crabcc plumbing)         first)
```

Reuse, don't rebuild: the [`agentfield-swe`](../../../vaked/examples/agentfield-swe.vaked)
workflow shape + the pr-review crate's model/`gh`/crabcc plumbing already exist. Wrap
buyer code in an off-the-shelf sandbox (container/microVM) on the dedicated box; keep
the wallet/secrets **out** of the job sandbox (the swe-x402 `pay.spend` rule).

## The economics ledger (the actual research output)

Every job appends one entry to an **append-only, hash-chained ledger** — the proven
eventd / ralph pattern ([ralph](../../../tools/ralph/README.md),
[eventd](./2026-06-12-eventd-design.md)) — so the experiment dogfoods the
immutable-ledger thesis on its own P&L *and* the ledger is the receipt substrate the
service needs later:

```
{ seq, prev, hash,
  ts, prompt_class, scale,            # demand signal
  model, tokens, model_cost_usd,      # COGS
  base_gas_usd, facilitator_fee_usd,
  price_usd, settled,                 # revenue
  wall_clock_s, outcome }             # merged | rejected | failed
```

Weekly fold → the real numbers: **jobs/week (demand), conversion, blended price, gross
margin, net vs fixed**, plus price-elasticity from deliberately varying the scale tiers.
This *is* the replacement for the projection.

## Phases

1. **Harness + ledger, local.** Synthetic + self-submitted jobs to calibrate true COGS
   (tokens/job, $/job) — no payments yet. Answers the *cost* half.
2. **Dedicated VM + testnet.** Stand up the cheap VM; x402 on **Base Sepolia**; open to
   the first word-of-mouth users. Answers the *demand* half cheaply.
3. **Mainnet USDC + real pricing.** Flip to Base mainnet; run real scale tiers; collect
   elasticity. Produce the measured economics table.
4. **Stage decision.** Gated on demand: stay VM, move to bare-metal `vakedos`, and/or
   add a macOS worker.

## Stop / go (avoid sunk-cost)

Define kill criteria up front: e.g. **if, after ~6–8 weeks of phase 2 at a low/intro
price, demand stays below ~N jobs/week, the market isn't there at this price — stop or
re-price**, don't buy hardware. The whole point of the cheap VM is to make that a
~$30 finding, not a $1k one.

## Safety (inherits swe-x402)

Dedicated box (no co-tenant blast radius); wallet/secrets/anchor-signer isolated from
the job sandbox; deny-by-default egress (allowlist model + x402 endpoints only);
per-job `spendUsd` + compute `budget` caps. See the swe-x402
[Security/threat model](./2026-06-13-vaked-swe-x402-service-design.md#security--threat-model-from-the-adversarial-review).

## Open questions

1. **Sandbox backend for buyer code on the VM** — plain container vs microVM
   (Firecracker) for the research phase (full Vaked sandboxd/wasm comes at bare-metal).
2. **Ledger storage** — local JSONL now; when does it graduate to real eventd / a
   published (CDN-anchored) ledger?
3. **Intro pricing for elasticity** — free/near-free to seed word-of-mouth, then ramp?
4. **Demand-source niches** to seed (crabcc/Vaked circle, web3 dev channels) without it
   counting as "marketing."
