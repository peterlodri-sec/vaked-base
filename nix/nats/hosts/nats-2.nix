import ../nats-node.nix {
  name = "nats-2";
  publicIp = "REPLACE_IP_2";
  routes = [
    "nats://nats-1.vaked.internal:6222"
    "nats://nats-3.vaked.internal:6222"
  ];
}
