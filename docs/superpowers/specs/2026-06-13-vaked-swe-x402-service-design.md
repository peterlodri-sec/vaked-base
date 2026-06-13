# Vaked SWE-as-a-service over x402 on Base (design)

## Status

Design / exploration (2026-06-13). A **service layer** that sits *on top of* the
runtime, not a core primitive — it exposes a Vaked agent field as a paid, onchain,
verifiable SWE service: `swe <prompt> <scale>`. Builds entirely on primitives that
already exist; the web3 parts are thin adapters at the edges. Convention: design →
plan → impl; this is the design + the honest case for/against.

## Spark

> integrating with 'base' and running vaked as a web3 `swe <prompt> <scale>` service

The calibration example [`agentfield-swe.vaked`](../../../vaked/examples/agentfield-swe.vaked)
is *already* the service: a `planner → coder → reviewer → publish` workflow DAG over
a capability-attenuated mesh, bounded by a `budget` block, grounded by an `index`,
remembering via `memory`. This note swaps its ingress (a GitHub issue label) for an
**onchain paid request**, and its trust model (trust-the-operator) for a
**verifiable receipt**.

## The request

```
swe <prompt> <scale>
```

- **`<prompt>`** — the task. Becomes the `workflow swe_af` input (replacing
  `on = "github.issue.labeled:agent"`).
- **`<scale>`** — how much compute to spend. Maps **directly** to the existing
  `budget swe { tokens, wallClock, toolCalls, fuel }` block (agentfield-swe lines
  80–86). Scale is a budget tier; **price = f(budget)** in USDC. Paying *is* buying
  a budget; `mcp-brokerd` already enforces it, so spend can't exceed the paid tier.

## Why Vaked fits (the mapping)

Every hard part already exists; web3 is a rim.

| Service need | Vaked primitive (today) | Base / web3 edge (adapter) |
|---|---|---|
| `<scale>` = metered compute | `budget swe { tokens, wallClock, toolCalls, fuel }` | x402 price tiers in USDC; payment = budget purchase |
| `<prompt>` = the task | `workflow swe_af` ingress | x402 request body replaces the issue-label trigger |
| enforce the paid tier | `mcp-brokerd` (budgets, approvals) | bounded spend ⇒ no overrun past payment |
| safe access for a stranger | mesh **capability delegation** (operator → attenuated subset, POLA, [0011](../../language/0011-type-system.md) §4) | mint a **UCAN** on payment: time-boxed `fs.repo_rw` / `mem.recall`, no shared trust root |
| **verifiable result** | `eventd` hash-chained log ([design](./2026-06-12-eventd-design.md)) + `provenance.json` | **anchor the chain head on Base** → onchain receipt of exactly what ran |
| deliver output | content-addressed artifacts (`patch`, catalog, palace) | fetch-by-hash (CDN → IPFS/Arweave tier) |
| agent pays for *its own* inputs | `mcp-brokerd` brokers tool calls | **Base MCP / CDP AgentKit** wallet — field pays x402 for model calls, premium indexes |
| who the service/buyer is | RFC 0006 identity ([SPIFFE](../../../protocol/rfcs/0006-transport-identity-distribution.md), internal) | ERC‑8004 + Basename at the commerce boundary |

## Flow

```
buyer/agent ──HTTP──▶ swe endpoint (x402-enabled)
                      ◀── 402 Payment Required   (PAYMENT-REQUIRED: amount=f(scale), token=USDC, network=base)
buyer wallet ──sign──▶ retry with PAYMENT-SIGNATURE
x402 facilitator ──verify+settle USDC on Base──▶ run authorized
                      │
                      ▼  workflow swe_af: plan → code → review → publish
                      │  bounded by budget(scale); mcp-brokerd enforces; sandboxd isolates
                      ▼
  anchor(eventd head + provenance hash) ──tx──▶ Base   ← the receipt
  deliver artifacts by hash (CDN→IPFS) + mint UCAN(scope, ttl) for the buyer
```

