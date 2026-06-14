# nats-1 cluster member. Fill publicIp from provision.sh output, then add this
# module to the node's nixosConfiguration. routes = the OTHER two members.
import ../nats-node.nix {
  name = "nats-1";
  publicIp = "REPLACE_IP_1";
  routes = [
    "nats://nats-2.vaked.internal:6222"
    "nats://nats-3.vaked.internal:6222"
  ];
}
