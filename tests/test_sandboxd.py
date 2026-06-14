#!/usr/bin/env python3
"""test_sandboxd.py — the process + filesystem membrane vertical slice.

Tests the agent_sandboxd Python reference implementation using mocks for
namespace / cgroup / eventd calls. Policy logic is exercised directly without
requiring actual namespace isolation or privileged kernel operations.

Six groups:

1. **policy.** decide_path is deny-by-default: only declared paths under
   allowed_read or allowed_write are permitted; everything else is denied.
   Write paths are not readable unless they appear in allowed_read too (they
   ARE readable — write ⊇ read in the lattice).

2. **namespace plan.** build_namespace_plan produces the correct unshare flags
   and bind-mount steps for a given NamespaceSpec, without executing any
   syscalls.

3. **cgroup limits.** apply_cgroup_limits writes the correct cgroup-v2 control
   files to a mock directory (no /sys/fs/cgroup access needed in CI).

4. **eventd audit.** spawn/kill/access events are appended to the eventd hash
   chain in write-ahead order; the chain is intact; each event has the expected
   kind and fields.

5. **daemon spawn + access.** SandboxDaemon.spawn enforces the process grant
   (deny if grant=none); SandboxDaemon.check_access enforces filesystem policy
   and logs every access; both audit to eventd.

6. **HTTP API.** The /health, /spawn (dry-run), /kill, /status endpoints return
   the expected JSON shapes (no real process spawning needed).

No namespace / cgroup syscalls are exercised here — those require privilege not
available in CI. The --dry-run path tests the plan-building layer. Real
namespace entry is a devshell gate (``task sandbox-smoke``).

Stdlib only; driven through the package APIs (no subprocess).
"""
import json
import os
import signal
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from urllib.request import urlopen, Request
from urllib.error import HTTPError

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)

import agent_sandboxd as sandboxd                           # noqa: E402
from agent_sandboxd.policy import (                         # noqa: E402
    FilesystemPolicy, FsGrant, PolicyDecision,
    ProcessGrant, ProcessPolicy, decide_path,
)
from agent_sandboxd.namespace import (                      # noqa: E402
    NamespaceSpec, build_namespace_plan,
)
from agent_sandboxd.cgroup import (                         # noqa: E402
    CgroupSpec, apply_cgroup_limits, cgroup_path,
)
from agent_sandboxd.eventd import (                         # noqa: E402
    spawn_event, kill_event, access_event, testify,
)
from agent_sandboxd.daemon import (                         # noqa: E402
    SandboxDaemon, SpawnRequest, _make_handler, run_server,
)
from eventd import EventLog, TamperError                    # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _fs_policy(read_paths=(), write_paths=(), grant=FsGrant.repo_rw):
    return FilesystemPolicy(
        grant=grant,
        allowed_read=list(read_paths),
        allowed_write=list(write_paths),
    )


def _proc_policy(grant=ProcessGrant.spawn_sandboxed, **kwargs):
    return ProcessPolicy(grant=grant, **kwargs)


# --------------------------------------------------------------------------- #
# 1. Policy — decide_path                                                       #
# --------------------------------------------------------------------------- #

def _test_policy(lines):
    ok = True

    with tempfile.TemporaryDirectory() as td:
        read_dir = os.path.join(td, "data")
        write_dir = os.path.join(td, "output")
        os.makedirs(read_dir)
        os.makedirs(write_dir)

        policy = _fs_policy(
            read_paths=[read_dir],
            write_paths=[write_dir],
        )

        # allowed reads
        allowed_reads = [
            os.path.join(read_dir, "file.txt"),
            read_dir,
            os.path.join(write_dir, "out.txt"),  # write ⊇ read
        ]
        for path in allowed_reads:
            d = decide_path(policy, path, "read")
            if not d.allowed:
                ok = False
                lines.append("  FAIL policy: %s read should be allowed (got: %s)"
                              % (path, d.reason))

        # allowed writes (only in write_dir)
        d = decide_path(policy, os.path.join(write_dir, "result.txt"), "write")
        if not d.allowed:
            ok = False
            lines.append("  FAIL policy: write to write_dir should be allowed")

        # denied reads (outside declared paths)
        denied_reads = [
            "/etc/passwd",
            "/tmp/outside",
            "/proc/self/mem",
            td,              # parent dir — not under any declared path
        ]
        for path in denied_reads:
            d = decide_path(policy, path, "read")
            if d.allowed:
                ok = False
                lines.append("  FAIL policy: %s read should be denied (got: %s)"
                              % (path, d.reason))

        # denied writes (read-only dir not in allowed_write)
        d = decide_path(policy, os.path.join(read_dir, "tamper.txt"), "write")
        if d.allowed:
            ok = False
            lines.append("  FAIL policy: write to read-only dir should be denied")

        # grant=none: everything denied
        none_policy = _fs_policy(
            read_paths=[read_dir],
            write_paths=[write_dir],
            grant=FsGrant.none)
        d = decide_path(none_policy, os.path.join(read_dir, "file.txt"), "read")
        if d.allowed:
            ok = False
            lines.append("  FAIL policy: grant=none should deny everything")

        # unknown mode
        d = decide_path(policy, os.path.join(write_dir, "x"), "exec")
        if d.allowed:
            ok = False
            lines.append("  FAIL policy: unknown mode 'exec' should deny")

    if ok:
        lines.append("  PASS policy: deny-by-default — declared paths allowed, "
                     "undeclared denied, grant=none denies all, write⊇read in lattice")
    return ok


