"""Genesis UDP listener for divergence test."""
import sys, time, threading
sys.path.insert(0, "/nix/store/9l6kn8l294a42nb427fpjq3w6rjy32lr-synapsed-0.1.0/lib/vaked")
from synapsed.merkletree import CapabilityMerkleTree
from synapsed.udp import UdpGossipTransport

mt = CapabilityMerkleTree()
mt.insert("genesis/network/egress", {
    "default": "deny",
    "allow": ["100.105.72.88:4433"],
    "protocol": "tcp",
    "authority": "genesis"
})
print("Genesis: %d caps, root=%s..." % (mt.leaf_count, mt.root_hash[:16]))
t = UdpGossipTransport("genesis.vaked.dev", mt, "100.105.72.88", 4435)
t.serve_forever()
