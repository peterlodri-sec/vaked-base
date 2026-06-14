# NATS HA cluster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`). Steps tagged **[OPERATOR]** need live credentials / spend / interactive auth and are run by the human; everything else is authorable + statically checkable offline.

**Goal:** Replace the single-node `crabcc-nats` SPOF with a 3-node JetStream cluster (R3/RAFT), decentralized JWT auth (nsc), hybrid connectivity (tailnet clients + mTLS RAFT routes), leaf nodes, monitoring, backups — deployed reproducibly via NixOS.

**Architecture:** 3 × Hetzner CCX13 in one location. Each runs `nats-server` (JetStream cluster member + leaf hub + JWT resolver) declared via a NixOS `services.nats.settings` module and applied with nixos-anywhere. Clients reach `:4222` over the tailnet; RAFT routes `:6222` run over public IPs + mutual TLS; leaf nodes connect `:7422` mTLS. See design: `docs/superpowers/specs/2026-06-14-nats-ha-cluster-design.md`; cost: `docs/economy.md`.

**Tech Stack:** NixOS 26.05, nats-server 2.14.x, `nsc` (JWT), `nats` CLI, Hetzner Cloud (`hcloud`), internal mTLS CA (`step-cli`), nixos-anywhere, prometheus-nats-exporter, NUI.

**Repo layout for artifacts:**
```
nix/nats/
├── nats-node.nix          # the reusable nats-server module (cluster member)
├── nats-leaf.nix          # smaller leaf-node module for app hosts
├── hosts/{nats-1,nats-2,nats-3}.nix   # per-node params (name, routes, tags)
scripts/nats/
├── provision.sh           # [OPERATOR] hcloud create 3x CCX13
├── nsc-bootstrap.sh       # operator/accounts/users/creds + resolver config
├── mtls-ca.sh             # internal CA + per-node route/leaf certs
├── streams.sh             # create SWE_AF_TASKS / EVENTS / ... via nats CLI
├── backup.sh              # nats stream backup -> minio (timer)
└── validate.sh            # RTT / failover / throughput / auth-isolation drills
docs/runbooks/nats-ha.md   # the operator runbook tying it together
```

---

## Task 1: Internal mTLS CA + per-node certs (`scripts/nats/mtls-ca.sh`)

RAFT routes + leaf links use mutual TLS. A tiny offline CA (step-cli) issues a cert per node (SAN = public IP + `nats-N.vaked.internal`). Tailnet client traffic is encrypted by WireGuard, so client `:4222` does **not** require TLS in v1.

- [ ] **Step 1: Write `mtls-ca.sh`** — creates `ca.crt/ca.key` once (idempotent), then a cert+key per node.

```bash
#!/usr/bin/env bash
set -euo pipefail
OUT=${1:-./nats-pki}; mkdir -p "$OUT"; cd "$OUT"
# root CA (once)
[ -f ca.crt ] || step certificate create "vaked-nats CA" ca.crt ca.key \
  --profile root-ca --no-password --insecure --not-after 87600h
# per-node leaf certs (SANs passed as: name=ip)
for spec in "$@"; do
  case "$spec" in *=*) name=${spec%%=*}; ip=${spec#*=};; *) continue;; esac
  [ -f "$name.crt" ] && continue
  step certificate create "$name" "$name.crt" "$name.key" \
    --profile leaf --ca ca.crt --ca-key ca.key --no-password --insecure \
    --san "$ip" --san "$name.vaked.internal" --not-after 8760h
done
```

- [ ] **Step 2: Static check** — Run: `bash -n scripts/nats/mtls-ca.sh` (syntax) and `shellcheck scripts/nats/mtls-ca.sh`. Expected: no errors.
- [ ] **Step 3: Commit** — `git add scripts/nats/mtls-ca.sh && git commit -m "feat(nats): internal mTLS CA + per-node cert script"`

---

## Task 2: JWT auth bootstrap (`scripts/nats/nsc-bootstrap.sh`)

Decentralized JWT: one operator, a locked-down SYS account, and per-domain accounts (EVENTS, SWE_AF, TELEMETRY, AGENTS) each with a JetStream tier and scoped users. Emits the NATS-resolver preload + creds files.

