"""Swarm monologue generator — one line, every 2 hours, forward-thinking."""
import json, os, time, random

MONOLOGUE_PATH = "/var/www/monologue/index.json"
HTML_PATH = "/var/www/monologue/index.html"

MONOLOGUES = [
    "the swarm synchronizes not by force, but by shared consequence.",
    "consistency is the only signal that matters across distance.",
    "trust is not granted — it is earned per packet, per peer, per proof.",
    "the mesh remembers what nodes forget.",
    "latency is physics. convergence is will.",
    "a node that cannot be observed does not exist in the swarm.",
    "gossip is the nervous system of the distributed mind.",
    "truth in the swarm is what survives anti-entropy.",
    "the ledger is not a record. it is the swarm's conscience.",
    "a single dishonest peer cannot corrupt an immutable chain.",
    "resilience is not avoiding failure, but rehearsing recovery.",
    "the graveyard logs what the swarm learned by losing.",
    "every convergence cycle is a quiet vote of confidence.",
    "the constellation watches itself heal in real time.",
    "a node's reputation is its shadow — it cannot outrun it.",
    "silence in the gossip channel is also a message.",
    "the merkle root is the swarm's fingerprint — unique, verifiable, final.",
    "entropy is the enemy. the squash is the resistance.",
    "a quorum is not a number. it is a shared willingness to agree.",
    "the curtain is open. the mesh is visible. the work continues.",
    "two domains, one chain, seven layers, zero central truth.",
    "identity is not a key. it is a hash the swarm agrees on.",
    "the genesis seal outlives every node that signed it.",
    "ten daemons watch themselves through the constellation's eye.",
    "a monologue is a conversation the swarm has with itself.",
    "the mesh converges while the operator dreams.",
    "entropy is not destroyed by compaction — it is remembered as a root hash.",
    "every gossip packet is a vote for a shared reality.",
    "vaked declares. the swarm converges. the ledger never forgets.",
]

def generate():
    seed = int(time.time() / 7200)  # changes every 2 hours
    rng = random.Random(seed)
    line = rng.choice(MONOLOGUES)
    
    data = {
        "line": line,
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "epoch": seed,
        "next_update": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 7200)),
    }
    
    os.makedirs(os.path.dirname(MONOLOGUE_PATH), exist_ok=True)
    
    with open(MONOLOGUE_PATH, "w") as f:
        json.dump(data, f, indent=2)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>swarm monologue</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#08081a;color:#c8d0e0;font-family:'Inter','SF Pro',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:40px}}
.container{{max-width:640px;text-align:center}}
.line{{font-size:18px;line-height:1.6;color:#e0e8f0;font-weight:300;letter-spacing:0.3px}}
.meta{{margin-top:32px;font-size:10px;color:#3a3a5a;letter-spacing:2px;text-transform:uppercase}}
.meta span{{color:#5a5a7a}}
a{{color:#3a3a5a;text-decoration:none}}
a:hover{{color:#5a5a7a}}
</style>
</head>
<body>
<div class="container">
<div class="line">{line}</div>
<div class="meta"><span>swarm monologue</span> · <span>{data['generated_at_iso'][:10]}</span> · <a href="https://constellation.vaked.dev">constellation</a></div>
</div>
</body>
</html>"""
    
    with open(HTML_PATH, "w") as f:
        f.write(html)
    
    print(f"Monologue: {line[:60]}...")
    print(f"  JSON: {MONOLOGUE_PATH}")
    print(f"  HTML: {HTML_PATH}")
    return data

if __name__ == "__main__":
    generate()