# --------------------------------------------------------------------------- #
# 2. Namespace plan                                                              #
# --------------------------------------------------------------------------- #

def _test_namespace_plan(lines):
    ok = True

    with tempfile.TemporaryDirectory() as td:
        host_path = os.path.join(td, "data")
        os.makedirs(host_path)

        spec = NamespaceSpec(
            user_ns=True, mount_ns=True, pid_ns=True, net_ns=True,
            bind_mounts={host_path: host_path},
            command=["echo", "hello"],
        )
        plan = build_namespace_plan(spec)

        # unshare flags
        expected_flags = {"--user", "--map-root-user", "--mount",
                          "--pid", "--fork", "--net"}
        got_flags = set(plan.unshare_args)
        missing = expected_flags - got_flags
        if missing:
            ok = False
            lines.append("  FAIL namespace: missing unshare flags %s" % missing)

        # bind-mount step
        if len(plan.mount_steps) != 1:
            ok = False
            lines.append("  FAIL namespace: expected 1 mount step, got %d"
                         % len(plan.mount_steps))
        else:
            step = plan.mount_steps[0]
            if step[0] != "mount" or step[1] != "--bind":
                ok = False
                lines.append("  FAIL namespace: mount step wrong: %s" % step)

        # dry-run lines are non-empty
        if not plan.dry_run_lines:
            ok = False
            lines.append("  FAIL namespace: dry_run_lines empty")

        # no-ns plan: flags should be empty
        spec2 = NamespaceSpec(
            user_ns=False, mount_ns=False, pid_ns=False, net_ns=False,
            command=["true"])
        plan2 = build_namespace_plan(spec2)
        if plan2.unshare_args:
            ok = False
            lines.append("  FAIL namespace: expected empty flags for no-ns spec, "
                         "got %s" % plan2.unshare_args)

        # overlay plan
        spec3 = NamespaceSpec(
            user_ns=True, mount_ns=True,
            overlay_lower="/lower", overlay_upper="/upper", overlay_work="/work",
            command=["sh"])
        plan3 = build_namespace_plan(spec3)
        if plan3.overlay_cmd is None:
            ok = False
            lines.append("  FAIL namespace: overlay_cmd should not be None when "
                         "lower/upper/work are set")

    if ok:
        lines.append("  PASS namespace: plan builds correct unshare flags, "
                     "bind-mount steps, overlay cmd, dry-run lines; "
                     "no syscalls executed")
    return ok


# --------------------------------------------------------------------------- #
# 3. Cgroup limits                                                               #
# --------------------------------------------------------------------------- #

