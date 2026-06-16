"""Log mesh expansion to Oculus ledger."""
import json, time, os, hashlib

def chash(prev, payload):
    h = hashlib.sha256()
    h.update(prev.encode("ascii"))
    h.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    return h.hexdigest()

path = "/var/lib/private/meta-ralphd/oculus.jsonl"
prev = "0"*64
seq = -1
if os.path.isfile(path):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                seq = e.get("seq", -1)
                prev = e.get("hash", "0"*64)
            except: pass

entry = {
    "seq": seq+1, "prev": prev,
    "payload": {
        "kind": "MESH_EXPANSION",
        "node": "edge-us-west-01",
        "location": "Hillsboro, OR, US",
        "ip": "5.78.122.125",
        "os": "Ubuntu 26.04",
        "latency_profile": {
            "intra_eu_ms": 136,
            "transatlantic_ms": 1751,
            "adaptive_batching": True,
            "threshold_ms": 300
        },
        "tailscale_status": "needs_auth",
        "auth_url": "https://login.tailscale.com/a/18c8ee6f012645",
        "timestamp": time.time()
    },
    "hash": ""
}
entry["hash"] = chash(prev, entry["payload"])

with open(path, "ab") as f:
    line = json.dumps(entry, sort_keys=True).encode() + b"\n"
    f.write(line)
    f.flush()
    os.fsync(f.fileno())
print("OK: MESH_EXPANSION logged to Oculus ledger")
print("seq=%d transatlantic=%dms adaptive_batching=True" % (entry["seq"], 1751))
