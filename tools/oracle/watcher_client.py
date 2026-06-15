"""Client for the root eBPF watcher daemon (revdev side; no caps needed).

Protocol: connect to the unix socket, send one JSON request line, read one JSON
response line. Request: {"pid": int, "duration_s": int}. Response:
{"ok": bool, "syscalls": {name: count}, "mmaps": [str], "files": [str], "error"?: str}.
"""
from __future__ import annotations

import json
import socket

DEFAULT_SOCK = "/run/oracle-watcher.sock"


def encode_request(*, pid: int, duration_s: int) -> bytes:
    return (json.dumps({"pid": pid, "duration_s": duration_s}) + "\n").encode()


def decode_response(raw: bytes) -> dict:
    resp = json.loads(raw.decode())
    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "watcher error"))
    return {"syscalls": resp.get("syscalls", {}),
            "mmaps": resp.get("mmaps", []),
            "files": resp.get("files", [])}


def query_watcher(sock_path: str = DEFAULT_SOCK, *, pid: int, duration_s: int,
                  timeout: float = 120.0) -> dict:
    """Impure. Returns {syscalls, mmaps, files}; raises on watcher error/unreachable."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(sock_path)
    try:
        s.sendall(encode_request(pid=pid, duration_s=duration_s))
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
        return decode_response(b"".join(chunks))
    finally:
        s.close()
