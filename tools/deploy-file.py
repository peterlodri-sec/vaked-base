#!/usr/bin/env python3
"""deploy-file — sync a local file to dev-cx53 /var/www in one command.

NO MORE: cat file | ssh 'sudo tee /var/www/dir/index.html > /dev/null' → silent fail → mkdir → retry
INSTEAD:  deploy-file docs/website/donate.html
          deploy-file --all            # deploy all website files
          deploy-file --list           # list deployed files
"""
import subprocess, sys, os

TARGET = "dev-cx53"
WWW = "/var/www"

SITE_MAP = {
    "docs/website/constellation.html":  f"{WWW}/constellation/index.html",
    "docs/website/radio.html":          f"{WWW}/radio/index.html",
    "docs/website/status.html":         f"{WWW}/status/index.html",
    "docs/website/nav.html":            f"{WWW}/nav/index.html",
    "docs/website/donate.html":         f"{WWW}/donate/index.html",
    "docs/website/rss.html":            f"{WWW}/rss/index.html",
    "docs/website/rss.xml":             f"{WWW}/rss/index.xml",
    "docs/website/bus.html":            f"{WWW}/bus/index.html",
    "docs/website/dogfeed.html":        f"{WWW}/dogfeed/index.html",
    "docs/website/pod-monitor.html":    f"{WWW}/monitor/index.html",
    "docs/website/reflect.html":        f"{WWW}/reflect/index.html",
}


def deploy_file(local_path: str, remote_path: str = None):
    """Deploy one file to dev-cx53."""
    if remote_path is None:
        # Derive from site map or filename
        if local_path in SITE_MAP:
            remote_path = SITE_MAP[local_path]
        else:
            basename = os.path.basename(local_path).replace(".html", "")
            remote_path = f"{WWW}/{basename}/index.html"
    
    remote_dir = os.path.dirname(remote_path)
    
    # Create directory
    subprocess.run(
        ["ssh", TARGET, f"sudo mkdir -p {remote_dir}"],
        capture_output=True, timeout=5
    )
    
    # Deploy file
    with open(local_path, "rb") as f:
        content = f.read()
    
    result = subprocess.run(
        ["ssh", TARGET, f"sudo tee {remote_path} > /dev/null"],
        input=content, capture_output=True, timeout=10
    )
    
    if result.returncode == 0:
        # Verify
        verify = subprocess.run(
            ["ssh", TARGET, f"wc -c < {remote_path}"],
            capture_output=True, text=True, timeout=5
        )
        size = verify.stdout.strip()
        print(f"✅ {local_path} → {remote_path} ({size}B)")
        return True
    else:
        print(f"❌ {local_path} → FAILED")
        return False


def deploy_all():
    """Deploy all known website files."""
    ok = 0
    fail = 0
    for local, remote in SITE_MAP.items():
        if os.path.isfile(local):
            if deploy_file(local, remote):
                ok += 1
            else:
                fail += 1
        else:
            print(f"⚠️  {local} — file not found, skipping")
    print(f"\n{ok} deployed, {fail} failed")


def verify_all():
    """Verify all deployed files are accessible."""
    for remote in SITE_MAP.values():
        result = subprocess.run(
            ["ssh", TARGET, f"test -f {remote} && echo OK || echo MISSING"],
            capture_output=True, text=True, timeout=5
        )
        status = result.stdout.strip()
        symbol = "✅" if status == "OK" else "❌"
        print(f"{symbol} {remote}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "--all":
        deploy_all()
    elif cmd == "--list" or cmd == "--verify":
        verify_all()
    else:
        local = sys.argv[1]
        remote = sys.argv[2] if len(sys.argv) > 2 else None
        deploy_file(local, remote)


if __name__ == "__main__":
    main()