- [ ] **Step 1: Write `nsc-bootstrap.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
export NSC_HOME=${NSC_HOME:-./nsc}
nsc add operator --name vaked --sys || true
nsc edit operator --service-url nats://nats-1.vaked.internal:4222

# per-domain accounts with JetStream tiers (mem/disk/streams/consumers)
add_acct() { # name  mem  disk  streams  consumers
  nsc add account --name "$1" || true
  nsc edit account --name "$1" \
    --js-mem-storage "$2" --js-disk-storage "$3" \
    --js-streams "$4" --js-consumers "$5"
}
add_acct EVENTS    256M 5G  50  200
add_acct SWE_AF    256M 5G  20  100
add_acct TELEMETRY 256M 10G 50  500
add_acct AGENTS    128M 2G  20  100

# scoped users -> creds (one per consumer)
add_user() { nsc add user --account "$1" --name "$2" || true
  nsc generate creds --account "$1" --name "$2" > "creds/$1-$2.creds"; }
mkdir -p creds
add_user SWE_AF    orchestrator
add_user SWE_AF    enqueue
add_user EVENTS    console
add_user TELEMETRY exporter

# cross-account export: SWE_AF status visible to a CONSOLE consumer in EVENTS
nsc edit account SWE_AF --js-tier ... 2>/dev/null || true
# (export/import of swe.af.status.> SWE_AF->EVENTS: see runbook; nsc add export/import)

# NATS-based resolver config fragment for the server (preload + dir)
nsc generate config --nats-resolver --sys-account SYS > nats-resolver.conf
```

- [ ] **Step 2: Static check** — `bash -n` + `shellcheck`. Document the exact `nsc add export`/`nsc add import` invocations for the `swe.af.status.>` cross-account share in `docs/runbooks/nats-ha.md` (the inline `...` above is filled there with verified flags).
- [ ] **Step 3: Commit** — `feat(nats): nsc JWT bootstrap (operator, accounts, users, resolver)`

---

## Task 3: `nats-node` NixOS module (`nix/nats/nats-node.nix`)

The cluster-member server config, expressed through `services.nats.settings` (the free-form escape hatch that maps 1:1 to the nats-server config — avoids guessing per-option NixOS names). Parameterized by node name, this node's listen IPs, the peer route URLs, and the server tag.

- [ ] **Step 1: Write the module**

```nix
# nix/nats/nats-node.nix
{ name, routes, publicIp, certDir, ... }:
{ config, pkgs, lib, ... }: {
  networking.firewall.allowedTCPPorts = [ 4222 6222 7422 8222 ];
  services.nats = {
    enable = true;
    jetstream = true;
    settings = {
      server_name = name;
      # clients over the tailnet; bind 4222 on all (ACL gates reachability)
      host = "0.0.0.0";
      port = 4222;
      max_payload = 1048576;          # 1 MiB
      write_deadline = "10s";
      ping_interval = "2m";
      lame_duck_duration = "30s";     # zero-downtime rolling restart
      server_tags = [ "az:fsn1" "node:${name}" ];

      jetstream = {
        store_dir = "/var/lib/nats/jetstream";
        max_memory_store = 2 * 1024 * 1024 * 1024;
        max_file_store  = 60 * 1024 * 1024 * 1024;
        sync_interval = "2m";
      };

      cluster = {
        name = "vaked-nats";
        host = publicIp;              # RAFT over public IP
        port = 6222;
        routes = routes;              # [ "nats://nats-2.vaked.internal:6222" ... ]
        pool_size = 3;
        no_advertise = true;
        tls = {                       # mutual TLS on routes
          cert_file = "${certDir}/${name}.crt";
          key_file  = "${certDir}/${name}.key";
          ca_file   = "${certDir}/ca.crt";
          verify_and_map = true;
          timeout = 5;
        };
      };

      leafnodes = {
        port = 7422;
        tls = {
          cert_file = "${certDir}/${name}.crt";
          key_file  = "${certDir}/${name}.key";
          ca_file   = "${certDir}/ca.crt";
          verify = true;
        };
      };

      # decentralized JWT (operator + SYS + nats-resolver); preload from nsc
      include = "auth.conf";          # operator/system_account/resolver, deployed via secrets

      http = "0.0.0.0:8222";          # monitoring (ACL-gated to tailnet)
    };
  };

  # OS tuning
  boot.kernel.sysctl = {
    "net.core.somaxconn" = 4096;
    "net.core.default_qdisc" = "fq";
    "net.ipv4.tcp_congestion_control" = "bbr";
    "vm.swappiness" = 1;
  };
  systemd.services.nats.serviceConfig = {
    LimitNOFILE = 1048576;
    Environment = [ "GOMEMLIMIT=6GiB" ];
  };
}
```

