"""Capability divergence convergence test."""
import sys, time
sys.path.insert(0, "/opt/synapsed-pkg")
from synapsed.gossip import SwarmState, GossipPacket, send_gossip, GOSSIP_HELLO
from synapsed.udp import UdpGossipTransport

data_dir = "/tmp/synapsed-divergence"
swarm = SwarmState("edge-node-02", data_dir)

print("=== BEFORE GOSSIP ===")
eg = (swarm.merkle_tree.to_dict().get("children",{}).get("genesis",{})
      .get("children",{}).get("network",{}).get("children",{}).get("egress",{})
      .get("leaf_value",{}))
print(f"  Root: {swarm.root_hash[:32]}...")
print(f"  egress.default: {eg.get('default','?')}")
print(f"  authority: {eg.get('authority','?')}")

transport = UdpGossipTransport("edge-node-02", swarm.merkle_tree, "100.66.205.85", 14435)
start = time.time()
transport.gossip_once("100.105.72.88", 4435, timeout=3.0)

hello = GossipPacket(GOSSIP_HELLO, "edge-node-02", {
    "merkle_root": swarm.root_hash, "capability_count": swarm.merkle_tree.leaf_count})
resp = send_gossip("100.105.72.88", 4434, hello, swarm, timeout=3.0)
elapsed = (time.time() - start) * 1000

print("\n=== AFTER GOSSIP (%.1fms) ===" % elapsed)
eg2 = (swarm.merkle_tree.to_dict().get("children",{}).get("genesis",{})
       .get("children",{}).get("network",{}).get("children",{}).get("egress",{})
       .get("leaf_value",{}))
print(f"  Root: {swarm.root_hash[:32]}...")
print(f"  egress.default: {eg2.get('default','?')}")
print(f"  authority: {eg2.get('authority','?')}")

if eg2.get("default") == "deny" and eg2.get("authority") == "genesis":
    print("\nCONVERGENCE: Genesis authority propagated (deny overrides allow)")
elif eg2.get("default") == "allow":
    print("\nDIVERGENCE PERSISTED: allow was not overridden")
else:
    print("\nUNEXPECTED: %s" % eg2)
