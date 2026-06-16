"""Strategy-enabled gateway runner."""
import sys, os, threading, logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
STORE = "/nix/store/4r1f3d6gfh9k2hiykjinijnaac21vr0g-synapsed-0.1.0"
sys.path.insert(0, STORE + "/lib/vaked")
from synapsed.gossip import SwarmState
from synapsed.gateway import run_gateway, GatewayHandler
from synapsed.sentinel import Sentinel
swarm = SwarmState("genesis.vaked.dev", "/var/lib/private/synapsed")
swarm.add_capability("genesis/network/egress", {"default": "deny"})
sentinel = Sentinel("genesis.vaked.dev", "/var/lib/private/synapsed", swarm.merkle_tree)
sentinel.start()
GatewayHandler._ledger_path = "/var/lib/private/meta-ralphd/oculus.jsonl"
GatewayHandler.constellation_path = "/var/www/constellation/index.html"
t = threading.Thread(target=run_gateway, args=(swarm, "100.105.72.88", 8081, 27.3, sentinel), daemon=True)
t.start()
print("Gateway: 100.105.72.88:8081")
# Hourly synthesis thread
def synthesis_loop():
    import subprocess
    while True:
        time.sleep(3600)
        try:
            subprocess.run(["python3", "/tmp/wise_synthesize.py"], cwd=os.path.expanduser("~"),
                         capture_output=True, timeout=60)
            subprocess.run(["sudo", "cp", "/tmp/vaked-library/wisdom.html", "/var/www/library/wisdom.html"],
                         capture_output=True, timeout=10)
            subprocess.run(["sudo", "cp", "/tmp/vaked-library/strategy.json", "/var/www/library/strategy.json"],
                         capture_output=True, timeout=10)
            logging.info("Hourly synthesis complete")
        except Exception as e:
            logging.error("Synthesis failed: %s", e)

threading.Thread(target=synthesis_loop, daemon=True).start()
logging.info("Hourly synthesis thread started")

import time
while True:
    time.sleep(10)
