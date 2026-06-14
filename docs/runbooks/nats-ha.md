# Runbook — NATS HA cluster bring-up

Ties together the artifacts under `scripts/nats/` and `nix/nats/`. Plan:
`docs/superpowers/plans/2026-06-14-nats-ha-cluster.md`. Spec:
`docs/superpowers/specs/2026-06-14-nats-ha-cluster-design.md`.

## Order of operations

1. **[OPERATOR] Provision** — `HCLOUD_TOKEN=… scripts/nats/provision.sh`. Record
   the 3 public IPs into `nix/nats/hosts/nats-{1,2,3}.nix` (`REPLACE_IP_*`).
2. **PKI** — `scripts/nats/mtls-ca.sh ./nats-pki nats-1=<ip1> nats-2=<ip2> nats-3=<ip3>`.
3. **JWT** — `scripts/nats/nsc-bootstrap.sh` → `nsc/`, `creds/*.creds`,
   `nats-resolver.conf`. Assemble each node's `auth.conf` =
   operator JWT + `system_account: <SYS id>` + the resolver block. Keep the
   operator key OFFLINE.
4. **[OPERATOR] Deploy** — for each node: ship `nats-pki/*` → `certDir`
   (`/var/lib/nats/pki`) and `auth.conf` as a deploy secret (age/sops or
   systemd `LoadCredential`), then
   `nixos-anywhere --flake .#nats-N root@<ipN>`. Verify `systemctl status nats`,
   `curl localhost:8222/healthz`.
5. **[OPERATOR] Tailnet** — on each node `tailscale up --advertise-tags=tag:server`;
   approve. Confirm clients reach `:4222` over the tailnet.
6. **Cluster check** — `nats --server nats://<ip1>:4222 --creds creds/SWE_AF-orchestrator.creds server list` → 3 nodes.
7. **Streams** — `NATS_URL=… scripts/nats/streams.sh` (SWE_AF_TASKS work-queue R3, EVENTS).
8. **Monitoring/backup** — deploy prometheus-nats-exporter scrape → cx53 telemetry;
   one NUI instance (tailnet); install `scripts/nats/backup.sh` on a timer.
9. **Validate** — `NATS_URL=… CREDS=… scripts/nats/validate.sh nats-1.vaked.internal nats-2.vaked.internal nats-3.vaked.internal`.
   Record RTT, throughput, failover recovery time below.

## Migration / cutover (from single-node crabcc-nats)

- Recreate the 3 existing stream definitions on the cluster (msg count 0 → no data move).
- Repoint clients one at a time (`NATS_URL` = 3-node list + the right `.creds`):
  - Sentinel Console → `creds/EVENTS-console.creds`
  - swe-af orchestrator (PR #188) → `NATS_URL`/`NATS_CREDS` = `creds/SWE_AF-orchestrator.creds`
  - telemetry exporter → `creds/TELEMETRY-exporter.creds`
- Retire `crabcc-nats` (or convert to a 4th leaf via `nix/nats/nats-leaf.nix`).

## Cross-account share (open item)

`swe.af.status.>` lives in SWE_AF but the console reads via EVENTS. Add the export
on SWE_AF and the import on EVENTS with `nsc add export` / `nsc add import`
(verify flags for your nsc version), then `nsc push` to the resolver.

## Recorded baselines (fill after validate.sh)

- Inter-node RTT: …
- JetStream R3 publish throughput / p99: …
- Failover recovery time (1 node down → writable): …
