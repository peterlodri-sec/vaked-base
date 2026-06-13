# `vakedos` — Vultr bare-metal AMD EPYC base host

> Nix materializes. This is the substrate.

`vakedos` is the NixOS **base host** for a Vultr bare-metal **AMD EPYC 4345P**
(Zen 5, 8c/16t @ 3.8 GHz, **128 GB ECC**, 2 × 1.9 TB NVMe). It is the
*materialization target*: the clean, well-tuned OS that a
Vaked runtime's emitted `nixosModules.<runtime>` (the OTP control plane + Zig
enforcement daemons) will later be layered onto — see
[`docs/language/0012-lowering.md`](../../docs/language/0012-lowering.md) §4.3 and
[`docs/runtime/README.md`](../../docs/runtime/README.md).

**Today it wires no runtime daemons** — they are unimplemented stubs. What it
*does* give you now is a reproducible, ZFS-mirrored, ECC-monitored, EPYC-tuned
Nix build host you can deploy and iterate on.

## What's here

| File | Role |
|------|------|
| `configuration.nix` | The host: BIOS/GRUB boot, ZFS, EPYC/ECC tuning, SSH, Nix builder settings, toolchains |
| `disko.nix` | Declarative ZFS-mirror disk layout (2 disks, BIOS-boot + mirrored `rpool`) |

Wired into the repo flake as `nixosConfigurations.vakedos`.

## Tuned to the concept — the membrane substrate

The host is more than a generic builder: it's the substrate the Vaked
**membranes** (`PROJECT_CONTEXT.md`) materialize onto. The daemons that enforce
them are still stubs, so nothing is *wired* — but every kernel/system facility
each membrane needs is present and tuned, so the compiler-emitted
`nixosModules.<runtime>` attaches cleanly later.

