import ../nats-node.nix {
  name = "nats-3";
  publicIp = "REPLACE_IP_3";
  routes = [
    "nats://nats-1.vaked.internal:6222"
    "nats://nats-2.vaked.internal:6222"
  ];
}
