#!/bin/sh
# readme-gen — regenerate README.md from live swarm state
# Run: bash tools/readme-gen.sh
# Principle: docs are reviewed, reflected, generated from the live system

set -e

LEDGER=$(ssh dev-cx53 'sudo wc -l < /var/lib/private/meta-ralphd/oculus.jsonl 2>/dev/null' 2>/dev/null || echo "?")
GRAVE=$(ssh dev-cx53 'wc -l < /var/log/vaked/graveyard.log 2>/dev/null' 2>/dev/null || echo "?")
MONO=$(curl -s https://constellation.vaked.dev/swarm-monologue 2>/dev/null | grep -o 'class="line">[^<]*' | sed 's/class="line">//')
GATEWAY=$(ssh dev-cx53 'systemctl --user is-active constellation-gateway 2>/dev/null' 2>/dev/null || echo "?")
GATEWAY_RAM=$(ssh dev-cx53 'systemctl --user show constellation-gateway --property=MemoryCurrent 2>/dev/null | cut -d= -f2' 2>/dev/null || echo "?")
PARIS=$(ssh -i ~/.ssh/swarm_self_genesis_block_key -o ConnectTimeout=5 ubuntu@57.130.66.229 'tailscale ip -4 2>/dev/null' 2>/dev/null || echo "offline")
ENDPOINTS=$(curl -s -o /dev/null -w "%{http_code}" https://constellation.vaked.dev/health 2>/dev/null)

echo "ledger=$LEDGER graveyard=$GRAVE gateway=$GATEWAY ram=$GATEWAY_RAM paris=$PARIS endpoints=$ENDPOINTS"
echo "monologue: $MONO"

# Update README counts
if [ -f README.md ]; then
    if [ "$LEDGER" != "?" ]; then
        sed -i '' "s/([0-9]* entries)/($LEDGER entries)/g" README.md 2>/dev/null || sed -i "s/([0-9]* entries)/($LEDGER entries)/g" README.md
    fi
    if [ "$GRAVE" != "?" ]; then
        sed -i '' "s/([0-9]* entries)/($GRAVE entries)/g" README.md 2>/dev/null || sed -i "s/([0-9]* entries)/($GRAVE entries)/g" README.md
    fi
    echo "README.md updated"
fi
