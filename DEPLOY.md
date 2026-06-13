# Deploying Vaked — the `vakedos` bare-metal host

> Vaked declares. **Nix materializes.** This is the materialize step.

This is the canonical deployment guide for **`vakedos`**, the NixOS bare-metal
host defined by `nixosConfigurations.vakedos` ([`flake.nix`](flake.nix)) and
[`hosts/vakedos/`](hosts/vakedos/). It is the *materialization target*: the
clean, tuned OS that a Vaked runtime's compiler-emitted `nixosModules.<runtime>`
(the OTP control plane + Zig enforcement daemons) is layered onto later
([`docs/language/0012-lowering.md`](docs/language/0012-lowering.md) §4.3). The
runtime daemons are still stubs ([`docs/runtime/README.md`](docs/runtime/README.md)),
so this host wires none of them — it provisions and tunes the substrate.

Host-internal details: [`hosts/vakedos/README.md`](hosts/vakedos/README.md).

---

## Target hardware

Validated against the Vultr bare-metal **AMD EPYC 4345P** plan:

| Component | Spec |
|---|---|
| CPU | EPYC 4345P — Zen 5, 8 cores / 16 threads @ 3.8 GHz (AVX-512) |
| RAM | 128 GB ECC |
| Disk | 2 × 1.9 TB NVMe (→ ZFS mirror) |
| Net | 25 Gbps |

> **Hard constraint — no EFI.** Vultr bare metal is **Legacy/PCBIOS only**. The
> config boots via GRUB + a 1 MiB `EF02` BIOS-boot partition on each mirror disk.
> Choose a **Legacy/PCBIOS** image when provisioning — never EFI.

Other EPYC parts work; adjust `vakedCpuArch`, the ARC cap, and the build
parallelism (below) to the core count / RAM.

---

## Prerequisites

- A machine with **Nix** (flakes enabled) to drive the install — your laptop, or
  the target itself.
- **Root SSH** to the freshly-provisioned box (`nixos-anywhere` kexecs it into an
  installer; needs ≥ 2 GB RAM — fine here).
- Your **SSH public key**.

---

## Install — `nixos-anywhere` + `disko`

### 1. Provision
Rent the Vultr bare-metal EPYC with a **Legacy/PCBIOS** image. Confirm
`ssh root@<IP>` works.

### 2. Fill the placeholders
These are intentional fill-before-deploy markers (the advisory CI reviewer flags
them — expected):

