# Vaked SWE-as-a-service over x402 on Base (design)

## Status

Design / exploration (2026-06-13), **hardened by an adversarial web3 review**
(facts verified against live x402/EIP-3009/ERC-8004/UCAN/Base docs; trust claim
corrected). A **service layer** that sits *on top of* the runtime, not a core
primitive — it exposes a Vaked agent field as a paid, onchain, auditable SWE service:
`swe <prompt> <scale>`. Builds entirely on primitives that already exist; the web3
parts are thin adapters at the edges. Convention: design → plan → impl; this is the
design + the honest case for/against.

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

Payment is an **EIP-3009 `transferWithAuthorization`** USDC payload (random 32-byte
nonce → onchain replay protection). The **payer** needs no account and no API key —
any funded wallet, human *or another agent*, pays per request — which makes `swe`
**composable** (other agents buy it with no prior relationship). Nuance the review
flagged: the **operator** still needs a CDP account for the hosted x402 facilitator
(free tier ~1,000 tx/mo) or must self-host one.

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
`approvals = "destructive"` is the box Vaked is shaped to provide — **but the review
caught a hole:** `budget` bounds *compute units* (tokens/fuel), not *dollars*. A
min-tier buyer can prompt-inject the coder into burning the whole budget on
attacker-controlled x402 endpoints (the agent "buys data" from the attacker; the
operator funds it). So `pay.spend` additionally needs:

1. a **separate outbound dollar ceiling** (not just the compute budget),
2. a **destination allowlist** — no arbitrary x402 URLs,
3. the **wallet key isolated in the control plane, unreachable from any node holding
   `process.spawn*`** — treat the buyer `<prompt>` as fully adversarial all the way to
   the payment signer.

(Caveat: CDP AgentKit custodies keys server-side, itself a trust-the-platform
assumption to reconcile with `pay.admin`.)

## The receipt: tamper-evident commitment, not (yet) trust-minimization

> Corrected after an adversarial web3 review (2026-06-13): the original "verify
> without trusting the operator" framing was **overstated**.

On `publish`, write **one Base tx** anchoring
`{ requestId, buyer, eventdHead, provenanceHash, artifactCID, budgetSpent }` (the
eventd chain head is a sha256 over the hash-chained log). Anchor cost on Base is
~$0.002–0.10, so one tx per run is affordable.