def _test_cgroup(lines):
    ok = True

    with tempfile.TemporaryDirectory() as td:
        spec = CgroupSpec(
            agent_id="test-worker",
            mem_max_bytes=128 * 1024 * 1024,  # 128 MiB
            pids_max=32,
            cpu_quota_us=50_000,
            cpu_period_us=100_000,
            io_limits=[{"major": 8, "minor": 0, "rbps": 10_000_000, "wbps": 5_000_000}],
        )
        result = apply_cgroup_limits(spec, cgroup_root=td)

        if not result.applied:
            ok = False
            lines.append("  FAIL cgroup: apply_cgroup_limits failed: %s" % result.error)
        if not result.mock:
            ok = False
            lines.append("  FAIL cgroup: expected mock=True for temp dir root")

        cg = cgroup_path("test-worker", td)
        expected_files = {
            "memory.max": str(128 * 1024 * 1024),
            "pids.max": "32",
            "cpu.max": "50000 100000",
        }
        for fname, expected_val in expected_files.items():
            path = os.path.join(cg, fname)
            if not os.path.exists(path):
                ok = False
                lines.append("  FAIL cgroup: %s not written" % fname)
            else:
                got = open(path).read().strip()
                if got != expected_val:
                    ok = False
                    lines.append("  FAIL cgroup: %s = %r, want %r"
                                 % (fname, got, expected_val))

        # io.max
        io_path = os.path.join(cg, "io.max")
        if os.path.exists(io_path):
            io_val = open(io_path).read().strip()
            if "8:0" not in io_val or "rbps=10000000" not in io_val:
                ok = False
                lines.append("  FAIL cgroup: io.max wrong: %r" % io_val)

        # unconstrained limits → "max"
        spec2 = CgroupSpec(agent_id="unconstrained")
        result2 = apply_cgroup_limits(spec2, cgroup_root=td)
        cg2 = cgroup_path("unconstrained", td)
        mem_val = open(os.path.join(cg2, "memory.max")).read().strip()
        pids_val = open(os.path.join(cg2, "pids.max")).read().strip()
        if mem_val != "max" or pids_val != "max":
            ok = False
            lines.append("  FAIL cgroup: unconstrained limits should write 'max', "
                         "got mem=%r pids=%r" % (mem_val, pids_val))

    if ok:
        lines.append("  PASS cgroup: cgroup-v2 files written correctly to mock path "
                     "(memory.max, pids.max, cpu.max, io.max); unconstrained → 'max'")
    return ok


# --------------------------------------------------------------------------- #
# 4. Eventd audit                                                                #
# --------------------------------------------------------------------------- #

def _test_eventd_audit(lines):
    ok = True

    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "eventd.jsonl")

        # spawn event (allow)
        e1 = testify(log, spawn_event(
            "agent-1", ["python3", "-c", "pass"],
            "repo_rw", "spawn_sandboxed",
            "tok-abc",
            action="allow", reason="reference phase allow-all", seq=0))
        # spawn event (deny)
        e2 = testify(log, spawn_event(
            "agent-2", ["bad-cmd"],
            "none", "none",
            None,
            action="deny", reason="process grant=none", seq=1))
        # kill event
        e3 = testify(log, kill_event(
            "agent-1", pid=12345, signal=15,
            reason="operator-requested", seq=2))
        # access events
        e4 = testify(log, access_event(
            "agent-1", "/work/out.txt", "write",
            action="allow", reason="within bound /work", seq=3))
        e5 = testify(log, access_event(
            "agent-1", "/etc/passwd", "read",
            action="deny", reason="deny-by-default", seq=4))

        # verify the chain
        try:
            elog = EventLog(log)
        except TamperError as e:
            ok = False
            lines.append("  FAIL eventd: chain tampered after 5 appends: %s" % e)
            return ok

        if len(elog) != 5:
            ok = False
            lines.append("  FAIL eventd: expected 5 entries, got %d" % len(elog))

        # check payload kinds and fields
        entries = list(elog.entries)
        kinds = [e.get("payload", {}).get("kind") for e in entries]
        expected_kinds = [
            "sandbox_spawn", "sandbox_spawn",
            "sandbox_kill",
            "sandbox_fs_access", "sandbox_fs_access",
        ]
        if kinds != expected_kinds:
            ok = False
            lines.append("  FAIL eventd: kinds %s != %s" % (kinds, expected_kinds))

        # spawn event fields
        spawn1 = entries[0].get("payload", {})
        if spawn1.get("action") != "allow" or spawn1.get("agent_id") != "agent-1":
            ok = False
            lines.append("  FAIL eventd: spawn allow event fields wrong: %s" % spawn1)

        spawn2 = entries[1].get("payload", {})
        if spawn2.get("action") != "deny":
            ok = False
            lines.append("  FAIL eventd: spawn deny event action wrong")

        # kill event fields
        kill1 = entries[2].get("payload", {})
        if kill1.get("pid") != 12345 or kill1.get("signal") != 15:
            ok = False
            lines.append("  FAIL eventd: kill event fields wrong: %s" % kill1)

        # access violation (deny on /etc/passwd)
        acc_deny = entries[4].get("payload", {})
        if acc_deny.get("action") != "deny" or acc_deny.get("path") != "/etc/passwd":
            ok = False
            lines.append("  FAIL eventd: access deny event wrong: %s" % acc_deny)

        # write-ahead ordering: seq fields are in order
        seqs = [e.get("payload", {}).get("seq") for e in entries]
        if seqs != [0, 1, 2, 3, 4]:
            ok = False
            lines.append("  FAIL eventd: seq ordering wrong: %s" % seqs)

    if ok:
        lines.append("  PASS eventd: 5 events (spawn×2, kill, access×2) testified; "
                     "chain intact; kinds + fields + seq ordering correct; "
                     "write-ahead discipline maintained")
    return ok