| What | Where | How |
|------|-------|-----|
| Disk IDs (×2) | `disko.nix` **and** `configuration.nix` (`boot.loader.grub.devices`) | `ssh root@<IP> ls -l /dev/disk/by-id` — use the `/dev/disk/by-id/...` names, never `/dev/sdX` |
| `networking.hostId` | `configuration.nix` | `head -c4 /dev/urandom \| od -A none -t x4` (replace `deadbeef`) |
| SSH key | `configuration.nix` (root + `vaked` user) | your real `ssh-ed25519 ...` |
| `vakedCpuArch` | `configuration.nix` | already `znver4`; see [Performance tuning](#performance-tuning) to use `znver5` |

### 3. Dry-build first (no hardware)
```sh
nix flake check
nix build .#nixosConfigurations.vakedos.config.system.build.toplevel
# optional: boot it in a VM before touching the box
nix run github:nix-community/nixos-anywhere -- --flake .#vakedos --vm-test
```

### 4. Install
```sh
nix run github:nix-community/nixos-anywhere -- \
  --flake .#vakedos --build-on-remote root@<IP>
```
`--build-on-remote` makes the EPYC build the (from-source, global-`-march`)
closure itself. This wipes the disks, lays out the ZFS mirror, installs, and
reboots into `vakedos`.

### 5. Verify
```sh
zpool status rpool            # mirror ONLINE, 0 errors
zfs list                      # /nix /var /home /build /var/lib/vaked present
free -g                       # ~128 GB    (+ zram swap)
nproc                         # 16 (8c/16t)
lscpu | grep -E "Model name|scaling driver"   # EPYC 4345P + amd-pstate
ras-mc-ctl --status           # ECC monitoring live
systemctl status sshd irqbalance               # up
bpftool version; wasmtime --version; nft list ruleset   # membrane substrate
dmesg | grep -qi "illegal instruction" && echo "SIGILL — wrong -march!" || echo "no SIGILL — -march OK"
nix build nixpkgs#hello       # builder healthy (scratch on /build)
sudo reboot                   # survives → BIOS/GRUB + mirror boot OK
```

---

## Performance tuning

Applied defaults and the knobs to turn. All live in
[`hosts/vakedos/configuration.nix`](hosts/vakedos/configuration.nix) /
[`disko.nix`](hosts/vakedos/disko.nix).

### CPU & latency
- `amd_pstate=active` + `cpuFreqGovernor = "performance"` (EPP performance).
- **Low-jitter**: `processor.max_cstate=1`, `nmi_watchdog=0`. *Trade-off:*
  shallower C-states give less power back to idle cores, so peak single-core
  turbo can be lower — chosen: determinism over absolute boost.
- For hard isolation later, reserve cores for the daemons with
  `isolcpus=`/`nohz_full=`/`rcu_nocbs=` once the core layout is known.
- **`mitigations` stay ON** — this is a security host. `mitigations=off` buys
  ~5–30% on syscall-heavy work but defeats the point; revisit only if the box is
  single-tenant + fully trusted.
- NUMA: the 4345P is a single node — nothing to pin across nodes.

### Microarchitecture (`vakedCpuArch`)
| Value | When |
|-------|------|
| `znver4` (default) | Zen 5 box, any recent GCC — AVX-512 + Zen tuning, safe |
| `znver5` | only if `gcc --version` ≥ 14 (older GCC rejects the arch → build fails) |
| `x86-64-v3` | conservative fallback (works on every EPYC, no AVX-512) |
| per-package | see below — cheaper on small boxes |

**Global vs per-package — the big economic call.** Global `-march`
(`nixpkgs.hostPlatform`) rebuilds the *entire* closure from source: **zero
binary-cache hits**, and every `nixos-rebuild` that bumps nixpkgs re-bootstraps
the world. On 8 cores that's hours each time. If that tax isn't worth it, drop
`nixpkgs.hostPlatform` and instead compile only the perf-critical daemons with
`-march=znver4` via per-package overrides — ~95% of the benefit, and you keep
`cache.nixos.org` for everything else.

### Build parallelism
`max-jobs = "auto"` (16) × `cores = 2` ≈ 32 threads. `cores = 0` ("all cores",
*not* 1) × 16 jobs ≈ 256 concurrent compilers, which risks OOM on 128 GB during
the from-source rebuild. Alternatives: `max-jobs=4; cores=4` (fewer, bigger
builds) or `cores=0` (whole box, once you trust headroom).

### Storage (ZFS on NVMe)
- ARC capped at **32 GiB** (`zfs.zfs_arc_max`) — leave RAM for builds/agents.
- `/build` scratch: `sync=disabled` + `lz4` + `recordsize=1M` (throwaway → fast).
- `auto-optimise-store` (hard-link dedup), weekly `autoScrub`, `trim` for NVMe.
- A `reserved` dataset (10 GiB reservation) keeps the pool off 100% (a full ZFS
  pool wedges writes).

### Network (25 Gbps)
BBR + `fq`, 128 MiB socket buffers (`rmem_max`/`wmem_max`/`tcp_rmem`/`tcp_wmem`),
`netdev_max_backlog=32768`, and `irqbalance` to spread NVMe/NIC IRQs.

### Resilience
`zramSwap` (zstd, ≈32 GiB) as a compressed-RAM OOM net during builds (no disk
swap; swap-on-zvol is deadlock-prone with ZFS).

---

## Day-2 operations

```sh
# deploy a config change from this repo
nixos-rebuild switch --flake .#vakedos --target-host root@<IP>

zpool status rpool          # health; scrub runs weekly automatically
nix-collect-garbage         # GC also runs weekly (--delete-older-than 30d)
ras-mc-ctl --errors         # ECC error history
```

**Rollback.** Every change here is reversible — NixOS keeps prior generations.
Revert a bad tuning change with `nixos-rebuild switch --rollback` (or pick an
earlier generation from the GRUB menu at boot). Kernel-param / `-march` changes
only take effect after a rebuild+reboot, so validate them with `--vm-test`
(above) before switching the live host.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Won't boot after install | Used an EFI image — reprovision **Legacy/PCBIOS**; check both `grub.devices` are correct by-id paths |
| `pool rpool ... another system` on import | `hostId` not regenerated — set a unique 8-hex `networking.hostId` |
| `SIGILL` / "illegal instruction" | `vakedCpuArch` too new for the CPU — drop to `znver4`/`x86-64-v3` |
| Build fails: unknown `-march` | stdenv GCC < 14 with `znver5` — use `znver4` |
| OOM during install/build | lower `cores`, or `max-jobs`; zram should absorb spikes |
| Locked out | SSH key placeholder not replaced before install |

---

## Forward pointer — layering the Vaked runtime

Once the runtime daemons (`agent-supervisord`, `agent-guardd`, `sandboxd`, …)
exist, compile a runtime with `vakedc lower`, add its emitted
`nixosModules.<runtime>` to this host's `modules`, and the compiler-emitted
`gen/colmena/hive.nix` becomes the deploy loop (`colmena apply`) — this base host
is exactly the node that hive targets.