| Membrane → daemon | Host facility provided here |
|-------------------|------------------------------|
| `ebpf` / `network` → **agent-guardd** | recent kernel (BPF + BTF/CO-RE), `nftables` backend (composes with cgroup/BPF egress), `bpftool`/`bpftrace`/`libbpf` |
| `process` / `filesystem` → **sandboxd**, **fs-snapshotd** | user namespaces, cgroup-v2 delegation, `overlay` module, raised inotify/pid/fd limits, `wasmtime` (isolation backend, #50) |
| supervision → **agent-supervisord** (OTP) | `DefaultLimitNOFILE` + `nofile` loginLimits, `kernel.pid_max`, `fs.file-max` for the BEAM control plane |
| `ebpf` audit → **eventd**; `memory` → **memoryd** | `/var/lib/vaked` ZFS dataset (checksummed + snapshotted) for the hash-chained audit spine and mined memory plane |
| `surface` / OTel → **otelcol**, surfaces | persistent journald, low-latency CPU governor, BBR/fq for stream + corpora data paths |

ECC integrity is monitored host-wide via `rasdaemon`, and a ZFS pool reservation
keeps the mirror from wedging at 100%.

### Performance profile

- **EPYC P-states**: `amd_pstate=active` + performance EPP.
- **Low-latency / low-jitter**: idle capped to C1 (`processor.max_cstate=1`) and
  the NMI watchdog dropped. Trade-off: shallower C-states can *lower* peak
  single-core turbo (less power ceded by idle cores) — determinism over boost.
- **Global `-march`**: `nixpkgs.hostPlatform` rebuilds the whole closure for the
  host CPU. Set to **`znver4`** — the 4345P is Zen 5, so this unlocks AVX-512 + Zen
  tuning while staying within what every recent GCC accepts. Bump `vakedCpuArch`
  to **`znver5`** only if the stdenv GCC is ≥ 14 (older GCC rejects the string and
  the build fails). The rebuild bypasses the binary cache and, on 8 cores, the
  first build is long — use `--build-on-remote` (below).

## Hard constraint: Vultr bare metal is **Legacy BIOS only**

Vultr bare metal does **not** support EFI. Everything here is GRUB + a 1 MiB
`EF02` BIOS-boot partition per disk. When provisioning, choose a **Legacy /
PCBIOS** image — not EFI.

## Install — `nixos-anywhere` + `disko`

This installs remotely over SSH: it kexecs the target into a NixOS installer,
partitions via `disko.nix`, and installs `nixosConfigurations.vakedos`. The
target needs **≥ 2 GB RAM** (the 128 GB box is fine) and **root SSH access**.

### 1. Provision the box
Rent the Vultr bare-metal EPYC. Boot Vultr's default Linux (or rescue) with a
**Legacy/PCBIOS** image and confirm you can `ssh root@<IP>`.

### 2. Fill in the placeholders
These are intentional fill-before-deploy markers (the advisory CI reviewer will
flag them — that's expected). Edit before installing:

- **Disk IDs** — find the stable device paths:
  ```sh
  ssh root@<IP> 'ls -l /dev/disk/by-id'
  ```
  Put the two `/dev/disk/by-id/...` names into **both** `disko.nix` (`device`)
  **and** `configuration.nix` (`boot.loader.grub.devices`). Never use `/dev/sdX`.

- **`networking.hostId`** — generate a unique 8-hex-digit id (required by ZFS;
  the `deadbeef` default must be replaced to avoid pool-import collisions):
  ```sh
  head -c4 /dev/urandom | od -A none -t x4
  ```
  Put it in `configuration.nix` (`networking.hostId`).

- **SSH public key** — replace every `REPLACE-WITH-YOUR-SSH-PUBLIC-KEY` in
  `configuration.nix` with your real `ssh-ed25519 ...` key.

- **`vakedCpuArch`** — already set to `znver4` for the confirmed EPYC 4345P
  (Zen 5). Sanity-check the part and GCC on the box, then optionally bump to
  `znver5`:
  ```sh
  ssh root@<IP> 'lscpu | grep "Model name"'   # expect EPYC 4345P
  gcc --version                               # ≥14 → znver5 is safe to use
  ```

### 3. Dry-build locally first (no hardware needed)
From the repo root:
```sh
nix flake check
nix build .#nixosConfigurations.vakedos.config.system.build.toplevel
```
Optionally boot it in a VM before touching the real box:
```sh
nix run github:nix-community/nixos-anywhere -- \
  --flake .#vakedos --vm-test
```

### 4. Install
```sh
nix run github:nix-community/nixos-anywhere -- \
  --flake .#vakedos --build-on-remote root@<IP>
```
This wipes the target disks, lays out the ZFS mirror, and installs. The box
reboots into `vakedos` when done. `--build-on-remote` makes the EPYC build the
(from-source, global-`-march`) closure itself — faster than your laptop and it
avoids shipping a giant closure over the wire.

### 5. Verify (on the box)
```sh
zpool status rpool            # mirror ONLINE, 0 errors
zfs list                      # /nix /var /home /build /var/lib/vaked present
free -g                       # ~128 GB
nproc                         # 16 (8c/16t)
ras-mc-ctl --status           # ECC monitoring live (also: journalctl -u rasdaemon)
systemctl status sshd         # up, key-only login works
# membrane substrate
bpftool version               # eBPF tooling present (agent-guardd evidence layer)
wasmtime --version            # sandbox wasm isolation backend present
nft list ruleset              # nftables backend active (network membrane)
sysctl net.ipv4.tcp_congestion_control  # = bbr
cat /proc/sys/user/max_user_namespaces  # > 0 (sandbox userns)
# performance profile
lscpu | grep -E "Model name|scaling driver"  # confirm CPU + amd-pstate active
cat /sys/module/processor/parameters/max_cstate 2>/dev/null  # = 1 (low-jitter)
dmesg | grep -i "illegal instruction" || echo "no SIGILL — -march OK"
nix build nixpkgs#hello       # Nix builder healthy (scratch on /build)
sudo reboot                   # comes back up → BIOS/GRUB + mirror boot survive
```

## Day-2: subsequent deploys
Edit the config in this repo, then push the new generation:
```sh
nixos-rebuild switch --flake .#vakedos --target-host root@<IP>
```

## Static networking (only if DHCP doesn't apply)
The host defaults to DHCP on the primary NIC. If your Vultr box needs a static
address, take the IP / gateway / netmask from the Vultr panel and replace the
DHCP default in `configuration.nix` with a `systemd.network.networks` entry, e.g.:
```nix
networking.useDHCP = false;
systemd.network.networks."10-wan" = {
  matchConfig.Name = "en*";
  address = [ "<IP>/<prefix>" ];
  routes = [ { Gateway = "<gateway>"; } ];
  networkConfig.DNS = [ "1.1.1.1" "8.8.8.8" ];
};
```

## Forward pointer: layering the Vaked runtime
Once the runtime daemons (`agent-supervisord`, `agent-guardd`, `sandboxd`, …)
are implemented, compile a runtime with `vakedc lower` and add its emitted
`nixosModules.<runtime>` to this host's `modules` list. At that point the
compiler-emitted `gen/colmena/hive.nix` becomes the deploy loop
(`colmena apply`) — this base host is exactly the node that hive targets.
