# NixOS module for meta-ralphd — the recursive observer (L2).
#
# Meta-Ralph watches Ralph (L1) — the autonomous decision loop — and acts as
# a reflexive watchdog. It monitors CPU, memory, and hash-chain integrity,
# restarting L1 if health checks fail, with strict recursion-safety and a
# circuit breaker that triggers emergency hold (disconnects tailscale0) before
# cascading.
#
# Exposed from the flake as ``nixosModules.meta-ralphd``. Usage:
#
#   imports = [ inputs.vaked.nixosModules.meta-ralphd ];
#   services.meta-ralphd = {
#     enable = true;
#     checkInterval = 5;        # seconds between health checks
#     journalMaxStale = 10;     # max seconds L1 journal can be stale
#     memoryMaxMb = 200;        # max RSS memory for L1
#   };
#
# Isolation: L2 runs as DynamicUser, has read-only access to L1's state dir,
# and CANNOT restart itself (hard-coded PID check). On circuit breaker trip,
# it kills the tailscale0 interface.
{ config, lib, pkgs, ... }:
let
  cfg = config.services.meta-ralphd;
in
{
  options.services.meta-ralphd = {
    enable = lib.mkEnableOption "meta-ralphd — recursive observer (L2)";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.meta-ralphd;
      defaultText = "pkgs.meta-ralphd";
      description = "The meta-ralphd package (Python reference implementation).";
    };

    checkInterval = lib.mkOption {
      type = lib.types.ints.positive;
      default = 5;
      description = "Seconds between health checks of L1.";
    };

    journalMaxStale = lib.mkOption {
      type = lib.types.ints.positive;
      default = 10;
      description = "Max seconds since L1's last journal write before triggering restart.";
    };

    memoryMaxMb = lib.mkOption {
      type = lib.types.ints.positive;
      default = 200;
      description = "Max RSS memory for L1 in MiB before triggering restart.";
    };
  };

  config = lib.mkIf cfg.enable {
    # Add the daemon to the system PATH
    environment.systemPackages = [ cfg.package ];

    # Read-only access to L1's state directory for journal monitoring
    systemd.tmpfiles.rules = [
      "d /var/lib/meta-ralphd 0750 meta-ralphd meta-ralphd -"
    ];

    systemd.services.meta-ralphd = {
      description = "meta-ralphd — recursive observer (L2) for the Vaked runtime";
      after = [ "network-online.target" "ralphd.service" "tailscaled.service" ];
      wants = [ "network-online.target" "ralphd.service" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        ExecStart = "${cfg.package}/bin/meta-ralphd watch \
          --interval ${toString cfg.checkInterval} \
          --journal-stale ${toString cfg.journalMaxStale} \
          --memory-max ${toString cfg.memoryMaxMb}";

        # Unprivileged + private state dir (Oculus ledger lives here)
        DynamicUser = true;
        StateDirectory = "meta-ralphd";
        RuntimeDirectory = "meta-ralphd";

        # Read-only access to L1's state (journal monitoring)
        SupplementaryGroups = [ "ralphd" ];
        BindReadOnlyPaths = [
          "/var/lib/ralph:/var/lib/ralph:ro"
          "/proc/sys/kernel/random/boot_id:/proc/sys/kernel/random/boot_id:ro"
        ];

        Restart = "on-failure";
        RestartSec = 5;

        # ── Hardening ────────────────────────────────────────────────────────
        # L2 needs: read L1 proc/{pid}/*, systemctl restart ralphd,
        # ip link set tailscale0 down (emergency hold).
        # It does NOT need: kernel modules, raw sockets, ptrace.

        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" "AF_NETLINK" ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;

        # Needs: systemctl (setuid) for restarting L1,
        # ip (setuid) for emergency hold tailscale down,
        # read access to /proc/<pid>/stat, /proc/<pid>/status, /proc/<pid>/syscall
        CapabilityBoundingSet = [ "CAP_DAC_OVERRIDE" "CAP_SYS_PTRACE" ];
        AmbientCapabilities = [ "CAP_DAC_OVERRIDE" "CAP_SYS_PTRACE" ];

        # Allow read access to /proc/<pid>/ for monitoring
        ProtectProc = "default";
        ProcSubset = "all";

        SystemCallFilter = [
          "@system-service"
          "~@privileged"
        ];
        SystemCallErrorNumber = "EPERM";
      };
    };

    # Grant meta-ralphd access to read ralphd's state
    users.groups.ralphd = {};

    # Ensure ralph service exists (may be defined elsewhere)
    # If ralphd is not defined, this will fail gracefully at evaluation.
    systemd.services.ralphd = lib.mkIf (!config.services.ralphd.enable or false) {
      description = "ralphd — autonomous decision loop (L1) [placeholder]";
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${pkgs.coreutils}/bin/true";
      };
    };
  };
}
