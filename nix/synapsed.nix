# NixOS module for synapsed — P2P capability-graph gossip protocol daemon.
#
# Synapse enables the Vaked swarm: nodes discover each other via the genesis
# bootstrap node and synchronize capability-graph state over encrypted P2P
# gossip (Tailscale WireGuard). Uses Merkle-tree delta sync for O(log N)
# state transfer.
#
# Exposed from the flake as ``nixosModules.synapsed``. Usage:
#
#   imports = [ inputs.vaked.nixosModules.synapsed ];
#   services.synapsed = {
#     enable = true;
#     bindIP = "100.105.72.88";         # tailscale0 IP
#     gossipPort = 4434;
#     genesisPeers = [ "100.105.72.88" ];  # bootstrap peers
#   };
#
# Runs as DynamicUser with ProtectSystem=strict.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.synapsed;
in
{
  options.services.synapsed = {
    enable = lib.mkEnableOption "synapsed — P2P gossip protocol daemon";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.synapsed;
      defaultText = "pkgs.synapsed";
      description = "The synapsed package (Python reference implementation).";
    };

    bindIP = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "IP address to bind the gossip server to (tailscale0 IP).";
    };

    gossipPort = lib.mkOption {
      type = lib.types.port;
      default = 4434;
      description = "TCP port for the gossip protocol.";
    };

    genesisPeers = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [];
      description = "List of genesis peer IPs to connect to at startup.";
    };

    openTailscaleFirewall = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Automatically add a firewall rule for allowedTCPPorts on the tailscale0
        interface for the gossip port.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];

    networking.firewall.interfaces."tailscale0" = lib.mkIf cfg.openTailscaleFirewall {
      allowedTCPPorts = [ cfg.gossipPort ];
    };

    systemd.services.synapsed = {
      description = "synapsed — P2P capability-graph gossip protocol daemon";
      after = [ "network-online.target" "tailscaled.service" "vaked-genesis.service" ];
      wants = [ "network-online.target" "tailscaled.service" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        ExecStart = "${cfg.package}/bin/synapsed start \
          --bind-ip ${cfg.bindIP} \
          --port ${toString cfg.gossipPort} \
          --genesis-peers ${lib.concatStringsSep "," cfg.genesisPeers}";

        DynamicUser = true;
        StateDirectory = "synapsed";
        RuntimeDirectory = "synapsed";

        Restart = "on-failure";
        RestartSec = 5;

        # ── Hardening ────────────────────────────────────────────────────
        # Synapse needs: TCP sockets for gossip, read/write its data dir.
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
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        SystemCallFilter = [ "@system-service" "~@privileged" ];
        SystemCallErrorNumber = "EPERM";
      };
    };
  };
}
