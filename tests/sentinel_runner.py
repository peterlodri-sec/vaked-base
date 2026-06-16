"""Sentinel + Gateway — runs the L3 reputation layer and web gateway."""
import sys, os, threading, logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

STORE = "/nix/store/b03dwx5mb9wyw39scbymybq7rhna95ir-synapsed-0.1.0"
sys.path.insert(0, STORE + "/lib/vaked")

from synapsed.gossip import SwarmState
from synapsed.gateway import run_gateway
from synapsed.sentinel import Sentinel

swarm = SwarmState("genesis.vaked.dev", "/var/lib/private/synapsed")
swarm.add_capability("genesis/network/egress", {"default": "deny", "version": "2"})

sentinel = Sentinel("genesis.vaked.dev", "/var/lib/private/synapsed", swarm.merkle_tree)
sentinel.start()
print("Sentinel: active, trust_index=%.3f" % sentinel.trust_index)

t = threading.Thread(target=run_gateway, args=(swarm, "100.105.72.88", 8081, 27.3, sentinel), daemon=True)
t.start()
print("Gateway: http://100.105.72.88:8081")

import time
while True:
    time.sleep(10)