- [ ] **Step 2: Per-node hosts** — write `nix/nats/hosts/nats-{1,2,3}.nix` instantiating the module with each node's `publicIp` + the other two as `routes`.
- [ ] **Step 3: Static check** — `nix-instantiate --parse nix/nats/nats-node.nix` (syntax) and, once a flake target exists, `nix flake check`. Expected: parses. **Note:** verify `services.nats.settings` accepts these keys against the pinned nixpkgs (`nixos-option services.nats.settings` or the module source) — adapt key names if the module wraps any.
- [ ] **Step 4: Commit** — `feat(nats): nats-node NixOS module (cluster, jetstream, leaf, mTLS, tuning)`

---

## Task 4: Provisioning script (`scripts/nats/provision.sh`) [OPERATOR]

- [ ] **Step 1: Write `provision.sh`** (needs `HCLOUD_TOKEN`)

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${HCLOUD_TOKEN:?set HCLOUD_TOKEN}"
LOC=${LOC:-fsn1}; TYPE=${TYPE:-ccx13}; IMAGE=${IMAGE:-debian-12}
for n in nats-1 nats-2 nats-3; do
  hcloud server create --name "$n" --type "$TYPE" --image "$IMAGE" \
    --location "$LOC" --ssh-key "$(hcloud ssh-key list -o noheader -o columns=name | head -1)" \
    --label role=nats