**What this proves:** the operator *committed* to a specific log + artifact at block
time — **tamper-evidence, timestamping, ordering, non-repudiation** (useful for
dispute resolution). **What it does NOT prove:** that the workflow ran at all. eventd
is single-writer, owned by the operator's `agent-supervisord`
([eventd daemon shape](./2026-06-12-eventd-design.md)); the hash chain is tamper-
*evident* against post-hoc edits but gives **zero** protection against the writer
fabricating a valid chain over fictional events in the first place. `budgetSpent` is
likewise operator-asserted (read from the operator's own fold), so a discretionary
refund is not incentive-compatible.

**Real verifiability requires TEE remote attestation:** run the field inside
SGX/TDX/Nitro and co-sign `eventdHead` with a hardware-rooted attestation quote the
buyer verifies. (Independent re-execution is out — LLM SWE is non-deterministic;
zkML isn't viable for agentic workloads in 2026.) So split the phase:

- **Phase 2a** — the commitment anchor: dispute/non-repudiation, **no operator trust
  removed**. Do not market as "trust-minimized."
- **Phase 2b** — TEE attestation: the only path that removes operator trust while the
  operator still runs the compute.

- **Anchor hashes only** — never prompt/code/log payloads (public + permanent).

Honest scope: even with 2b, this proves the **process ran as attested**, not that the
patch is *correct* — correctness is the `reviewer` node + tests; price by
`budget(scale)`, not outcome. (ERC-8004's Reputation/Validation registries are the
right home for an operator reputation/stake signal — see Identity.)

## Settlement & SLA

- **Up-front settle is NOT trust-minimized.** If x402 settles to the operator before
  any work, the operator holds 100% of funds and controls the refund; a buyer who pays
  and gets nothing has no recourse (the operator simply never anchors). Operator-
  asserted `budgetSpent` makes the refund discretionary.
- **Required for any trust claim:** an **onchain escrow / streaming-settlement
  contract** where release + refund are constrained onchain, not operator-
  discretionary. Up-front settle + a bounded `budget` is acceptable only for a
  trusted-operator v0; a public service must promote escrow to v1.

## Identity

- **Internal:** unchanged — SPIFFE/SPIRE per RFC 0006.
- **Commerce boundary:** the service registers onchain (ERC‑8004 agent registry +
  a Basename, e.g. `swe.vaked.base.eth`); buyers are identified by wallet / Basename.
  The two are bridged at the x402 ingress, not fused (fusing a 1-hour-rotating SVID
  with a persistent onchain identity would be a category error).
- **ERC‑8004 status:** recent (EIP published Aug 2025; mainnet reference ~Jan 2026;
  Base port TBD). It ships **Identity + Reputation + Validation** registries — adopt
  Reputation/Validation for an operator stake/reputation signal rather than
  reinventing one. Treat it as moving, not settled, infrastructure.
- **Bridge must be forgery-proof:** bind the minted internal SVID/UCAN **1:1 to the
  settled EIP-3009 nonce** and expire it on run completion, so paying once cannot mint
  excess internal authority (RFC 0006's model rests on SVID = verified principal).

## Phases

1. **x402 ingress + budget pricing** — an x402-gated endpoint in front of the
   `swe_af` workflow; `<scale>` → `budget` tier → USDC price; settle, then run.
   (Off-the-shelf x402 facilitator; no contract yet.)
2a. **Commitment anchor** — Base anchor contract + `pay.settle` + onchain escrow;
   publish `{eventdHead, provenanceHash, artifactCID, budgetSpent}`; a verifier CLI.
   Dispute/non-repudiation only — no operator-trust removed.
2b. **TEE attestation** — co-sign `eventdHead` with an SGX/TDX/Nitro quote; only then
   is "trust-minimized" earned.
3. **`pay` capability + agent wallet** — `pay.spend` bounded by `budget`; broker
   Base MCP through `mcp-brokerd`; the field buys its own inputs.
4. **UCAN delegation + decentralized delivery** — mint attenuated UCANs on payment;
   IPFS/Arweave artifact tier.

## Security / threat model (from the adversarial review)

A public agent that writes code, holds a funded wallet, and acts onchain is a large
surface. Ranked:

1. **Prompt-injection → wallet drain (critical).** Outbound dollar ceiling +
   destination allowlist + key isolation from `process.spawn*` nodes (see `pay`).
2. **Escrow/custody gap (high).** No funds held in trust between pay and publish →
   onchain escrow (see Settlement).
3. **Facilitator chokepoint + double-settle race (high).** The hosted x402 facilitator
   can censor / go down (single trust point), and an authorization can race at
   `/settle`/deliver. Mitigate with **service-layer idempotency keyed on the EIP-3009
   nonce** (dedup *before* running the workflow); treat self-hosted-vs-hosted as a
   security decision, not an open question, if censorship-resistance is claimed.
4. **Buyer-IP leakage (medium).** The `artifactCID` is **public onchain** → encrypt
   artifacts, deliver the key via the minted UCAN; minimize onchain metadata (commit
   to `buyer` rather than the raw wallet + `budgetSpent`). The operator also sees
   plaintext prompt/code — unavoidable without TEE (loops back to the receipt).
5. **Identity-bridge forgery (medium).** Bind the minted credential 1:1 to the settled
   nonce; expire on completion (see Identity).
6. **Pricing griefing (medium).** `f(budget)` on non-deterministic work: a min-tier
   buyer can force max budget consumption (DoS the operator's margin). Price for
   variance; the compute budget alone doesn't bound the dollar outcome.

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
