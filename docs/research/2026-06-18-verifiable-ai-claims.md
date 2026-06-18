---
title: Making Swarm Claims Verifiable, Not Asserted — a mapping to Vaked
date: 2026-06-18
provenance: deep-research workflow (13 agents); cited; [UNVERIFIED] tags preserved
relates: eventd/ ; RFC 0004 (multi-agent) ; RFC 0007 (PQ-sealed image) ; rfc-v0.9-quorum-sensing
---

## The structural gap
Every Vaked mechanism today proves **integrity of a record** — "this transcript byte-string
was committed at this chain position and hasn't been altered" (`eventd` sha256 chain;
content-addressed sealed images + ML-DSA `provenance.json`, RFC 0007; per-step `StepHash`
anchors, RFC 0004). **None proves honesty of the computation** — "this output is what the
declared model/prompt/decoding params would actually produce." A lying agent can write a
perfectly chained, perfectly signed entry containing a fabricated result. Closing that
second gap is the task.

## Technique → Vaked mapping

1. **Append-only transcripts — HAVE; extend with an external witness.** `eventd` is a strong
   instance, but it is operator-held: nothing stops the operator rewriting from genesis and
   re-signing. **Add:** periodically anchor the `eventd` tail hash to an external witness
   (Rekor public instance / `omniwitness` / Trillian). Cheapest high-leverage add — converts
   "trust our log" into "anyone can catch our log lying." (https://docs.sigstore.dev/logging/overview/)
   [UNVERIFIED whether Rekor accepts arbitrary non-software manifest schemas out of the box.]
2. **Content-addressed logging — HAVE.** Validated pattern: keep only hashes/Merkle-roots/
   scores/signatures in the authoritative ledger; push raw transcripts/datasets/weights
   off-chain by content hash (O(1) on-ledger commitment, O(log M) Merkle-proof verify).
   Consider FG-Trac's DATA/MODEL/PROOF three-root structure. (https://arxiv.org/abs/2604.18614, https://arxiv.org/abs/2601.14971)
3. **Reproducible evaluation — PARTIAL; highest-value "honest" add.** HadAgent blueprint:
   a `PROOF`-kind `eventd` payload `(model_hash, prompt_hash, decoding_params, dataset_hash,
   output_hash, score)`; a second agent (or quorum — fits rfc-v0.9-quorum-sensing) recomputes
   a random subset and writes a confirming/refuting entry. Makes a claim peer-reproducible,
   not just self-signed. Trust dynamics: fast-to-lose (2 fails), slow-to-earn (5).
   (https://arxiv.org/abs/2604.18614)
   **Blocker:** assumes deterministic bit-identical recompute. GPU inference is nondeterministic
   across hardware/CUDA/attention-impl/tensor-parallel — naive SHA256 equality on outputs
   FAILS. `eventd`'s exact-byte chain is right for transcript integrity but cannot be the
   recompute-equality check for LLM outputs across heterogeneous workers. (https://arxiv.org/abs/2501.16007)
4. **Proof-of-honest-compute menu:**
   - **TopLoc** — locality-sensitive hash over top-k activations; detects model/prompt/precision
     swaps, ~258 bytes/32 tokens, verify cheaper than generate, no training. The most adoptable
     nondeterminism-tolerant primitive for a GPU swarm. Limits: misses speculative decoding;
     vulnerable to adversarial "unstable prompt mining"; subtle fine-tunes hard to detect. (https://arxiv.org/abs/2501.16007)
   - **ZKML (zk-SNARK/STARK)** — gold standard, certifies the claimed computation without
     revealing data/weights; high cost/complexity. (https://arxiv.org/abs/2502.18535)

## Bottom line for the honest swarm
The honesty gate shipped this session proves record-integrity (the right floor). The next
honest step is the *external witness* (anchor `eventd`/`SEALS.sha256` tail in Rekor) + a
*proof-of-inference recompute lane* (PROOF entries + quorum recompute, TopLoc for
nondeterminism). That moves swarm metrics from "signed by the claimant" to "reproducible by a peer."
