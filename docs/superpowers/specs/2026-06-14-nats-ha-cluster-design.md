# NATS HA cluster — best-practice, optimized fleet bus (spike design)

## Status

Spike design (2026-06-14). NATS is the **core message bus of vaked** — the
work-queue for `swe_af`, the `crabcc.>` event spine the Sentinel Console renders,
and the transport telemetry/agents ride. Today it is a **single node**
(`crabcc-nats` 100.73.72.35, NATS 2.14.2, JetStream, 1 account, 3 streams,
`ha_assets: 0`, `routes: 0`) — a single point of failure for the whole fleet.
This spike defines the HA, secured, and **performance-optimized** target and a
plan to validate it before cutover. Cost model: [`docs/economy.md`](../../economy.md).

## Goals / non-goals

**Goals:** survive any single-node loss with zero data loss (R3 JetStream,
RAFT quorum 2/3); decentralized JWT auth with per-domain account isolation;
hybrid connectivity (clients over the tailnet, RAFT routes over low-latency
mTLS); leaf nodes so every app box has a local NATS endpoint; full
observability + scheduled backups; a tuned, reproducible (Nix) deployment.

**Non-goals (this spike):** multi-region active/active (single-region cluster —
RAFT wants <~10 ms inter-node); replacing eventd's file-based audit chain
(separate concern); message-schema redesign.

## Decisions (locked via brainstorm)

| Decision | Choice |
|---|---|
| Topology | **3 fresh co-located dedicated nodes** (not reuse of packed cx53) |
| Auth | **Decentralized JWT** via `nsc` (operator -> accounts -> users) |
| Connectivity | **Hybrid** — clients over tailnet (`:4222`), cluster RAFT routes over public IP + **mTLS** (`:6222`) |
| Replication | **R3** streams (one replica per node, anti-affinity) |
| Deploy | **NixOS module** (`services.nats`) via nixos-anywhere/colmena — "Vaked declares, Nix materializes" |

## Architecture

```
                         tailnet (WireGuard, ACL-gated)  :4222  (clients)
   cx53 console ─┐   bench-node ─┐   orchestrator/workers ─┐
                 │               │                          │
            ┌────┴───────────────┴──────────────────────────┴────┐
            │     3-node JetStream cluster  "vaked-nats"          │
            │   nats-1 ── nats-2 ── nats-3   (RAFT, R3)           │
            │   routes :6222 over PUBLIC IP + mTLS (same DC, <1ms)│
            │   leafnodes :7422 (mTLS)  for off-tailnet leaves    │
            └─────────────────────────────────────────────────────┘
                 ▲ leaf (local nats-server, dials out)
   each app box (cx53, bench-node, GCP workers) runs a LEAF node →
   local :4222 endpoint, global subject propagation, survives hub blips
```

### Nodes (sizing — see economy.md for the cost trade)
- **3 × Hetzner CCX13** (2 dedicated vCPU, 8 GB, 80 GB NVMe) in **one location**
  (e.g. `fsn1`). Dedicated vCPU = consistent RAFT latency (no noisy-neighbor
  jitter); 80 GB NVMe >> the bus's small-message footprint. Budget alternative:
  3 × CAX21 (ARM, €7.99) — NATS runs well on ARM; loses dedicated-vCPU latency
  guarantees. Recommendation: **CCX13** for "core of vaked" stability.
- Each node joins the **tailnet** (tag:server) for client reach AND keeps its
  **public IP** for the mTLS RAFT route mesh (same-DC, sub-ms).

### Auth — decentralized JWT (nsc)
- `nsc` operator; **SYS** account (locked down) + per-domain accounts:
  **EVENTS** (`crabcc.>`), **SWE_AF** (`swe.af.>`), **TELEMETRY**, **AGENTS**.
  Cross-account visibility via explicit export/import (e.g. SWE_AF exports
  `swe.af.status.>` -> a CONSOLE import).
- **NATS-based resolver** (`resolver: { type: full, dir: … }`) on the cluster;
  account JWTs pushed with `nsc push`. Users get scoped `.creds` files
  (orchestrator, console, each worker, telemetry exporter).
- Per-account JetStream tiers (`max_memory`, `max_storage`, `max_streams`).

### Connectivity / TLS (hybrid)
- **Clients** (`:4222`) connect over the **tailnet** — WireGuard encrypts
  transport; ACL gates who reaches the nodes; JWT does authz. No client TLS certs
  to manage.
- **Cluster routes** (`:6222`) use **public IPs + mutual TLS** (cert per node) —
  keeps RAFT off the tailnet data path for lowest, most stable quorum latency
  (co-located => sub-ms).
