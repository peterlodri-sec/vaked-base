"""Mnemosyne 30-day simulation test."""
import sys, json, time, hashlib
sys.path.insert(0, "/tmp")
from mnemosyne import squash_ledger, verify_chain, is_critical_event, GENESIS_HASH

now = time.time()
day = 86400
entries = []
prev = GENESIS_HASH

# Genesis
e0 = {"seq": 0, "prev": prev, "payload": {"kind": "genesis_start", "timestamp": now - 30*day}, "hash": ""}
pb = json.dumps(e0["payload"], sort_keys=True, separators=(",",":")).encode()
e0["hash"] = hashlib.sha256(prev.encode() + pb).hexdigest()
entries.append(e0); prev = e0["hash"]

# 25 normal events over 25 days
for i in range(1, 26):
    ts = now - (30 - i) * day
    kind = "HEARTBEAT" if i % 2 == 0 else "STATE_SYNC"
    e = {"seq": i, "prev": prev, "payload": {"kind": kind, "timestamp": ts}, "hash": ""}
    pb = json.dumps(e["payload"], sort_keys=True, separators=(",",":")).encode()
    e["hash"] = hashlib.sha256(prev.encode() + pb).hexdigest()
    entries.append(e); prev = e["hash"]

# Critical error at day 20
e = {"seq": 26, "prev": prev, "payload": {"kind": "WATCHDOG_EMERGENCY_HOLD", "timestamp": now - 20*day, "severity": "CRITICAL"}, "hash": ""}
pb = json.dumps(e["payload"], sort_keys=True, separators=(",",":")).encode()
e["hash"] = hashlib.sha256(prev.encode() + pb).hexdigest()
entries.append(e); prev = e["hash"]

# 12 normal events
for i in range(27, 39):
    ts = now - (39 - i) * day * 0.4
    e = {"seq": i, "prev": prev, "payload": {"kind": "ROUTINE_CHECK", "timestamp": ts}, "hash": ""}
    pb = json.dumps(e["payload"], sort_keys=True, separators=(",",":")).encode()
    e["hash"] = hashlib.sha256(prev.encode() + pb).hexdigest()
    entries.append(e); prev = e["hash"]

path = "/tmp/mnemosyne-30d.jsonl"
with open(path, "w") as f:
    for e in entries:
        f.write(json.dumps(e, sort_keys=True) + chr(10))

print("=== 30-Day Simulated Ledger ===")
print("  Total:", len(entries))
print("  Chain:", verify_chain(entries))
print()

cutoff = now - 7*day
old = [e for e in entries if e.get("payload",{}).get("timestamp",0) < cutoff and e.get("seq",0) > 0]
old_crit = [e for e in old if is_critical_event(e)]
old_norm = [e for e in old if not is_critical_event(e)]
recent = [e for e in entries if e.get("payload",{}).get("timestamp",0) >= cutoff or e.get("seq",0) == 0]
print("  Old entries: %d (%d critical, %d normal)" % (len(old), len(old_crit), len(old_norm)))
print("  Recent: %d" % len(recent))
print()

print("=== Squash (7-day) ===")
squash_ledger(path, high_fidelity_days=7, dry_run=True)
