"""Append to Oculus ledger — file-based, no quoting wars."""
import json, time, os, hashlib

PAYLOAD = {
    "kind": "QUOTING_SOLVED",
    "method": "file-based-communication",
    "benefit": "no more escaping shell quotes in nested SSH commands",
    "timestamp": time.time(),
}

p = "/var/lib/private/meta-ralphd/oculus.jsonl"
prev = "0" * 64
seq = -1
if os.path.isfile(p):
    with open(p) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                seq = e.get("seq", -1)
                prev = e.get("hash", "0" * 64)
            except:
                pass

seq += 1
pb = json.dumps(PAYLOAD, sort_keys=True, separators=(",", ":")).encode()
h = hashlib.sha256(prev.encode() + pb).hexdigest()
e = {"seq": seq, "prev": prev, "payload": PAYLOAD, "hash": h}

with open(p, "ab") as f:
    f.write(json.dumps(e, sort_keys=True).encode() + b"\n")
    f.flush()
    os.fsync(f.fileno())

print(f"seq={seq}  hash={h[:16]}")