- **Leaf nodes** (`:7422`, mTLS): app boxes run a local `nats-server` in
  leaf-node mode dialing OUT to the cluster — gives each box a local endpoint and
  solves off-tailnet boxes (GCP) via public+mTLS leaf links.

### JetStream + stream conventions
- File store on NVMe, **R3** (replicas=3), `unique_tag` placement so each
  replica lands on a distinct node.
- **SWE_AF_TASKS**: `WorkQueue` retention, R3, `max_age` (e.g. 24h), dedupe
  window (`duplicate_window` 2m), `max_msgs`/`max_bytes` caps. (This is the
  orchestrator's queue from the swe-af-fanout-batch plan — point its `NATS_URL`
  at the cluster + `SWE_AF` creds.)
- **EVENTS** (`crabcc.>`): `Limits`/`Interest` retention, R3, `max_bytes` +
  `max_age`; the console subscribes.
- **status / ephemeral** (`swe.af.status.>`): core NATS pub/sub (no JS) unless
  durable history is wanted — cheapest, lowest latency.

### Optimization (the "highly optimize" mandate)
- **nats-server**: `max_payload` 1 MB (down from 8 MB — smaller buffers, less mem;
  raise only if large frames are real), `write_deadline` 10s, `ping_interval` 2m,
  **`lame_duck_duration` 30s** (graceful drain on rolling deploy => zero-downtime),
  `max_connections` 64k, cluster `pool_size` 3, `no_advertise: true`.
- **JetStream**: `max_file_store` 60 GB/node, `sync_interval 2m` (throughput;
  switch to `always` only if a node can lose unsynced writes on crash — RAFT R3
  already covers single-node loss, so `2m` is the right default), compression on.
- **OS** (NixOS): `nofile` 1M, `net.core.somaxconn` 4096, BBR + `fq`, larger
  `tcp_rmem/wmem`, `vm.swappiness=1`, NVMe `none` scheduler, THP off (latency).
- **Runtime**: `GOMEMLIMIT` ≈ 80% RAM to bound the Go heap; `mlock` off.
- **Placement**: `server_tags` (`az`, `node`) drive replica anti-affinity.

### Observability + backup
- `:8222` monitoring (`/healthz`, `/varz`, `/jsz`) bound to tailnet;
  **prometheus-nats-exporter** per node -> the fleet telemetry stack
  (uptrace/openobserve on cx53).
- **NUI** (one instance, behind tailnet) for human stream/KV/consumer browsing.
- **Backups**: scheduled `nats stream backup` per stream -> the fleet's
  rustfs/minio object store; restore runbook.

### Deployment (Nix)
- A `nats-node` NixOS module (`services.nats` with JetStream + cluster + leaf +
  resolver + the tuning above), parameterized per node (server_name, routes,
  tags). 3 `nixosConfigurations` (or a colmena hive) -> `nixos-anywhere` onto the
  3 Hetzner cloud VMs. Leaf config is a smaller module layered onto the app hosts.
- Secrets (operator/account JWTs, mTLS certs, creds) via the repo's existing
  secret path — never in the Nix store world-readable; use `age`/`sops` or
  systemd `LoadCredential`.

### Migration / cutover
1. Stand up the 3-node cluster in parallel (crabcc-nats stays live).
2. Recreate the 3 existing stream **definitions** on the cluster (current msg
   count is 0 -> no data migration).
3. Repoint clients (`NATS_URL` + creds): console, orchestrator, telemetry,
   agents — one at a time, watch `/jsz`.
4. Decommission single-node `crabcc-nats` (or convert to a 4th leaf).

## Spike validation plan (the empirical part)
- [ ] **Inter-node RTT** between the 3 chosen nodes < 2 ms (ping/`nats bench`); if
      a candidate is cross-region, re-pick — RAFT degrades past ~10 ms.
- [ ] **Throughput/latency bench**: `nats bench` pub/sub + JetStream R3 publish
      (msgs/s, p99 latency) at expected fleet load; record baseline.
- [ ] **Failover drill**: kill one node -> quorum holds, streams stay writable,
      consumers resume; restore -> catches up. Measure recovery time.
- [ ] **Auth isolation**: a SWE_AF user cannot read EVENTS subjects; SYS locked.
- [ ] **Zero-downtime deploy**: rolling `nats-server` restart with lame-duck ->
      no client errors.

## Risks
- 3 small nodes co-located = correlated failure if the whole DC drops (accepted;
  multi-region is a non-goal). Backups to object store mitigate data loss.
- JWT/nsc adds operational surface (resolver, JWT pushes) — document the runbook;
  keep operator key offline.
- Leaf nodes on app boxes add a local daemon to maintain — keep the leaf config
  minimal; it's optional per box.
