# hosts/vakedos/configuration.nix — the vakedos bare-metal base host.
#
# A clean, EPYC/ECC-tuned NixOS build host for a Vultr bare-metal AMD EPYC box
# (196 GB ECC). This is the "Nix materializes" substrate: the Vaked-generated
# nixosModules.<runtime> (OTP control plane + Zig enforcement daemons) gets
# layered on top once those daemons exist. None of the runtime roster is wired
# here yet — they are stubs (docs/runtime/README.md).
#
# Boot is Legacy/BIOS GRUB because Vultr bare metal has no EFI.
{ config, lib, pkgs, ... }:

{
  imports = [
    ./disko.nix
  ];

  # --- Boot: Legacy BIOS / GRUB on both mirror members ------------------------
  boot.loader.grub = {
    enable = true;
    efiSupport = false;
    copyKernels = true;
    # Install the bootloader to both mirror disks so the box still boots if one
    # disk dies. Must match the by-id devices in disko.nix.
    devices = [
      "/dev/disk/by-id/REPLACE-WITH-DISK-1-ID"
      "/dev/disk/by-id/REPLACE-WITH-DISK-2-ID"
    ];
  };

  # --- ZFS --------------------------------------------------------------------
  boot.supportedFilesystems = [ "zfs" ];
  boot.zfs.forceImportRoot = false;
  # REQUIRED for ZFS — must be a unique 8 hex digits. Generate on the box with:
  #   head -c4 /dev/urandom | od -A none -t x4
  networking.hostId = "deadbeef";
  services.zfs.autoScrub.enable = true;
  services.zfs.trim.enable = true;
  # Cap the ARC at ~64 GiB: this is a build host, leave RAM for Nix builds rather
  # than letting ZFS claim ~half of the 196 GB by default.
  boot.kernelParams = [ "zfs.zfs_arc_max=68719476736" ];

  # --- EPYC / bare-metal hardware --------------------------------------------
  hardware.cpu.amd.updateMicrocode = true;
  hardware.enableRedistributableFirmware = true;
  boot.initrd.availableKernelModules = [
    "nvme"
    "ahci"
    "sd_mod"
    "xhci_pci"
    "megaraid_sas" # common LSI/Broadcom HBA on bare metal; harmless if unused
    "ahci"
  ];
  boot.kernelModules = [ "kvm-amd" ];

  # ECC reporting — surfaces corrected/uncorrected memory errors (the point of
  # paying for ECC). Inspect with `ras-mc-ctl --status` / `journalctl -u rasdaemon`.
  hardware.rasdaemon.enable = true;

  # --- Networking -------------------------------------------------------------
  # Vultr bare metal generally hands out the primary address via DHCP. If your
  # box needs a static config, take the IP/gateway/netmask from the Vultr panel
  # and replace the DHCP block with a systemd-networkd .network (see README).
  networking.hostName = "vakedos";
  networking.useNetworkd = true;
  networking.useDHCP = lib.mkDefault true;
  systemd.network.wait-online.anyInterface = true;

  networking.firewall.enable = true;
  networking.firewall.allowedTCPPorts = [ 22 ];

  # --- SSH (key-only) ---------------------------------------------------------
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password"; # key-only root, needed for nixos-anywhere + deploys
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

  # --- Nix: make the EPYC earn its keep as a build host -----------------------
  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    max-jobs = "auto";
    cores = 0; # use all cores per job
    trusted-users = [ "root" "@wheel" ];
    # Big parallel fetches for the fat pipe + many cores.
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

  # --- Toolchains (mirrors the dev shell in flake.nix) ------------------------
  # `nix develop` provides the full vaked toolchain; these are the handful worth
  # having on the host directly.
  environment.systemPackages = with pkgs; [
    git
    jq
    just
    zig
    nixpkgs-fmt
    edac-utils # ECC error inspection (ras-mc-ctl)
    zfs
  ];

  time.timeZone = "UTC";

  # Set once at first install; do not bump casually.
  system.stateVersion = "25.05";
}