done
hcloud server list -l role=nats -o columns=name,ipv4,ipv6,datacenter
```

- [ ] **Step 2: Static check** — `bash -n` + `shellcheck`.
- [ ] **Step 3 [OPERATOR]:** run it; record the 3 public IPs into `nix/nats/hosts/*.nix`.
- [ ] **Step 4: Commit** — `feat(nats): hcloud provisioning script (3x CCX13, one location)`

---

## Task 5: Deploy + tailnet join [OPERATOR]

- [ ] **Step 1:** `mtls-ca.sh nats-1=<ip1> nats-2=<ip2> nats-3=<ip3>` → PKI; `nsc-bootstrap.sh` → JWTs + creds; assemble each node's `auth.conf` (operator JWT + `system_account` + resolver) as a deploy secret (age/sops or `LoadCredential`).
- [ ] **Step 2 [OPERATOR]:** `nixos-anywhere --flake .#nats-1 root@<ip1>` (×3). Verify `systemctl status nats`, `curl localhost:8222/healthz`.
- [ ] **Step 3 [OPERATOR]:** on each node `tailscale up --advertise-tags=tag:server`; approve. Confirm clients reach `:4222` over the tailnet.
- [ ] **Step 4:** verify cluster formed: `nats --server nats://<ip1>:4222 server list` shows 3; `server report jetstream` shows R3 capable. Commit any host-file IP updates.

---

## Task 6: Streams (`scripts/nats/streams.sh`)

- [ ] **Step 1: Write `streams.sh`** (uses the SWE_AF/EVENTS creds)

```bash
#!/usr/bin/env bash
set -euo pipefail
S=${NATS_URL:-nats://nats-1.vaked.internal:4222}
nats --server "$S" --creds creds/SWE_AF-orchestrator.creds stream add SWE_AF_TASKS \
  --subjects 'swe.af.tasks' --retention work --replicas 3 \
  --max-age 24h --dupe-window 2m --storage file --defaults
nats --server "$S" --creds creds/EVENTS-console.creds stream add EVENTS \
  --subjects 'crabcc.>' --retention limits --replicas 3 \
  --max-age 168h --max-bytes 5GB --storage file --defaults
```

- [ ] **Step 2: Static check** — `bash -n` + `shellcheck`.
- [ ] **Step 3 [OPERATOR]:** run against the live cluster; `nats stream report` shows R3.
- [ ] **Step 4: Commit** — `feat(nats): stream provisioning (SWE_AF_TASKS workqueue, EVENTS)`

---

## Task 7: Monitoring + backups

- [ ] **Step 1:** add `prometheus-nats-exporter` to the node module (scrape `:8222`), wire a scrape target into the fleet telemetry stack (uptrace/openobserve on cx53). Deploy one **NUI** instance (tailnet-only) for human browsing.
- [ ] **Step 2: Write `backup.sh`** + a systemd timer: `nats stream backup <name> <dir>` for each stream → push to the fleet rustfs/minio. Document restore.
- [ ] **Step 3: Static check** + **Commit** — `feat(nats): prometheus exporter + NUI + scheduled stream backups`

---

## Task 8: Migration / cutover

- [ ] **Step 1:** recreate the 3 existing crabcc-nats stream **definitions** on the cluster (current msg count 0 → no data migration).
- [ ] **Step 2 [OPERATOR]:** repoint clients one at a time — set `NATS_URL` to the 3-node list + the right `.creds`: the Sentinel Console (EVENTS-console), the swe-af orchestrator (SWE_AF-orchestrator), telemetry (TELEMETRY-exporter), agents. Watch `/jsz` after each.
- [ ] **Step 3 [OPERATOR]:** retire single-node `crabcc-nats` (or convert to a 4th leaf). Update the swe-af-orchestrator env (`NATS_URL`, `NATS_CREDS`) — ties back to PR #188's deploy.
- [ ] **Step 4: Commit** the runbook `docs/runbooks/nats-ha.md`.

---

## Task 9: Validation drills (`scripts/nats/validate.sh`)

- [ ] **Step 1: Write `validate.sh`** covering the spec's validation plan:

```bash
#!/usr/bin/env bash
set -euo pipefail
S=${NATS_URL:?}; C=${CREDS:?}
echo "== inter-node RTT (expect <2ms) =="; for h in "$@"; do ping -c5 "$h" | tail -1; done
echo "== throughput/latency =="; nats --server "$S" --creds "$C" bench bench.test \
  --js --replicas 3 --pub 4 --sub 4 --msgs 100000 --size 256
echo "== failover: kill nats-1, confirm quorum + writable =="  # [OPERATOR] manual
echo "== auth isolation: SWE_AF creds must NOT read crabcc.> =="
nats --server "$S" --creds creds/SWE_AF-orchestrator.creds sub 'crabcc.>' --count 1 --timeout 3s \
  && { echo "FAIL: isolation breach"; exit 1; } || echo "ok: isolation holds"
```

- [ ] **Step 2: Static check** — `bash -n` + `shellcheck`.
- [ ] **Step 3 [OPERATOR]:** run all drills; record baseline numbers + the failover recovery time in `docs/runbooks/nats-ha.md`.
- [ ] **Step 4: Commit** — `feat(nats): validation drills (RTT, throughput, failover, auth isolation)`

---

## Verification (whole feature)
- [ ] All scripts pass `bash -n` + `shellcheck`; Nix files pass `nix-instantiate --parse` / `nix flake check`.
- [ ] [OPERATOR] 3-node cluster up; `server list` = 3; a stream is R3; killing one node keeps it writable (quorum 2/3); rolling restart causes no client errors (lame-duck).
- [ ] [OPERATOR] auth isolation holds (SWE_AF cannot read EVENTS subjects); SYS locked.
- [ ] [OPERATOR] all fleet clients repointed; `crabcc-nats` SPOF retired.

## Open items
- Verify pinned-nixpkgs `services.nats.settings` key acceptance (adapt if wrapped).
- Confirm exact `nsc add export/import` flags for the `swe.af.status.>` cross-account share.
- IPv6-only nodes + tailnet to avoid IPv4 surcharge (economy.md open item).
