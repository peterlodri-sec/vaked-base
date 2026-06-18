#!/usr/bin/env python3
"""vaked-ledger-mcp — Oculus ledger querying via MCP.

Query by kind, date range, hash chain verification.
Exposes the swarm's append-only truth to the agent fleet.

GENESIS_SEAL:  7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf
ULTIMATE_HASH: 81aa1c0bd9e11fef
"""
import json, sys, os, subprocess

LEDGER_PATH = "/tmp/oculus_export.jsonl"

def _fetch_ledger():
    if not os.path.isfile(LEDGER_PATH):
        subprocess.run(["ssh", "dev-cx53", "sudo cat /var/lib/private/meta-ralphd/oculus.jsonl"],
                      stdout=open(LEDGER_PATH, "w"), stderr=subprocess.DEVNULL, timeout=15)

def _load():
    _fetch_ledger()
    entries = []
    if os.path.isfile(LEDGER_PATH):
        with open(LEDGER_PATH) as f:
            for line in f:
                if line.strip():
                    try: entries.append(json.loads(line))
                    except: pass
    return entries

def query_last(n=10):
    entries = _load()[-n:]
    return [{"seq": e["seq"], "kind": e["payload"].get("kind","?"), "hash": e.get("hash","")[:12]} for e in entries]

def query_by_kind(kind, n=5):
    entries = [e for e in _load() if e["payload"].get("kind") == kind]
    return [{"seq": e["seq"], "hash": e.get("hash","")[:12]} for e in entries[-n:]]

def verify_chain():
    entries = _load()
    if len(entries) < 2: return {"valid": True, "entries": len(entries)}
    import hashlib
    for i in range(1, len(entries)):
        prev = entries[i-1]["hash"]
        payload = json.dumps(entries[i]["payload"], sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(prev.encode() + payload.encode()).hexdigest()
        if expected != entries[i]["hash"]:
            return {"valid": False, "broken_at": i, "expected": expected[:16], "found": entries[i]["hash"][:16]}
    return {"valid": True, "entries": len(entries), "last_hash": entries[-1]["hash"][:16]}

TOOLS = {
    "query_last": lambda args: query_last(args.get("n", 10)),
    "query_by_kind": lambda args: query_by_kind(args["kind"], args.get("n", 5)),
    "verify_chain": lambda args: verify_chain(),
    "stats": lambda args: {"entries": len(_load()), "genesis": "7c242080"},
}

# MCP stdio protocol (same pattern as Ralph)
def main():
    init = json.loads(sys.stdin.readline().strip())
    resp = {"jsonrpc":"2.0","id":init.get("id",0),"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"vaked-ledger-mcp","version":"1.0.0"}}}
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
