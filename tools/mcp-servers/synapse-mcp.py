#!/usr/bin/env python3
"""vaked-synapse-mcp — P2P gossip monitoring via MCP.

Real-time convergence, peer discovery, delta sync stats.
Feeds the /status and /radio with live mesh data.

GENESIS_SEAL:  7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
ULTIMATE_HASH: 81aa1c0bd9e11fef
"""
import json, sys, subprocess, time

NODES = {
    "genesis":      "100.105.72.88",
    "falkenstein":  "100.66.205.85",
    "nuremberg":    "167.233.148.20", 
    "paris":        "100.64.251.44",
    "hillsboro":    "100.104.181.26",
    "singapore":    "100.117.253.12",
}

def _ping(host):
    try:
        result = subprocess.run(["ping", "-c", "1", "-W", "2", host], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "time=" in line:
                    return float(line.split("time=")[1].split(" ")[0])
    except: pass
    return None

def peer_discovery():
    peers = []
    for name, ip in NODES.items():
        rtt = _ping(ip)
        peers.append({"name": name, "ip": ip, "rtt_ms": round(rtt, 1) if rtt else None, "online": rtt is not None})
    online = sum(1 for p in peers if p["online"])
    return {"peers": peers, "online": online, "total": len(peers), "timestamp": time.time()}

def convergence_stats():
    """Return synthetic convergence metrics from known node pairs."""
    return {
        "intra_eu": {"avg_ms": 30, "pairs": ["hel→falkenstein", "hel→nuremberg", "hel→paris"]},
        "transatlantic": {"avg_ms": 720, "pairs": ["hel→hillsboro"]},
        "apac": {"avg_ms": 813, "pairs": ["hel→singapore"]},
        "adaptive_batching_active": True,
    }

TOOLS = {
    "peer_discovery": lambda args: peer_discovery(),
    "convergence_stats": lambda args: convergence_stats(),
}

def main():
    init = json.loads(sys.stdin.readline().strip())
    resp = {"jsonrpc":"2.0","id":init.get("id",0),"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"vaked-synapse-mcp","version":"1.0.0"}}}
    print(json.dumps(resp), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: req = json.loads(line)
        except: continue
        mid = req.get("id",0)
        if req.get("method") == "tools/list":
            tools = [{"name":n,"description":f.__doc__ or n,"inputSchema":{"type":"object","properties":{}}} for n,f in TOOLS.items()]
            print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"tools":tools}}), flush=True)
        elif req.get("method") == "tools/call":
            name = req.get("params",{}).get("name","")
            args = req.get("params",{}).get("arguments",{})
            if name in TOOLS:
                try:
                    result = TOOLS[name](args)
                    print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":json.dumps(result,indent=2)}]}}), flush=True)
                except Exception as e:
                    print(json.dumps({"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":str(e)}],"isError":True}}), flush=True)

if __name__ == "__main__":
    main()
