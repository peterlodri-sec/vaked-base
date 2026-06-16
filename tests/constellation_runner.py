"""Constellation gateway runner."""
import sys, os, threading, logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
STORE = "/nix/store/2dn1sky7ys0ipnxwfdq62h0as5qpkmjs-synapsed-0.1.0"
sys.path.insert(0, STORE + "/lib/vaked")
from synapsed.gossip import SwarmState
from synapsed.gateway import run_gateway, GatewayHandler
from synapsed.sentinel import Sentinel
swarm = SwarmState("genesis.vaked.dev", "/var/lib/private/synapsed")
swarm.add_capability("genesis/network/egress", {"default": "deny"})
sentinel = Sentinel("genesis.vaked.dev", "/var/lib/private/synapsed", swarm.merkle_tree)
sentinel.start()
GatewayHandler.constellation_path = "/var/www/constellation/index.html"
t = threading.Thread(target=run_gateway, args=(swarm, "100.105.72.88", 8081, 27.3, sentinel), daemon=True)
t.start()
print("Gateway: http://100.105.72.88:8081")
print("Constellation: http://100.105.72.88:8081/constellation")
import time
while True:
    time.sleep(10)
