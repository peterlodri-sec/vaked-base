"""agent_sandboxd.daemon — HTTP daemon for the process + filesystem membrane.

Exposes the sandboxd control plane as a minimal HTTP server (stdlib
``http.server``). This is the reference daemon shape for the Python oracle;
the Zig port replaces this with a TCP listener on the same HTTP API.

**Endpoints:**

  ``POST /spawn``
      Spawn a child process inside an isolated namespace boundary.
      Body (JSON):
        ``command``            — list[str], the argv to exec
        ``filesystem_policy``  — FilesystemPolicy dict
                                 (allowed_read, allowed_write, grant)
        ``process_policy``     — ProcessPolicy dict
                                 (grant, max_pids, cpu_weight, mem_max_bytes, ...)
        ``capability_token``   — str | null, the preceptord grant token
                                 (reference phase: allow-all + log)
        ``agent_id``           — str, used as cgroup leaf + log key
        ``dry_run``            — bool (default false), print plan, no exec

      Response (JSON):
        ``status``   — "ok" | "error" | "denied"
        ``pid``      — int (only on ok)
        ``detail``   — str

  ``POST /kill``
      Terminate a supervised process.
      Body (JSON):  ``pid`` (int), ``agent_id`` (str), ``signal`` (int, default 15)
      Response:     ``status``, ``detail``

  ``GET /status/<pid>``
      Return the status of a supervised process.
      Response:     ``pid``, ``state`` ("running"|"exited"|"unknown"), ``returncode``

  ``GET /health``
      Liveness probe. Returns ``{"status": "ok"}``.

**Process supervision:**

  Spawned pids are tracked in :attr:`SandboxDaemon._processes`. The daemon
  does not block waiting for children; callers poll ``/status/<pid>`` or wait
  for eventd audit events. A ``SIGCHLD`` reaper would be the Zig implementation;
  the Python reference uses ``subprocess.Popen.poll()`` on status queries.

**Security posture (reference phase):**

  - capability_token is accepted but NOT verified (no preceptord); every
    spawn is logged via eventd (allow-all + log).
  - The deny path is wired: if process_policy.grant == "none" the spawn is
    refused and logged as ``action="deny"``.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from .cgroup import CgroupSpec, apply_cgroup_limits
from .eventd import access_event, kill_event, spawn_event, testify
from .namespace import NamespaceSpec, enter_namespace
from .policy import (
    FilesystemPolicy, FsGrant, PolicyDecision, ProcessGrant, ProcessPolicy,
    decide_path,
)


# --------------------------------------------------------------------------- #
# Request / result types                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class SpawnRequest:
    """Parsed /spawn request body."""
    command: list                     # list[str]
    agent_id: str
    filesystem_policy: FilesystemPolicy
    process_policy: ProcessPolicy
    capability_token: "str | None" = None
    dry_run: bool = False
    env: dict = field(default_factory=dict)


@dataclass
class SpawnResult:
    """Result of a /spawn operation."""
    status: str                       # "ok" | "denied" | "error"
    pid: "int | None" = None
    detail: str = ""
    entry: "dict | None" = None       # the eventd chain entry


@dataclass
class ProcessStatus:
    """Status of a supervised process."""
    pid: int
    state: str                        # "running" | "exited" | "unknown"
    returncode: "int | None" = None


# --------------------------------------------------------------------------- #
# Daemon core                                                                   #
# --------------------------------------------------------------------------- #

class SandboxDaemon:
    """The sandboxd reference daemon.

    Manages supervised processes, applies policy, and drives namespace / cgroup
    machinery. Thread-safe for the multi-threaded HTTP server.
    """

    def __init__(self, *, eventd_log: str, cgroup_root: str = "/sys/fs/cgroup",
                 dry_run: bool = False):
        """
        Args:
          eventd_log: path to the eventd JSONL log file.
          cgroup_root: root of the cgroup-v2 hierarchy. Pass a temp dir in CI.
          dry_run: global dry-run flag (overrides per-request dry_run).
        """
        self.eventd_log = eventd_log
        self.cgroup_root = cgroup_root
        self.dry_run = dry_run
        self._processes: dict[int, subprocess.Popen] = {}   # pid → Popen
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(eventd_log)), exist_ok=True)

    # ----------------------------------------------------------------------- #
    # spawn                                                                     #
    # ----------------------------------------------------------------------- #

    def spawn(self, req: SpawnRequest) -> SpawnResult:
        """Spawn a child process inside the isolation boundary.

        1. Check process grant (deny if grant == none).
        2. Write-ahead the spawn event to eventd.
        3. Apply cgroup-v2 limits.
        4. Enter the namespace boundary and exec the command.
        5. Track the pid.
        """
        dry_run = self.dry_run or req.dry_run

        # --- policy check: process grant ------------------------------------ #
        if req.process_policy.grant == ProcessGrant.none:
            entry = testify(self.eventd_log, spawn_event(
                req.agent_id, req.command,
                req.filesystem_policy.grant.value,
                req.process_policy.grant.value,
                req.capability_token,
                action="deny",
                reason="process grant=none — no spawn capability"))
            return SpawnResult(
                status="denied",
                detail="process grant=none: spawn refused",
                entry=entry)

        # --- write-ahead audit event ---------------------------------------- #
        entry = testify(self.eventd_log, spawn_event(
            req.agent_id, req.command,
            req.filesystem_policy.grant.value,
            req.process_policy.grant.value,
            req.capability_token,
            action="allow",
            reason="reference phase allow-all (preceptord not yet present)"))

        # --- cgroup limits -------------------------------------------------- #
        cg_spec = CgroupSpec(
            agent_id=req.agent_id,
            mem_max_bytes=req.process_policy.mem_max_bytes,
            pids_max=req.process_policy.max_pids,
            cpu_quota_us=None,    # cpu_weight → cpu.max mapping is daemon-impl detail
        )
        if not dry_run:
            apply_cgroup_limits(cg_spec, cgroup_root=self.cgroup_root)

        # --- namespace entry ------------------------------------------------ #
        ns_spec = NamespaceSpec(
            command=req.command,
            env=req.env,
        )
        # Bind-mount declared read paths (read-only) and write paths (bind rw).
        # In the reference impl we pass them through directly; the Zig daemon
        # will construct an overlay rootfs + pivot_root instead.
        for p in req.filesystem_policy.allowed_read:
            ns_spec.bind_mounts[p] = p
        for p in req.filesystem_policy.allowed_write:
            ns_spec.bind_mounts[p] = p

        result = enter_namespace(ns_spec, dry_run=dry_run)

        if dry_run:
            return SpawnResult(
                status="ok", pid=None,
                detail="dry-run: plan printed, no exec",
                entry=entry)

        if not result.entered:
            return SpawnResult(
                status="error",
                detail=result.detail or result.error or "namespace entry failed",
                entry=entry)

        with self._lock:
            # Popen object is not returned by enter_namespace (it uses unshare CLI);
            # for the reference impl we track by pid only — the Popen is owned by
            # enter_namespace. In the HTTP daemon we store a lightweight sentinel.
            self._processes[result.pid] = _PidSentinel(result.pid)

        return SpawnResult(
            status="ok", pid=result.pid,
            detail=result.detail,
            entry=entry)

    # ----------------------------------------------------------------------- #
    # kill                                                                      #
    # ----------------------------------------------------------------------- #

    def kill(self, pid: int, agent_id: str,
             sig: int = signal.SIGTERM) -> dict:
        """Terminate a supervised process.

        Write-ahead the kill event to eventd before signalling.
        Returns ``{"status": "ok"|"error", "detail": str}``.
        """
        testify(self.eventd_log, kill_event(
            agent_id=agent_id, pid=pid, signal=sig,
            reason="operator-requested termination"))

        try:
            os.kill(pid, sig)
            with self._lock:
                self._processes.pop(pid, None)
            return {"status": "ok", "detail": "sent signal %d to pid %d" % (sig, pid)}
        except ProcessLookupError:
            return {"status": "ok", "detail": "pid %d not found (already exited)" % pid}
        except PermissionError as e:
            return {"status": "error", "detail": "kill failed: %s" % e}

    # ----------------------------------------------------------------------- #
    # status                                                                    #
    # ----------------------------------------------------------------------- #

    def status(self, pid: int) -> ProcessStatus:
        """Poll the status of a supervised process."""
        with self._lock:
            sentinel = self._processes.get(pid)

        if sentinel is None:
            # Not tracked — check if the pid exists in the kernel.
            try:
                os.kill(pid, 0)   # signal 0 = probe only
                return ProcessStatus(pid=pid, state="running")
            except ProcessLookupError:
                return ProcessStatus(pid=pid, state="unknown")
            except PermissionError:
                # Pid exists but we don't own it — still running.
                return ProcessStatus(pid=pid, state="running")

        rc = sentinel.poll()
        if rc is None:
            return ProcessStatus(pid=pid, state="running")
        with self._lock:
            self._processes.pop(pid, None)
        return ProcessStatus(pid=pid, state="exited", returncode=rc)

    # ----------------------------------------------------------------------- #
    # filesystem access decision (for callers that want the policy oracle)     #
    # ----------------------------------------------------------------------- #

    def check_access(self, agent_id: str, policy: FilesystemPolicy,
                     path: str, mode: str = "read",
                     *, log: bool = True) -> PolicyDecision:
        """Make a filesystem access decision and optionally testify it to eventd.

        This is the policy oracle path — callers (e.g. a FUSE layer in the Zig
        impl) can query sandboxd for each file operation. The Python reference
        drives policy directly via :func:`decide_path`.
        """
        decision = decide_path(policy, path, mode)
        if log:
            testify(self.eventd_log, access_event(
                agent_id=agent_id, path=path, mode=mode,
                action="allow" if decision.allowed else "deny",
                reason=decision.reason))
        return decision


# --------------------------------------------------------------------------- #
# Lightweight pid sentinel (no Popen available from enter_namespace)           #
# --------------------------------------------------------------------------- #

class _PidSentinel:
    """Minimal process handle tracking a pid spawned via unshare(1)."""

    def __init__(self, pid: int):
        self.pid = pid
        self._returncode: "int | None" = None

    def poll(self) -> "int | None":
        if self._returncode is not None:
            return self._returncode
        try:
            wpid, status = os.waitpid(self.pid, os.WNOHANG)
            if wpid == self.pid:
                self._returncode = os.waitstatus_to_exitcode(status)
                return self._returncode
        except ChildProcessError:
            # Not our child (unshare forks) — probe via signal 0.
            pass
        except OSError:
            pass
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            self._returncode = -1
            return self._returncode
        return None


# --------------------------------------------------------------------------- #
# HTTP server                                                                   #
# --------------------------------------------------------------------------- #

def _make_handler(daemon: SandboxDaemon):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass   # suppress default access log; eventd is the audit trail

        def _send_json(self, code: int, body: dict) -> None:
            data = json.dumps(body, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> "dict | None":
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, ValueError):
                return None

        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if self.path.startswith("/status/"):
                try:
                    pid = int(self.path[len("/status/"):])
                except ValueError:
                    self._send_json(400, {"error": "invalid pid"})
                    return
                st = daemon.status(pid)
                self._send_json(200, {
                    "pid": st.pid, "state": st.state,
                    "returncode": st.returncode})
                return
            self._send_json(404, {"error": "not found"})

        def do_POST(self):
            body = self._read_json()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return

            if self.path == "/spawn":
                try:
                    req = _parse_spawn_request(body)
                except (KeyError, ValueError) as e:
                    self._send_json(400, {"error": "bad request: %s" % e})
                    return
                result = daemon.spawn(req)
                code = 200 if result.status == "ok" else (
                    403 if result.status == "denied" else 500)
                self._send_json(code, {
                    "status": result.status,
                    "pid": result.pid,
                    "detail": result.detail})
                return

            if self.path == "/kill":
                try:
                    pid = int(body["pid"])
                    agent_id = str(body.get("agent_id", "unknown"))
                    sig = int(body.get("signal", signal.SIGTERM))
                except (KeyError, ValueError) as e:
                    self._send_json(400, {"error": "bad request: %s" % e})
                    return
                resp = daemon.kill(pid, agent_id, sig)
                code = 200 if resp["status"] == "ok" else 500
                self._send_json(code, resp)
                return

            self._send_json(404, {"error": "not found"})

    return Handler


def _parse_spawn_request(body: dict) -> SpawnRequest:
    """Deserialise a /spawn request body into a :class:`SpawnRequest`."""
    command = list(body["command"])
    agent_id = str(body.get("agent_id", "default"))
    capability_token = body.get("capability_token")
    dry_run = bool(body.get("dry_run", False))
    env = dict(body.get("env", {}))

    # filesystem_policy
    fp = body.get("filesystem_policy", {})
    fs_policy = FilesystemPolicy(
        grant=FsGrant(fp.get("grant", "none")),
        allowed_read=[str(p) for p in fp.get("allowed_read", [])],
        allowed_write=[str(p) for p in fp.get("allowed_write", [])],
    )

    # process_policy
    pp = body.get("process_policy", {})
    proc_policy = ProcessPolicy(
        grant=ProcessGrant(pp.get("grant", "none")),
        max_pids=pp.get("max_pids"),
        cpu_weight=pp.get("cpu_weight"),
        mem_max_bytes=pp.get("mem_max_bytes"),
        io_max_rbps=pp.get("io_max_rbps"),
        io_max_wbps=pp.get("io_max_wbps"),
    )

    return SpawnRequest(
        command=command, agent_id=agent_id,
        filesystem_policy=fs_policy, process_policy=proc_policy,
        capability_token=capability_token, dry_run=dry_run, env=env)


def run_server(daemon: SandboxDaemon, host: str = "127.0.0.1",
               port: int = 7240) -> None:
    """Run the sandboxd HTTP daemon (blocking)."""
    handler = _make_handler(daemon)
    server = HTTPServer((host, port), handler)
    print("[sandboxd] listening on %s:%d" % (host, port))
    print("[sandboxd] eventd log: %s" % daemon.eventd_log)
    print("[sandboxd] cgroup root: %s" % daemon.cgroup_root)
    if daemon.dry_run:
        print("[sandboxd] dry-run mode: namespace/cgroup calls will be printed, not executed")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
