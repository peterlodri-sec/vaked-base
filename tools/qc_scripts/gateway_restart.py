#> @
"""Gateway restart — stops old instance, starts fresh."""
import subprocess, time

# Stop
subprocess.run(["systemctl", "--user", "stop", "constellation-gw"],
              capture_output=True)
time.sleep(2)

# Start minimal gateway
subprocess.run(["systemd-run", "--user", "--unit=constellation-gw",
               "python3", "/tmp/gw_mon.py"],
              capture_output=True)

time.sleep(3)

# Verify
import http.client
try:
    conn = http.client.HTTPConnection("127.0.0.1", 8081, timeout=5)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    print(f"Gateway: {resp.status} {resp.read().decode()}")
except Exception as e:
    print(f"Gateway: FAILED ({e})")
