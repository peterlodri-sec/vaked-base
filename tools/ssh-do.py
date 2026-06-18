#!/usr/bin/env python3
"""ssh-do — execute Python/Shell on dev-cx53 without quoting.

NO MORE: ssh dev-cx53 'python3 -c "..."' 
INSTEAD:  ssh-do script.py
          ssh-do --shell "uptime && free -h"
          ssh-do --sudo script.py
          echo "print('hello')" | ssh-do

All file transmission happens via SCP (no inline quoting).
All execution happens on the remote (no local shell interference).
"""
import subprocess, sys, os, tempfile

TARGET = "dev-cx53"


def run_remote_python(script: str, sudo: bool = False) -> int:
    """Write Python script to temp file, SCP to target, execute."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp_path = f.name
    
    remote_path = f"/tmp/sshdo_{os.path.basename(tmp_path)}.py"
    
    try:
        subprocess.run(["scp", tmp_path, f"{TARGET}:{remote_path}"],
                      check=True, capture_output=True)
        
        cmd = ["ssh", TARGET]
        if sudo:
            cmd.extend(["sudo", "python3", remote_path])
        else:
            cmd.extend(["python3", remote_path])
        
        result = subprocess.run(cmd)
        
        # Cleanup
        subprocess.run(["ssh", TARGET, "rm", "-f", remote_path],
                      capture_output=True)
        
        return result.returncode
    finally:
        os.unlink(tmp_path)


def run_remote_shell(command: str, sudo: bool = False) -> int:
    """Run a shell command on the target."""
    cmd = ["ssh", TARGET]
    if sudo:
        cmd.append("sudo")
    cmd.extend(["bash", "-c", command])
    return subprocess.run(cmd).returncode


def run_remote_file(filepath: str, sudo: bool = False) -> int:
    """SCP and execute a file on the target."""
    with open(filepath) as f:
        return run_remote_python(f.read(), sudo)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Usage:")
        print("  ssh-do script.py          # Run Python on dev-cx53")
        print("  ssh-do --sudo script.py    # Run with sudo")
        print("  ssh-do --shell 'command'   # Run shell command")
        print("  echo 'code' | ssh-do       # Pipe Python from stdin")
        sys.exit(1)
    
    sudo = False
    args = sys.argv[1:]
    
    if args[0] == "--sudo":
        sudo = True
        args = args[1:]
    
    if args[0] == "--shell":
        return run_remote_shell(args[1], sudo)
    
    if args[0] == "-":
        # Read from stdin
        script = sys.stdin.read()
        return run_remote_python(script, sudo)
    
    if os.path.isfile(args[0]):
        return run_remote_file(args[0], sudo)
    
    # Treat as inline Python
    return run_remote_python(args[0], sudo)


if __name__ == "__main__":
    sys.exit(main())
