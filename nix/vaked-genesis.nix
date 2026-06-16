# NixOS module for vaked-genesis — the genesis bootstrap daemon for the Vaked mesh.
#
# The genesis node is the bootstrap entry point for the Vaked peer-to-peer mesh,
# discovered via DNS SRV (``_vaked-bootstrap._tcp.vaked.dev``). It binds
# exclusively to the tailscale0 interface (or a configured IP), serves bootstrap
# handshakes, and maintains an eventd-compatible audit chain.
#
# Exposed from the flake as ``nixosModules.vaked-genesis``. Usage:
#
#   imports = [ inputs.vaked.nixosModules.vaked-genesis ];
#   services.vaked-genesis = {
#     enable = true;
#     bindIP = "100.105.72.88";          # tailscale0 IP
#     bindPort = 4433;
#     genesisID = "genesis.vaked.dev";
#   };
#
# The daemon is stdlib-only Python; the package is just python3 + the genesisd/
# subtree in the repo. The closure is tiny. Runs unprivileged (DynamicUser) with
# full systemd sandboxing, binding only to the configured IP.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.vaked-genesis;
in
{
  options.services.vaked-genesis = {
    enable = lib.mkEnableOption "vaked-genesis — genesis bootstrap daemon for the Vaked mesh";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.vaked-genesis;
      defaultText = "pkgs.vaked-genesis";
      description = "The vaked-genesis package (a python3 wrapper around genesisd/).";
    };

    bindIP = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "IP address to bind the bootstrap listener to (e.g., the tailscale0 IP).";
    };

    bindPort = lib.mkOption {
      type = lib.types.port;
      default = 4433;
      description = "TCP port for the bootstrap listener.";
    };

    genesisID = lib.mkOption {
      type = lib.types.str;
      default = "genesis.vaked.dev";
      description = "Genesis node identifier (hostname or SRV target).";
    };

    openTailscaleFirewall = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Automatically add a firewall rule for allowedTCPPorts on the tailscale0
        interface. When enabled, the module adds:
          networking.firewall.interfaces."tailscale0".allowedTCPPorts = [ cfg.bindPort ];
        Only the Tailscale interface is opened — all other interfaces remain deny-by-default.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    # Package the genesis daemon if not already in pkgs.
    environment.systemPackages = [ cfg.package ];

    # Firewall: open only on tailscale0 (never on public interfaces).
    networking.firewall.interfaces."tailscale0" = lib.mkIf cfg.openTailscaleFirewall {
      allowedTCPPorts = [ cfg.bindPort ];
    };

    # The systemd service for vaked-genesis.
    systemd.services.vaked-genesis = {
      description = "vaked-genesis — bootstrap genesis daemon for the Vaked mesh";
      after = [ "network-online.target" "tailscaled.service" ];
      wants = [ "network-online.target" "tailscaled.service" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        ExecStart = "${cfg.package}/bin/vaked-genesis \
          --bind-ip ${cfg.bindIP} \
          --bind-port ${toString cfg.bindPort} \
          --genesis-id ${cfg.genesisID}";

        # Unprivileged + private state dir (audit log lives here).
        DynamicUser = true;
        StateDirectory = "vaked-genesis";
        RuntimeDirectory = "vaked-genesis";

        # Pass the state dir path via the environment variable the daemon reads
        # (STATE_DIRECTORY is set by systemd for DynamicUser).
        Environment = [
          "GENESISD_LOG_DIR=%S/vaked-genesis/log"
        ];

        Restart = "on-failure";
        RestartSec = 5;

        # ── Hardening ────────────────────────────────────────────────────────
        # fail-closed: the genesis daemon needs only network I/O on one
        # specific IP:port. Everything else is denied.

        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;

        # No capabilities needed — we bind to a specific IP, not privileged ports.
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";

        # Only allow the system calls needed for socket I/O and threading.
        SystemCallFilter = [
          "@system-service"
          "~@privileged"
          "~@resources"
        ];
        SystemCallErrorNumber = "EPERM";

        # IP address sandboxing: bind only to the configured IP.
        # This works for modern systemd (v250+).
        IPAddressAllow = cfg.bindIP;
        IPAddressDeny = "any";

        # Socket bind sandboxing: restrict to AF_INET/AF_INET6 (single definition above).
      };
    };

    # Verify the daemon is healthy after start.
    systemd.services.vaked-genesis.postStart = ''
      ${pkgs.coreutils}/bin/sleep 1
      ${pkgs.systemd}/bin/systemctl is-active vaked-genesis || exit 1
    '';
  };
}
