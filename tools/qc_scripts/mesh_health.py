
"""Mesh health check — runs on all nodes and reports status."""
import subprocess, time

NODES = {
    "dev-cx53": "100.105.72.88",
    "bench-node": "100.66.205.85",
    "us-west": "100.104.181.26",
    "singapore": "100.117.253.12",
}

print("=== MESH HEALTH @ " + time.strftime("%H:%M:%S") + " ===")
for name, ip in sorted(NODES.items()):
    # Quick ping
    import os
    result = subprocess.run(["ping", "-c", "2", "-W", "3", ip],
                          capture_output=True, text=True)
    if result.returncode == 0:
        line = result.stdout.split("\n")[-2]
        rtt = line.split("=")[-1].split("/")[1] if "=" in line else "?"
        print(f"  {name:15s} {ip:16s}  {'✓ online':12s}  {rtt}ms")
    else:
        print(f"  {name:15s} {ip:16s}  {'✗ offline':12s}")
