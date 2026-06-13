# `vakedos` — Vultr bare-metal AMD EPYC base host

> Nix materializes. This is the substrate.

`vakedos` is the NixOS **base host** for a Vultr bare-metal **AMD EPYC, 196 GB
ECC** box. It is the *materialization target*: the clean, well-tuned OS that a
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

## Hard constraint: Vultr bare metal is **Legacy BIOS only**

Vultr bare metal does **not** support EFI. Everything here is GRUB + a 1 MiB
`EF02` BIOS-boot partition per disk. When provisioning, choose a **Legacy /
PCBIOS** image — not EFI.

## Install — `nixos-anywhere` + `disko`

This installs remotely over SSH: it kexecs the target into a NixOS installer,
partitions via `disko.nix`, and installs `nixosConfigurations.vakedos`. The
target needs **≥ 2 GB RAM** (the 196 GB box is fine) and **root SSH access**.

### 1. Provision the box
Rent the Vultr bare-metal EPYC. Boot Vultr's default Linux (or rescue) with a
**Legacy/PCBIOS** image and confirm you can `ssh root@<IP>`.

### 2. Fill in the placeholders
Three things must be edited before installing:

- **Disk IDs** — find the stable device paths:
  ```sh
  ssh root@<IP> 'ls -l /dev/disk/by-id'
  ```
  Put the two `/dev/disk/by-id/...` names into **both** `disko.nix` (`device`)
  **and** `configuration.nix` (`boot.loader.grub.devices`). Never use `/dev/sdX`.

- **`networking.hostId`** — generate a unique 8-hex-digit id (required by ZFS):
  ```sh
  head -c4 /dev/urandom | od -A none -t x4
  ```
  Put it in `configuration.nix` (`networking.hostId`).

- **SSH public key** — replace every `REPLACE-WITH-YOUR-SSH-PUBLIC-KEY` in
  `configuration.nix` with your real `ssh-ed25519 ...` key.

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
  --flake .#vakedos root@<IP>
```
This wipes the target disks, lays out the ZFS mirror, and installs. The box
reboots into `vakedos` when done.

### 5. Verify (on the box)
```sh
zpool status rpool            # mirror ONLINE, 0 errors
free -g                       # ~196 GB
nproc                         # full EPYC core count
ras-mc-ctl --status           # ECC monitoring live (also: journalctl -u rasdaemon)
systemctl status sshd         # up, key-only login works
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
