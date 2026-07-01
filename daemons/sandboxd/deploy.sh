#!/bin/bash
# sandboxd deployment — cross-compile → scp → run on dev-cx53
set -e

echo "▸ sandboxd deploy to dev-cx53"

# 1. Cross-compile for Linux
cd "$(dirname "$0")"
echo "  Building for x86_64-linux..."
zig build -Dtarget=x86_64-linux-gnu 2>/dev/null
echo "  ✅ $(ls -lh zig-out/bin/sandboxd | awk '{print $5}') binary"

# 2. Create systemd service file
cat > zig-out/bin/sandboxd.service << 'UNIT'
[Unit]
Description=sandboxd — namespace/exec enforcement daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/sandboxd --policy /etc/sandboxd/policy.json
Restart=on-failure
RestartSec=5
User=root
Group=root

[Install]
WantedBy=multi-user.target
UNIT

# 3. Create default policy
cat > zig-out/bin/policy.json << 'POLICY'
{
  "runtime": "native",
  "membranes": [
    {
      "name": "default",
      "default": "deny",
      "allow": [
        {"host": "127.0.0.1", "port": 11434, "proto": "tcp"}
      ]
    }
  ]
}
POLICY

# 4. Deploy to dev-cx53
echo "  Deploying to dev-cx53..."
scp zig-out/bin/sandboxd zig-out/bin/sandboxd.service zig-out/bin/policy.json dev-cx53:/tmp/
ssh dev-cx53 "sudo cp /tmp/sandboxd /usr/local/bin/ && \
  sudo cp /tmp/sandboxd.service /etc/systemd/system/ && \
  sudo mkdir -p /etc/sandboxd && \
  sudo cp /tmp/policy.json /etc/sandboxd/ && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable sandboxd && \
  sudo systemctl start sandboxd && \
  echo '✅ sandboxd running on dev-cx53'"

echo ""
echo "▸ Verify:"
echo "  ssh dev-cx53 'systemctl status sandboxd'"
