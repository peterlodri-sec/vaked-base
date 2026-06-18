#!/usr/bin/env python3
"""gw-route — add a route to the Zig gateway in one command.

NO MORE: edit gw.zig → scp → build → kill → restart → test → 404 → debug
INSTEAD:  gw-route add /chat chat.html "text/html"
          gw-route list
          gw-route test /chat

Handles: source edit, SCP, Zig build, stop old gateway, deploy, start, verify.
"""
import subprocess, sys, os, time

TARGET = "dev-cx53"
GATEWAY_SRC = "gateway/gw_v3.zig"  # current active source
GATEWAY_BIN = "/opt/vaked/vaked-gateway"
SERVICE = "constellation-gateway"


def add_route(path: str, filename: str, content_type: str = "text/html"):
    """Add a route to the gateway source, build, deploy, verify."""
    
    # 1. Add route to source
    route_line = f'    .{{ .path = "{path}", .content_type = "{content_type}", .file_path = "/var/www/{filename}/index.html", .inline_content = null }},'
    
    with open(GATEWAY_SRC) as f:
        src = f.read()
    
    if path in src:
        print(f"Route {path} already exists in source")
    else:
        # Insert before mesh.json entry
        src = src.replace(
            '    .{ .path = "/mesh.json"',
            f'{route_line}\n    .{{ .path = "/mesh.json"'
        )
        with open(GATEWAY_SRC, "w") as f:
            f.write(src)
        print(f"Added {path} to {GATEWAY_SRC}")
    
    # 2. SCP to target
    subprocess.run(["scp", GATEWAY_SRC, f"{TARGET}:/tmp/gw_route.zig"],
                  check=True, capture_output=True)
    print(f"SCP'd to {TARGET}:/tmp/gw_route.zig")
    
    # 3. Build
    result = subprocess.run(
        ["ssh", TARGET, "cd /tmp && zig build-exe gw_route.zig -O ReleaseFast -fstrip --name vaked-gw-new"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode != 0:
        print("BUILD FAILED:")
        for line in result.stderr.split("\n")[-5:]:
            print(f"  {line}")
        return 1
    
    print("Build successful")
    
    # 4. Stop old, deploy new, start
    subprocess.run(["ssh", TARGET, f"systemctl --user stop {SERVICE}"],
                  capture_output=True, timeout=10)
    time.sleep(1)
    subprocess.run(["ssh", TARGET, "fuser -k 8081/tcp 2>/dev/null; true"],
                  capture_output=True, timeout=5)
    time.sleep(1)
    subprocess.run(["ssh", TARGET, f"sudo cp -f /tmp/vaked-gw-new {GATEWAY_BIN}"],
                  capture_output=True, timeout=5)
    subprocess.run(["ssh", TARGET, f"systemctl --user start {SERVICE}"],
                  capture_output=True, timeout=5)
    time.sleep(2)
    
    # 5. Verify
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "--connect-timeout", "10", "--max-time", "20",
         f"https://constellation.vaked.dev{path}"],
        capture_output=True, text=True, timeout=15
    )
    
    code = result.stdout.strip()
    if code == "200":
        print(f"✅ {path} → 200 OK")
    else:
        print(f"❌ {path} → {code}")
    
    return 0 if code == "200" else 1


def list_routes():
    """List all routes in the gateway source."""
    with open(GATEWAY_SRC) as f:
        src = f.read()
    
    import re
    routes = re.findall(r'\.path = "([^"]+)"', src)
    for r in routes:
        print(f"  {r}")
    print(f"\n{routes.__len__()} routes total")


def test_route(path: str):
    """Test if a route returns 200."""
    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "--connect-timeout", "10", "--max-time", "20",
         f"https://constellation.vaked.dev{path}"],
        capture_output=True, text=True, timeout=15
    )
    print(f"{path} → {result.stdout.strip()}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Usage: gw-route add <path> <dir> [content-type]")
        print("       gw-route list")
        print("       gw-route test <path>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "add":
        path = sys.argv[2]
        filename = sys.argv[3] if len(sys.argv) > 3 else path.lstrip("/")
        ct = sys.argv[4] if len(sys.argv) > 4 else "text/html"
        sys.exit(add_route(path, filename, ct))
    
    elif cmd == "list":
        list_routes()
    
    elif cmd == "test":
        test_route(sys.argv[2])
    
    elif cmd == "deploy-file":
        # Deploy an HTML file and create its directory
        local_file = sys.argv[2]
        remote_path = sys.argv[3] if len(sys.argv) > 3 else f"/var/www/{os.path.basename(local_file).replace('.html','')}/index.html"
        remote_dir = os.path.dirname(remote_path)
        
        subprocess.run(["ssh", TARGET, f"sudo mkdir -p {remote_dir}"],
                      capture_output=True, timeout=5)
        
        with open(local_file) as f:
            content = f.read()
        
        subprocess.run(
            ["ssh", TARGET, f"sudo tee {remote_path} > /dev/null"],
            input=content.encode(), capture_output=True, timeout=10
        )
        
        print(f"Deployed {local_file} → {TARGET}:{remote_path}")


if __name__ == "__main__":
    main()
