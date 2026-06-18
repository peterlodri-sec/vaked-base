#!/usr/bin/env python3
"""zigpush — SCP to dev-cx53, apply fixes, build, report.

Usage: zigpush <name> <file.zig>
Copies file to dev-cx53, runs zigfix, builds with zig 0.16.
"""
import subprocess, sys, os

TARGET = "dev-cx53"
REMOTE_DIR = "/tmp"

def main():
    if len(sys.argv) < 3:
        print("Usage: zigpush <name> <file.zig>")
        sys.exit(1)
    
    name = sys.argv[1]
    path = sys.argv[2]
    
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        sys.exit(1)
    
    # Step 1: SCP
    remote_path = f"{REMOTE_DIR}/{name}.zig"
    print(f"→ scp {path} → {TARGET}:{remote_path}")
    subprocess.run(["scp", path, f"{TARGET}:{remote_path}"], check=True)
    
    # Step 2: Build
    binary = f"vaked-{name}"
    print(f"→ zig build-exe {name}.zig -O ReleaseFast -fstrip --name {binary}")
    
    result = subprocess.run(
        ["ssh", TARGET, f"cd {REMOTE_DIR} && zig build-exe {name}.zig -O ReleaseFast -fstrip --name {binary}"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode == 0:
        # Check size
        size_result = subprocess.run(
            ["ssh", TARGET, f"ls -lh {REMOTE_DIR}/{binary}"],
            capture_output=True, text=True
        )
        size = size_result.stdout.strip().split()[-4] if size_result.stdout else "?"
        print(f"✅ {binary} · {size}")
    else:
        print(f"❌ BUILD FAILED:")
        for line in result.stderr.split('\n')[:5]:
            if 'error' in line.lower():
                print(f"   {line[:120]}")
        sys.exit(1)

if __name__ == "__main__":
    main()
