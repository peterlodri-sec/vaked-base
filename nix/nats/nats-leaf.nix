# Leaf-node module for app hosts (cx53, bench-node, GCP workers): a local
# nats-server that dials OUT to the cluster, giving each box a local :4222
# endpoint + global subject propagation, resilient to brief hub blips.
# Off-tailnet boxes connect via public + mTLS.
{ hubUrls, certDir ? "/var/lib/nats/pki", credsFile ? "/etc/nats/leaf.creds", ... }:
{ lib, ... }:
{
  networking.firewall.allowedTCPPorts = [ 4222 ];
  services.nats = {
    enable = true;
    jetstream = false;          # leaf relies on the hub's JetStream
    settings = {
      server_name = "leaf";
      host = "127.0.0.1";       # local clients only
      port = 4222;
      leafnodes.remotes = [
        {
          urls = hubUrls;       # [ "tls://nats-1.vaked.internal:7422" ... ]
          credentials = credsFile;
          tls = {
            ca_file = "${certDir}/ca.crt";
          };
        }
      ];
    };
  };
}