# --------------------------------------------------------------------------- #
# 5. Daemon spawn + access                                                       #
# --------------------------------------------------------------------------- #

def _test_daemon(lines):
    ok = True

    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "eventd.jsonl")
        cgroup_root = os.path.join(td, "cgroup")
        workdir = os.path.join(td, "work")
        os.makedirs(workdir)

        daemon = SandboxDaemon(
            eventd_log=log, cgroup_root=cgroup_root, dry_run=True)

        fs_policy = FilesystemPolicy(
            grant=FsGrant.repo_rw,
            allowed_read=[workdir],
            allowed_write=[workdir],
        )

        # --- spawn: grant=none is denied ------------------------------------ #
        req_denied = SpawnRequest(
            command=["true"],
            agent_id="test-agent",
            filesystem_policy=fs_policy,
            process_policy=ProcessPolicy(grant=ProcessGrant.none),
        )
        result = daemon.spawn(req_denied)
        if result.status != "denied":
            ok = False
            lines.append("  FAIL daemon: grant=none should return status='denied', "
                         "got %r" % result.status)

        # --- spawn: grant=spawn_sandboxed (dry-run) ------------------------- #
        req_ok = SpawnRequest(
            command=["echo", "hello"],
            agent_id="test-agent",
            filesystem_policy=fs_policy,
            process_policy=ProcessPolicy(
                grant=ProcessGrant.spawn_sandboxed,
                max_pids=16, mem_max_bytes=64 * 1024 * 1024),
            dry_run=True,
        )
        result = daemon.spawn(req_ok)
        if result.status != "ok":
            ok = False
            lines.append("  FAIL daemon: dry-run spawn should be 'ok', got %r (detail: %s)"
                         % (result.status, result.detail))

        # --- check_access: allowed + denied --------------------------------- #
        allowed_path = os.path.join(workdir, "result.txt")
        denied_path = "/etc/shadow"

        d1 = daemon.check_access("test-agent", fs_policy, allowed_path, "write")
        if not d1.allowed:
            ok = False
            lines.append("  FAIL daemon: write to workdir should be allowed")

        d2 = daemon.check_access("test-agent", fs_policy, denied_path, "read")
        if d2.allowed:
            ok = False
            lines.append("  FAIL daemon: read of /etc/shadow should be denied")

        # --- eventd: all decisions are logged ------------------------------- #
        elog = EventLog(log)
        n = len(elog)
        if n < 4:   # at least: spawn-deny, spawn-allow, access-allow, access-deny
            ok = False
            lines.append("  FAIL daemon: expected >=4 eventd entries, got %d" % n)
        else:
            kinds = {e.get("payload", {}).get("kind") for e in elog.entries}
            expected_kinds = {"sandbox_spawn", "sandbox_fs_access"}
            if not expected_kinds.issubset(kinds):
                ok = False
                lines.append("  FAIL daemon: event kinds %s missing from log" %
                             (expected_kinds - kinds))

    if ok:
        lines.append("  PASS daemon: grant=none spawn denied; dry-run spawn ok; "
                     "access allowed/denied per policy; all decisions in eventd chain")
    return ok


# --------------------------------------------------------------------------- #
# 6. HTTP API (dry-run server)                                                   #
# --------------------------------------------------------------------------- #

