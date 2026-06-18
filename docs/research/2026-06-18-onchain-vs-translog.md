---
title: On-chain vs Transparency-log Anchoring for Integrity Seals
date: 2026-06-18
provenance: deep-research workflow (13 agents); cited; [UNVERIFIED] tags preserved
relates: docs/research/2026-06-18-external-anchoring.md ; the Ethereum question
---

**Goal:** make tamper-with-reseal of a committed seal manifest externally detectable.
A signature alone does NOT stop it if the attacker holds the key — you need an
external append-only *witness* so the reseal appears as a second, later, conflicting
record the attacker cannot erase. (https://docs.attest.org/docs/core--concepts/onchain-vs-offchain)

## Ranked

1. **Signed git tag — baseline floor.** Trust the key holder; reseal detectable only
   against a previously distributed hash. Necessary, insufficient alone. (https://git-scm.com/docs/git-tag)
2. **Rekor (Sigstore/cosign) — strongest fit, recommended primary.** Append-only Merkle
   log; verifiers check inclusion+consistency proofs, not key custody. The log witnesses
   the signing event; owners monitor it for their identity → tamper-with-reseal is
   externally detectable *even if the attacker holds a key*. Free public instance
   (`rekor.sigstore.dev`, 99.5% SLO), keyless OIDC, GHA-native, no dev-machine build.
   (https://docs.sigstore.dev/logging/overview/, https://docs.sigstore.dev/cosign/signing/overview/)
   Caveat [UNVERIFIED]: the Rekor identity-monitor is WIP — confirm entry-type coverage
   before relying on auto-alerting vs manual queries.
3. **OpenTimestamps (Bitcoin) — free, trustless existence proof; complementary.** Proves
   "this hash existed before time T" on a permissionless chain, no trusted third party,
   hash computed client-side (manifest stays private), single `ots stamp`. Latency = a
   block confirmation. No identity alerting — a passive proof you check. Good as a second,
   fully-trustless layer under Rekor. (https://opentimestamps.org/)
4. **Ethereum / EAS (on-chain) — only if permissionless public verification is a hard req.**
   On-chain wins ONLY when (a) a smart contract must read/verify the seal, or (b) you need
   consensus-backed availability with NO trusted operator at all. Else a transparency log
   gives the same tamper-evidence without gas/key-custody/block latency. Anchor only the
   hash/Merkle root on-chain, never the body. **vaked-base has no smart-contract consumer,
   so on-chain does not win here today.** (https://docs.attest.org/docs/core--concepts/onchain-vs-offchain, https://attest.org/)

## Don't self-host Trillian/CT
Rekor is built on Trillian; rolling your own reinvents Rekor with far more burden (gRPC +
MySQL + an app-specific "personality"); Trillian is in maintenance mode (→ Tessera/tlog-tiles).
Only self-host (Tessera) if sovereignty forbids the public Rekor instance. (https://github.com/google/trillian)

## Concrete for vaked-base
Adopt now: signed git tag (floor) + cosign→Rekor in CI as the primary, deploy-time anchor
(GHA-native, no dev build, no key custody, free). Layer OpenTimestamps if a fully-trustless
second witness is wanted. Skip Ethereum until a contract actually consumes the seal.
