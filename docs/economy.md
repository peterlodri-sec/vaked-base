# economy.md — fleet cost model

Living cost ledger for vaked fleet infrastructure decisions. Each section: the
spend, the alternatives, and the cost-vs-benefit. Prices are **ex-VAT**, captured
2026-06-14 (Hetzner post-April-2026 pricing; verify at the source before
purchase). Sources: [Hetzner Cloud pricing](https://www.hetzner.com/cloud/),
[bitdoze Hetzner 2026](https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/),
[Synadia Cloud pricing](https://docs.synadia.com/cloud/pricing).

---

## 1. NATS HA cluster (3-node JetStream)

Design: [`docs/superpowers/specs/2026-06-14-nats-ha-cluster-design.md`](superpowers/specs/2026-06-14-nats-ha-cluster-design.md).
Decision: move the core vaked bus from a single node (`crabcc-nats`, a SPOF) to a
3-node co-located JetStream cluster (R3, RAFT quorum 2/3).

### Candidate node specs + price (Hetzner, EUR/mo, ex-VAT)

| Plan | vCPU | RAM | NVMe | Traffic | €/mo/node |
|---|---|---|---|---|---|
| **CCX13** (dedicated) | 2 | 8 GB | 80 GB | 20 TB | **12.49** |
| CAX21 (ARM) | 4 | 8 GB | 80 GB | 20 TB | 7.99 |
| CCX23 (dedicated) | 4 | 16 GB | 160 GB | 20 TB | 24.49 |
| CAX31 (ARM) | 8 | 16 GB | 160 GB | 20 TB | 15.99 |

+ IPv4 ≈ €0.50/mo/node (or run IPv6-only + tailnet to avoid; verify).

### 3-node cluster totals

| Option | Nodes | Compute €/mo | +IPv4 | **Total €/mo** | €/yr |
|---|---|---|---|---|---|
| **Recommended — CCX13 ×3** | 2c/8GB ded | 37.47 | 1.50 | **≈ 39** | ≈ 468 |
| Budget — CAX21 ×3 (ARM) | 4c/8GB | 23.97 | 1.50 | ≈ 25 | ≈ 306 |
| Headroom — CCX23 ×3 | 4c/16GB ded | 73.47 | 1.50 | ≈ 75 | ≈ 900 |

No load balancer needed (NATS clients fail over across the node list) -> €0.
Backups reuse the fleet's existing rustfs/minio -> €0 extra. Inter-node + client
traffic is tiny vs the 20 TB/node included -> €0 overage expected.

### Additional cost (vs today)

Today `crabcc-nats` is one small node (already paid; ~€6-8/mo class).

- **If the 3 fresh nodes replace crabcc-nats:** net additional ≈ **€33/mo**
  (€39 − ~€6) ≈ €400/yr.
- **If crabcc-nats is kept** (e.g. as a 4th leaf): additional = **€39/mo**.

Hetzner bills **hourly (capped monthly)**, so the spike can stand up all 3 nodes,
run the validation plan over a few days, and destroy them — **validation cost ≈
€1.3/day for the trio**. Commit to the monthly spend only after the failover +
throughput drills pass.

### Alternative: managed (Synadia Cloud)

| Tier | $/mo | HA streams | Storage | Transfer | Fit |
|---|---|---|---|---|---|
| Personal | 0 | 0 | 5 GiB | 10 GiB | too small |
| Starter | 49 | 2 | 1 GiB | 100 GiB | **inadequate** (vaked needs >2 HA streams) |
| Pro | 199 | 10 | 10 GiB | 1 TiB | works, pricey |

Self-hosted CCX13 ×3 (**€39/mo ≈ $42**) gives **unlimited streams, 240 GB NVMe,
60 TB traffic, full control** — roughly the Pro tier's capability at ~1/5 the
price, and ~the same price as the *inadequate* Starter tier. The team already
runs Hetzner + NixOS, so operational marginal cost is low. **Self-host wins.**

### Cost vs benefit

- **Spend:** ~€33-39/mo (~€400-470/yr) to go from 1 node to 3-node R3 HA.
- **What it removes:** the **single point of failure for the entire vaked bus.**
  Every agent, the `swe_af` work-queue, the paid Sentinel Console's live feed,
  and telemetry ride this bus. Today a single disk/host failure on `crabcc-nats`
  = **full fleet bus outage + potential JetStream data loss** (the 25 GB store
  lives on one disk).
- **What it buys:** survive any one node loss with **zero data loss** (R3 +
  quorum), **zero-downtime rolling deploys** (lame-duck drain), account-isolated
  multi-tenancy, and headroom.
- **Verdict:** for a component explicitly designated "core of vaked," ~€39/mo to
  eliminate a fleet-wide SPOF is trivial against the blast radius (a bus outage
  cascades to every agent and the paid product). **Proceed — recommended CCX13
  ×3**, drop to CAX21 ×3 only if the ~€14/mo saving matters more than dedicated
  -vCPU RAFT-latency stability.

### Open cost items to confirm before purchase
- Exact IPv4 surcharge (or go IPv6-only + tailnet -> €0).
- Whether `crabcc-nats` is retired (−its cost) or kept as a leaf.
- Chosen location (all 3 in ONE location for RAFT latency).