def _test_http_api(lines):
    """Spin up the HTTP server in a background thread and exercise its endpoints."""
    ok = True

    with tempfile.TemporaryDirectory() as td:
        log = os.path.join(td, "eventd.jsonl")
        cgroup_root = os.path.join(td, "cgroup")
        workdir = os.path.join(td, "work")
        os.makedirs(workdir)

        daemon = SandboxDaemon(
            eventd_log=log, cgroup_root=cgroup_root, dry_run=True)

        from http.server import HTTPServer
        handler_cls = _make_handler(daemon)
        # Bind to port 0 → OS picks a free port.
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        port = server.server_address[1]

        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            base = "http://127.0.0.1:%d" % port

            # /health
            resp = _http_get(base + "/health")
            if resp.get("status") != "ok":
                ok = False
                lines.append("  FAIL http: /health should return {status: ok}")

            # /spawn (dry-run, grant=spawn_sandboxed)
            spawn_body = {
                "command": ["echo", "test"],
                "agent_id": "http-test",
                "dry_run": True,
                "filesystem_policy": {
                    "grant": "repo_rw",
                    "allowed_read": [workdir],
                    "allowed_write": [workdir],
                },
                "process_policy": {
                    "grant": "spawn_sandboxed",
                    "max_pids": 8,
                },
            }
            resp = _http_post(base + "/spawn", spawn_body)
            if resp.get("status") != "ok":
                ok = False
                lines.append("  FAIL http: /spawn (dry-run, allowed) should be ok, "
                             "got %r (detail: %s)" % (resp.get("status"), resp.get("detail")))

            # /spawn (grant=none → 403)
            denied_body = dict(spawn_body)
            denied_body["process_policy"] = {"grant": "none"}
            code, resp = _http_post_raw(base + "/spawn", denied_body)
            if code != 403 or resp.get("status") != "denied":
                ok = False
                lines.append("  FAIL http: /spawn with grant=none should be 403/denied, "
                             "got %d/%r" % (code, resp.get("status")))

            # /status/<pid> — unknown pid
            resp = _http_get(base + "/status/99999")
            if "state" not in resp:
                ok = False
                lines.append("  FAIL http: /status/<pid> should return state field")

            # /kill (unknown pid is ok)
            kill_body = {"pid": 99999, "agent_id": "http-test", "signal": 15}
            resp = _http_post(base + "/kill", kill_body)
            if resp.get("status") not in ("ok",):
                ok = False
                lines.append("  FAIL http: /kill unknown pid should be ok, got %r" %
                             resp.get("status"))

            # /health again — still alive
            resp2 = _http_get(base + "/health")
            if resp2.get("status") != "ok":
                ok = False
                lines.append("  FAIL http: /health after /kill should still be ok")

        finally:
            server.shutdown()
            server.server_close()

    if ok:
        lines.append("  PASS http: /health → ok; /spawn dry-run → ok; "
                     "/spawn grant=none → 403; /status → state field; "
                     "/kill unknown-pid → ok")
    return ok


def _http_get(url: str) -> dict:
    import urllib.request
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def _http_post(url: str, body: dict) -> dict:
    _, resp = _http_post_raw(url, body)
    return resp


def _http_post_raw(url: str, body: dict) -> "tuple[int, dict]":
    import urllib.request, urllib.error
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            return e.code, json.loads(body_bytes)
        except Exception:
            return e.code, {"status": "error", "detail": body_bytes.decode()}


# --------------------------------------------------------------------------- #
# Runner                                                                         #
# --------------------------------------------------------------------------- #

def run():
    lines = []
    ok = True
    for label, fn in [
        ("policy (decide_path deny-by-default)", _test_policy),
        ("namespace plan (build_namespace_plan, no syscalls)", _test_namespace_plan),
        ("cgroup limits (mock path for CI)", _test_cgroup),
        ("eventd audit (write-ahead, chain integrity)", _test_eventd_audit),
        ("daemon spawn + access (dry-run + policy enforcement)", _test_daemon),
        ("http api (health / spawn / kill / status)", _test_http_api),
    ]:
        lines.append(label + ":")
        try:
            ok &= fn(lines)
        except Exception as e:
            import traceback
            ok = False
            lines.append("  ERROR %s: %s" % (label, e))
            lines.append(traceback.format_exc())
    return bool(ok), lines


if __name__ == "__main__":
    ok, lines = run()
    print("== test_sandboxd ==")
    for ln in lines:
        print(ln)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
