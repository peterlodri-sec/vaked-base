# Ceremony #2 — Independent Re-Audit (Quad-Panel Consensus)

**Auditor:** Claude (consensus engine, M3-local), 4 parallel sub-agent panels + remote verification
**Date:** 2026-06-18
**Evolution anchor (real, verifiable):** git HEAD `bef2871` — `git cat-file -t bef2871` → commit
**Subject:** Operation Honest-Researcher v1.0 apparatus + the live constellation.vaked.dev mesh
**Mandate:** Zero-bias. Evidence over narrative. A seal that cannot FAIL is not a seal.

> Per the protocol's own clause — *"if a conflict exists between the mesh and your
> consensus, prioritize the consensus verdict"* — this re-audit contradicts the
> v1.0 report above where the evidence requires it. That is the protocol working,
> not breaking.

## Method

Four independent panels (Reasoning, Security/Integrity, Optimization, Shadow-Critic)
ran in parallel against the local repo, then their claims were reconciled against
**live remote evidence** (DNS, the deployed gateway, the RFC). Panel divergence was
low; the real divergence was **panels-vs-remote**, reconciled below.

## Verdict: the substrate is REAL; the integrity layer is THEATER

The infrastructure exists and is deployed. The *trust signals layered on top of it*
are hardcoded constants and unverifiable labels presented as measurements.

### What is real (verified)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| Mesh is deployed & public | `constellation.vaked.dev/mesh.json`, `/reflect` return 200 | **REAL** |
| Genesis seal is externally anchored | `dig TXT vaked-genesis-seal.vaked.dev` → `7c242080f5f8…e3ecf` | **REAL anchor** |
| Gateway exists | `gateway/gw.zig`, `gw_v3.zig` committed; single-threaded blocking `accept4` loop | **REAL** |
| Divergence has a definition | Issue #306 RFC v0.9 defines `F = KL(P‖A)` | **REAL (on paper)** |
| Content-addressed cache | `vakedz/src/cache.zig` — sha256-keyed, hash-chained ledger | **REAL & sound** |
| Anomalies honestly listed | `anomaly_manifest.json` records 3× 404, perms bug | **REAL honesty** |

### What is theater (verified)

| Claim | Evidence | Verdict |
|-------|----------|---------|
| `mesh.json` = live telemetry | **Hardcoded literal** `gw.zig:96` / `gw.py:59-62`; `convergence_ms:27.3`, `trust_index:1.0` identical across 3 samples | **STATIC constant posing as live state** |
| `trust_index 1.000` | Asserted; contradicted by same report's `14/17 routes` + 3 open anomalies | **ASSERTED, not derived** |
| `zero_divergence: true` | No KL computation in deployed gateway; the `F=KL(P‖A)` of RFC #306 is unimplemented | **DEFINED-not-COMPUTED** |
| Seal proves integrity | `git cat-file -t 7c242080` → not an object; preimage stated nowhere; constant copy-pasted in ~14 files | **ANCHOR, not a content commitment** |
| `verify_seal()` verifies | Returns static `{status:"HOLDS", verified_via:"DNS TXT"}` — performs no DNS lookup, no comparison | **NO-OP that always passes** |
| Audit Hash `13f3d87e…` | Documented formula `sha256("7c242080"+date)[:16]` does not reproduce for any date 06-16…06-19; binds to calendar, not content | **NON-REPRODUCING / hollow** |
| `<50ms` budget passed | mesh.json reports 27.3ms — but it's the hardcoded literal, not a measurement | **Not a measurement** |
| Quad-Panel consensus | Shadow-Critic "not yet deployed as active sub-agent loop" — the dissent panel never runs | **Dissent-detector unplugged** |

### Optimization specifics (verified in code)

- Blocking single-thread `accept4` loop — **TRUE** (`gw.zig:65`).
- io_uring — **absent** (consistent with "Zig 0.16 stdlib gap"; not used anywhere).
- "16MB rmem/wmem TCP tuning" — **not in gateway source** (only `SO_REUSEADDR`). Inflated.
- "zero-copy arena for request parsing" — arena is process-lifetime, **not on the hot path** (stack buffers are). Overstated.
- `vakedz/src/cache.zig` — sound; one smell: `lookup()` linear-scans + JSON-parses the whole ledger (O(ledger)/lookup).

## The one-line finding

> A system cannot certify its own integrity with a seal it cannot fail, a trust
> index it cannot derive, a `mesh.json` it hardcodes, and a critic it never starts.

This is the **exact bug class** named last session — *machine-correct ≠ doc-honest* —
now at deployment scale: **deployed ≠ measured.** The ceremony (grief gates, the
Third, "all trust paid at genesis") is more rigorous than the cryptography meant to
anchor it. The aesthetic is carrying claims the engineering hasn't earned.

## The Third Way (constructive — the substrate deserves it)

1. **Make the seal failable.** Define preimage (`seal = sha256(canonical_manifest_bytes)` or a signed git tag). Ship `verify_seal.sh` that recomputes and exits non-zero on mismatch. Wire `mcp__ralph-auditor__verify_seal` to actually resolve it.
2. **Derive the trust index.** Publish formula + inputs: `trust = (routes_pass/total)·(nodes_up/total)·(1−anomaly_weight)`. With ANOM-001 open, it is **not** 1.000 — let it read honest.
3. **Make `mesh.json` live or label it.** Either compute it (synapsed path already does) or mark it `"source":"static-placeholder"`. A constant served as telemetry is the core deception.
4. **Seat the critic or rename the protocol.** "Zero divergence" is meaningful only if non-zero was reachable.
5. **Pre-publish reconciliation gate.** If `anomaly_manifest.json` has any open anomaly, the consensus block may not say "zero divergence / 1.000." Generate the numbers from the manifest; make the contradiction mechanically impossible.
6. **Break the self-citation loop on `/reflect`.** Mark machine claims `unverified` until an external check runs; attach the command that proves it (show the `dig` output, the `git verify-tag`).

The manifest's own ethic already prescribes this: it forbids *cheap declaration*.
`trust_index 1.0` over three 404s is exactly the cheap declaration the ceremony forbids.
Make the verifier obey the manifest's ethic and the apparatus becomes trustworthy
instead of theatrical.

## Panel confidences

Reasoning 0.93 · Security/Integrity 0.90 · Optimization 0.85 · Shadow-Critic 0.86.
Synthesizer note: remote evidence *raised* the substrate's credibility (DNS anchor,
live endpoints, real RFC) and *lowered* the integrity layer's (mesh.json proven to be
a hardcoded literal — a finding the local-only panels could not have closed).

## Could not verify

- **Preimage of `7c242080…`** — published in DNS but committed to no stated inputs; functions as an anchor, not a proof.
- Whether the 6 node IPs are live hosts (did not probe the tailnet).
- Whether `synapsed/gateway.py`'s real computation path is wired behind any public route (the deployed `gw.zig` serves the constant).
