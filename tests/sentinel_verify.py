"""Sentinel logic verification test."""
import sys, os
sys.path.insert(0, "/nix/store/b03dwx5mb9wyw39scbymybq7rhna95ir-synapsed-0.1.0/lib/vaked")
from synapsed.sentinel import TrustEngine, TruthPing
from synapsed.merkletree import CapabilityMerkleTree

mt = CapabilityMerkleTree()
mt.insert("genesis/network/egress", {"default": "deny"})
print("Tree root:", mt.root_hash[:16])

tp = TruthPing(mt)
honest, actual = tp.verify_claim("genesis/network/egress", {"default": "allow"})
print("TruthPing claim=allow -> honest:", honest, "actual:", actual)
assert not honest, "claim=allow should be dishonest when truth is deny"

honest2, _ = tp.verify_claim("genesis/network/egress", {"default": "deny"})
print("TruthPing claim=deny  -> honest:", honest2)
assert honest2, "claim=deny should be honest when truth is deny"

te = TrustEngine()
alert = tp.cross_reference_gossip("edge-node-02", "rx", "genesis/network/egress", {"default": "allow"})
assert alert is not None, "cross-reference should detect lie"
te.penalize("edge-node-02", alert["severity"], 0.15)
print("Trust: %.3f, flagged: %s" % (te.get("edge-node-02").score, te.get("edge-node-02").flagged))
assert te.trust_index() < 1.0, "trust should drop after penalize"
assert "edge-node-02" in te.flagged_peers(), "flagged peers should include liar"

print("PASS: Sentinel logic verified — trust dropped, liar flagged")
os._exit(0)
