{ config, lib, pkgs, ... }:

# Root eBPF watcher for vaked-oracle. Exposes a unix socket; the unprivileged
# revdev client (tools/oracle/watcher_client.py) requests PID-scoped bpftrace
# evidence. revdev never gains CAP_BPF/CAP_PERFMON — the socket is the entire
# attenuation surface ("the watcher watches the analyst").
#
# DEPLOY (manual, on the box; nix-base and vaked-base are SEPARATE repos):
#   1. Copy this module + tools/oracle/watcher_daemon.py into the nix-base
#      dev-cx53 host config (or reference them), keeping `watcher` pointed at the
#      deployed watcher_daemon.py.
#   2. Import this module from the dev-cx53 host (the same imports list that
#      includes revdev.nix).
#   3. `sudo nixos-rebuild switch --flake .#dev-cx53` ON THE BOX.
#   4. Verify: `systemctl is-active oracle-ebpf-watcher` (active) and
#      `ls -l /run/oracle-watcher.sock` (srw-rw---- root oracle-watcher).
let
  watcher = ./watcher_daemon.py;
in
{
  systemd.services.oracle-ebpf-watcher = {
    description = "vaked-oracle eBPF watcher (root; PID-scoped bpftrace over a unix socket)";
    after = [ "network.target" ];
    wantedBy = [ "multi-user.target" ];
    path = [ pkgs.bpftrace pkgs.coreutils ];
    serviceConfig = {
      Type = "simple";
      ExecStart = "${pkgs.python3}/bin/python3 ${watcher}";
      Restart = "on-failure";
      RestartSec = 3;
      RuntimeDirectory = "oracle-watcher";
      Group = "oracle-watcher";
    };
  };

  # revdev reaches the socket via group membership — no caps granted to revdev.
  users.groups.oracle-watcher = { };
  users.users.revdev.extraGroups = [ "oracle-watcher" ];
}
