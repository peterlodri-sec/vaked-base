# hosts/vakedos/configuration.nix — the vakedos bare-metal base host.
#
# A Vultr bare-metal AMD EPYC box (196 GB ECC) tuned as the *membrane substrate*
# for the Vaked concept: "Nix materializes · OTP supervises · Zig enforces ·
# eBPF testifies." The runtime materializes the Vaked membranes onto a daemon
# roster (docs/runtime/README.md, docs/context/PROJECT_CONTEXT.md); those daemons
# are still stubs, so this host wires none of them — instead it exposes and tunes
# the kernel/system facilities each membrane needs, so the compiler-emitted
# nixosModules.<runtime> can attach cleanly later (docs/language/0012-lowering.md
# §4.3). Boot is Legacy/BIOS GRUB because Vultr bare metal has no EFI.
{ config, lib, pkgs, ... }:

{
  imports = [
    ./disko.nix
  ];

  # === Boot: Legacy BIOS / GRUB on both mirror members ========================
  boot.loader.grub = {
    enable = true;
    efiSupport = false;
    copyKernels = true;
    # Install to both mirror disks so the box still boots if one disk dies.
    # Must match the by-id devices in disko.nix.
    devices = [
      "/dev/disk/by-id/REPLACE-WITH-DISK-1-ID"
      "/dev/disk/by-id/REPLACE-WITH-DISK-2-ID"
    ];
  };

  # Kernel: stay on the NixOS default (a recent LTS) — it is guaranteed
  # ZFS-compatible (pinning linuxPackages_latest can break ZFS-root evaluation)
  # and already ships everything the eBPF testimony/enforcement layer
  # (agent-guardd) needs: BPF + BTF/CO-RE, BPF-LSM, and BPF ring buffers. To ride
  # a newer ZFS-compatible kernel, set
  # boot.kernelPackages = config.boot.zfs.package.latestCompatibleLinuxPackages;

  # === ZFS ===================================================================
  boot.supportedFilesystems = [ "zfs" ];
  boot.zfs.forceImportRoot = false;
  # REQUIRED for ZFS — unique 8 hex digits. Generate on the box with:
  #   head -c4 /dev/urandom | od -A none -t x4
  networking.hostId = "deadbeef";
  services.zfs.autoScrub.enable = true;
  services.zfs.trim.enable = true;

  # === EPYC / bare-metal hardware ===========================================
  hardware.cpu.amd.updateMicrocode = true;
  hardware.enableRedistributableFirmware = true;
  boot.initrd.availableKernelModules = [
    "nvme"
    "ahci"
    "sd_mod"
    "xhci_pci"
    "megaraid_sas" # common LSI/Broadcom HBA on bare metal; harmless if unused
  ];
  # kvm-amd: future sandboxd VM/microVM isolation; overlay: sandbox/snapshot mounts.
  boot.kernelModules = [ "kvm-amd" "overlay" ];

  # ECC reporting — surfaces corrected/uncorrected memory errors (the point of
  # paying for ECC). Inspect with `ras-mc-ctl --status` / `journalctl -u rasdaemon`.
  hardware.rasdaemon.enable = true;

  # Bare metal: favor throughput/latency over power savings — interactive agent
  # runclasses (e.g. runclass.interactive, agentfield-swe.vaked) want low latency.
  powerManagement.cpuFreqGovernor = lib.mkDefault "performance";

  # Cap the ZFS ARC at ~64 GiB and prefer fast network paths. This is a build +
  # runtime host: leave RAM for Nix builds and agent workloads rather than letting
  # ZFS claim ~half of the 196 GB.
  boot.kernelParams = [ "zfs.zfs_arc_max=68719476736" ];

  # === Membrane substrate ====================================================
  # Each block below maps a Vaked runtime membrane (PROJECT_CONTEXT.md) to the
  # host facility its enforcing daemon will use.

  # -- network membrane → agent-guardd: deny-by-default egress + eBPF cgroup maps.
  #    nftables backend composes with cgroup/BPF egress programs the daemon loads.
  networking.nftables.enable = true;

  # -- process + filesystem membranes → sandboxd / fs-snapshotd: unprivileged,
  #    supervised sandboxes via user namespaces + cgroup-v2 delegation + overlays.
  security.allowUserNamespaces = true; # default; explicit for the sandbox membrane

  # -- ebpf membrane → agent-guardd + eventd: kernel evidence for net/proc/file.
  #    BTF ships in the NixOS kernel by default; tooling for the evidence layer is
  #    in environment.systemPackages below. (BPF-LSM program attach is enabled by
  #    the agent-guardd module when it lands, to avoid overriding the host LSM
  #    stack from the base layer.)

  # Kernel tuning for the OTP control plane (agent-supervisord) + many fibers and
  # the index/surface data paths.
  boot.kernel.sysctl = {
    # OTP + Zig daemons + sandboxes: lots of fds, processes, and inotify watches
    # (fs-snapshotd, surfaces, index refresh).
    "fs.file-max" = 2097152;
    "fs.inotify.max_user_watches" = 1048576;
    "fs.inotify.max_user_instances" = 8192;
    "kernel.pid_max" = 4194304;
    "user.max_user_namespaces" = 63920;
    # index corpora pulls + surface streams over the fat pipe.
    "net.core.default_qdisc" = "fq";
    "net.ipv4.tcp_congestion_control" = "bbr";
  };

  # BEAM/OTP and many-fiber workloads exhaust the default fd ceiling; raise the
  # systemd-managed and login limits to match the sysctl above.
  systemd.extraConfig = ''
    DefaultLimitNOFILE=1048576
  '';
  security.pam.loginLimits = [
    { domain = "*"; type = "soft"; item = "nofile"; value = "1048576"; }
    { domain = "*"; type = "hard"; item = "nofile"; value = "1048576"; }
  ];

  # surface / OTel evidence: keep logs across reboots so eventd/otelcol and the
  # operator surfaces have a durable journal to draw on.
  services.journald.extraConfig = ''
    Storage=persistent
    SystemMaxUse=2G
  '';

  # === Networking ============================================================
  # Vultr bare metal generally hands out the primary address via DHCP. For a
  # static config, take the IP/gateway/netmask from the Vultr panel (see README).
  networking.hostName = "vakedos";
  networking.useNetworkd = true;
  networking.useDHCP = lib.mkDefault true;
  systemd.network.wait-online.anyInterface = true;

  networking.firewall.enable = true;
  networking.firewall.allowedTCPPorts = [ 22 ];

  # === SSH (key-only) ========================================================
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password"; # key-only root for nixos-anywhere + deploys
    };
  };

  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-ed25519 REPLACE-WITH-YOUR-SSH-PUBLIC-KEY"
  ];

  users.users.vaked = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 REPLACE-WITH-YOUR-SSH-PUBLIC-KEY"
    ];
  };
  security.sudo.wheelNeedsPassword = false;

  # === Nix: make the EPYC earn its keep as a build host ======================
  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    # max-jobs = derivations built in parallel; "auto" = number of CPUs.
    max-jobs = "auto";
    # cores = NIX_BUILD_CORES, the parallelism *inside* one derivation.
    # 0 means "use all available CPU cores" (per the Nix manual — this is also
    # the Nix default; it is NOT 1 core). Combined with max-jobs=auto this can
    # oversubscribe (≈ cpus × cpus threads); the usual risk is OOM from many
    # parallel linkers, which the 196 GB ECC removes — so we let it use the whole
    # box. If you ever see scheduler thrashing on huge parallel builds, cap it,
    # e.g. max-jobs=8; cores=8 on a ~64-thread part.
    cores = 0;
    trusted-users = [ "root" "@wheel" ];
    http-connections = 50;
    substituters = [ "https://cache.nixos.org" ];
  };
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 30d";
  };
  # Keep large build trees on the dedicated /build ZFS dataset (disko.nix).
  systemd.services.nix-daemon.environment.TMPDIR = "/build";
  boot.tmp.cleanOnBoot = true;

  # === Toolchains + membrane tooling =========================================
  # `nix develop` provides the full vaked dev shell; these are the host-level
  # tools worth having directly — including the eBPF evidence layer and the
  # sandboxd wasm isolation backend (#50), which are host capabilities rather
  # than per-runtime build outputs.
  environment.systemPackages = with pkgs; [
    git
    jq
    just
    zig
    nixpkgs-fmt
    zfs
    edac-utils # ECC inspection (ras-mc-ctl)
    # ebpf membrane (agent-guardd) — evidence/enforcement tooling
    bpftools
    bpftrace
    libbpf
    # process/filesystem membrane (sandboxd) — wasm isolation backend (#50)
    wasmtime
  ];

  time.timeZone = "UTC";

  # Set once at first install; do not bump casually.
  system.stateVersion = "25.05";
}
