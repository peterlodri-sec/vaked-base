"""Sentinel malicious capability injection test."""
import sys, time
sys.path.insert(0, "/nix/store/b03dwx5mb9wyw39scbymybq7rhna95ir-synapsed-0.1.0/lib/vaked")
from synapsed.sentinel import Sentinel
from synapsed.merkletree import CapabilityMerkleTree

mt = CapabilityMerkleTree()
mt.insert("genesis/network/egress", {"default": "deny", "version": "2"})
sentinel = Sentinel("test-sentinel", "/tmp/sentinel-test", mt)
sentinel.start()

# Inject a lie
print("Injecting malicious claim from edge-node-02...")
alert = sentinel.inject_test_lie(
    liar_id="edge-node-02",
    path="genesis/network/egress",
    fake_value={"default": "allow", "authority": "rogue", "fabricated": True}
)

if alert:
    print("Sentinel DETECTED dishonesty!")
    print("  Alert kind:", alert.get("kind"))
    print("  Target:    ", alert.get("target"))
    print("  Path:      ", alert.get("path"))
    print("  Claimed:   ", alert.get("claimed"))
    print("  Actual:    ", alert.get("actual"))
    print("  Severity:  ", alert.get("severity"))
else:
    print("Alert: NO_ALERT")

state = sentinel.to_dict()
print()
print("Trust index:", state.get("trust_index"))
print("Flagged peers:", state.get("flagged_peers"))
for pid, info in state.get("peers", {}).items():
    print("  %s: score=%.3f alerts=%d flagged=%s" % (
        pid, info["score"], info["alerts"], info["flagged"]))

sentinel.stop()
# Force exit (don't wait for Sentinel thread to finish its sleep)
import os
os._exit(0 if sentinel.trust_index < 1.0 else 1)
