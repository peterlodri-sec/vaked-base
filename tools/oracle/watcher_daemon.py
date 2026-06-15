"""Root eBPF watcher daemon: unix socket -> PID-scoped bpftrace -> JSON.

Runs as root (NixOS systemd service, see hosts/dev-cx53/oracle-ebpf-watcher.nix).
The unprivileged revdev client never gains caps. parse_bpftrace + handle_request
are pure (tested); serve()/_run_bpftrace are the impure socket+exec loop.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess

DEFAULT_SOCK = "/run/oracle-watcher.sock"
_SYS_PREFIX = "tracepoint:syscalls:sys_enter_"
_SYS = re.compile(r"@syscalls\[(?P<name>[^\]]+)\]:\s*(?P<n>\d+)")
_FILE = re.compile(r"@files\[(?P<path>[^\]]+)\]:\s*\d+")


def parse_bpftrace(out: str) -> dict:
    syscalls, files = {}, []
    for m in _SYS.finditer(out):
        name = m.group("name")
        if name.startswith(_SYS_PREFIX):
            name = name[len(_SYS_PREFIX):]
        syscalls[name] = int(m.group("n"))
    for m in _FILE.finditer(out):
        files.append(m.group("path"))
    return {"syscalls": syscalls, "mmaps": [f for f in files if f.endswith(".gguf")],
            "files": files}


def _bpftrace_program(pid: int) -> str:
    return (
        f"tracepoint:syscalls:sys_enter_* /pid == {pid}/ "
        f"{{ @syscalls[probe] = count(); }} "
        f"tracepoint:syscalls:sys_enter_openat /pid == {pid}/ "
        f"{{ @files[str(args.filename)] = count(); }}"
    )


def _run_bpftrace(pid: int, duration_s: int) -> dict:
    prog = _bpftrace_program(pid)
    proc = subprocess.run(["timeout", str(duration_s), "bpftrace", "-e", prog],
                          capture_output=True, text=True)
    return parse_bpftrace(proc.stdout)


def handle_request(req: dict, *, run=_run_bpftrace) -> dict:
    pid = req.get("pid")
    dur = int(req.get("duration_s", 5))
    if not isinstance(pid, int) or pid <= 0:
        return {"ok": False, "error": f"bad pid: {pid!r}"}
    try:
        data = run(pid, dur)
    except Exception as e:  # noqa: BLE001 - daemon must never crash on a request
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, **data}


def serve(sock_path: str = DEFAULT_SOCK) -> None:  # pragma: no cover (impure loop)
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    os.chmod(sock_path, 0o660)  # group-restricted; revdev added to the socket group
    srv.listen(4)
    while True:
        conn, _ = srv.accept()
        try:
            raw = conn.recv(65536)
            resp = handle_request(json.loads(raw.decode()))
            conn.sendall(json.dumps(resp).encode())
        except Exception:  # noqa: BLE001
            try:
                conn.sendall(json.dumps({"ok": False, "error": "bad request"}).encode())
            except OSError:
                pass
        finally:
            conn.close()


if __name__ == "__main__":  # pragma: no cover
    serve()