x402 (Base's HTTP-402 payment protocol) needs **no account and no API key**: any
funded wallet — human *or another agent* — can pay per request. That makes `swe`
**composable**: other agents can buy it with no prior relationship.

## New: the `pay` / `chain` capability domain

Onchain actions are authority and must be POLA-bound exactly like `mem`/`fs`. Add a
capability domain (named `pay` to avoid the `chain`↔naming collisions, cf. the
`mem`-vs-`memory` rule in [0014](../../language/0014-memory-primitive.md)):

```vaked
capability pay {
  grant none quote settle spend admin
  order none < quote < settle < spend < admin
}
```

- `pay.quote` — read prices / construct a `402` quote (no funds move).
- `pay.settle` — accept an inbound x402 payment (the service side).
- `pay.spend` — sign an *outbound* payment from the agent wallet, **hard-capped by
  the run `budget`** (the agent buys its own model calls / data).
- `pay.admin` — wallet/key administration; control plane only.

A funded autonomous agent is the scariest thing in web3; gating outbound spend
behind `pay.spend` + the `budget` ceiling + `sandboxd` isolation + the existing
`approvals = "destructive"` is exactly the box Vaked is shaped to provide.

## The verifiable receipt (the actual differentiator)

Without this, `swe` is Stripe-with-extra-steps. With it, it is trust-minimized:

- On `publish`, compute the run's **eventd chain head** (already a sha256 over the
  hash-chained log) and the `provenance.json` hash, and write **one tx** to a Base
  contract: `{ requestId, buyer, eventdHead, provenanceHash, artifactCID, budgetSpent }`.
- The buyer (or anyone) can later **verify the delivered artifacts + log against the
  onchain anchor** without trusting the operator: the eventd chain proves the log
  wasn't rewritten; the anchor proves it existed at block time; the CID proves the
  artifact is the one paid for.
- **Anchor hashes only** — never prompt/code/log payloads (public + permanent).

Honest scope: this proves the **process ran as logged**, not that the patch is
*correct*. Correctness is carried by the `reviewer` node + tests; pricing is by
`budget(scale)`, not outcome.

## Settlement & SLA

- **Escrow-on-publish (v1 lean):** x402 settles up-front for the budget tier; the
  `budget` ceiling guarantees bounded spend. If the run fails before `publish`,
  refund the unspent budget (the `eventd` fold gives an exact `budgetSpent`).
- Alternative: streaming settlement per workflow step — defer (more onchain txs).

## Identity

- **Internal:** unchanged — SPIFFE/SPIRE per RFC 0006.
- **Commerce boundary:** the service registers onchain (ERC‑8004 agent registry +
  a Basename, e.g. `swe.vaked.base.eth`); buyers are identified by wallet / Basename.
  The two are bridged at the x402 ingress, not fused.

## Phases

1. **x402 ingress + budget pricing** — an x402-gated endpoint in front of the
   `swe_af` workflow; `<scale>` → `budget` tier → USDC price; settle, then run.
   (Off-the-shelf x402 facilitator; no contract yet.)
2. **Verifiable receipt** — the Base anchor contract + `pay.settle`; publish
   `{eventdHead, provenanceHash, artifactCID}`; a verifier CLI.
3. **`pay` capability + agent wallet** — `pay.spend` bounded by `budget`; broker
   Base MCP through `mcp-brokerd`; the field buys its own inputs.
4. **UCAN delegation + decentralized delivery** — mint attenuated UCANs on payment;
   IPFS/Arweave artifact tier.

## Non-goals / honest caveats

- **No native token, no tokenomics.** USDC only; the chain is rails + a notary.
- **Anchor, don't migrate.** The eventd log stays local; only its head goes onchain.
- If the verifiable-receipt + agentic-composability angles aren't used, this isn't
  worth a chain — use a normal payment processor.
- SWE output is non-deterministic: "verifiable" = provable provenance/effort, not
  guaranteed correctness.
- Regulatory/abuse surface (a public agent that writes code, spends money, acts
  onchain) — gate hard via `pay`/`approvals`/`sandboxd`; KYC/limits are an operator
  policy, out of scope here.

## Open questions

1. **Escrow model:** up-front budget settle + refund-unspent (v1) vs per-step
   streaming settlement.
2. **Anchor cadence/cost:** one tx per run vs batched Merkle root per epoch (cheaper,
   delayed finality) — reuse the eventd→chain anchoring pattern either way.
3. **UCAN vs SPIFFE bridge:** does the buyer's UCAN map onto an internal SVID for the
   duration, or stay a parallel external proof?
4. **Pricing function** `f(budget)`: linear in tokens/fuel, or tier-stepped; how to
   price `approvals`/human-in-the-loop steps.
5. **Which x402 facilitator / wallet** (CDP AgentKit, Bankr, Sponge) — and self-hosted
   facilitator vs hosted.
