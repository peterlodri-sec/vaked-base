# Reusable NATS cluster-member module. Config goes through services.nats.settings
# (the free-form escape hatch -> nats-server config), so we don't depend on
# per-option NixOS attr names. Instantiate per node from nix/nats/hosts/<name>.nix.
#
# OPEN ITEM: verify the pinned-nixpkgs `services.nats` accepts `settings` with
#   these nested keys (jetstream/cluster/leafnodes/tls). Adapt if the module
#   wraps any. `nixos-option services.nats.settings` on the target confirms.
{ name, publicIp, routes, certDir ? "/var/lib/nats/pki", ... }:
{ lib, ... }:
{
  networking.firewall.allowedTCPPorts = [ 4222 6222 7422 8222 ];

  services.nats = {
    enable = true;
    jetstream = true;
    settings = {
      server_name = name;
      host = "0.0.0.0";          # clients over tailnet; ACL gates reachability
      port = 4222;
      max_payload = 1048576;     # 1 MiB
      write_deadline = "10s";
      ping_interval = "2m";
      lame_duck_duration = "30s";
      server_tags = [ "az:fsn1" "node:${name}" ];

      jetstream = {
        store_dir = "/var/lib/nats/jetstream";
        max_memory_store = 2147483648;    # 2 GiB
        max_file_store = 64424509440;     # 60 GiB
        sync_interval = "2m";
      };

      cluster = {
        name = "vaked-nats";
        host = publicIp;          # RAFT over public IP (co-located, sub-ms)
        port = 6222;
        routes = routes;
        pool_size = 3;
        no_advertise = true;
        tls = {
          cert_file = "${certDir}/${name}.crt";
          key_file = "${certDir}/${name}.key";
          ca_file = "${certDir}/ca.crt";
          verify_and_map = true;
          timeout = 5;
        };
      };

      leafnodes = {
        port = 7422;
        tls = {
          cert_file = "${certDir}/${name}.crt";
          key_file = "${certDir}/${name}.key";
          ca_file = "${certDir}/ca.crt";
          verify = true;
        };
      };

      # operator + system_account + nats-resolver, deployed as a secret include.
      include = "auth.conf";

      http = "0.0.0.0:8222";      # monitoring (ACL-gated to tailnet)
    };
  };

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
