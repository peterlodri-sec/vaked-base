"""agent-sandboxd CLI — drive + demonstrate the process + filesystem membrane.

    python3 -m agent_sandboxd probe
        Report kernel namespace + cgroup capability on this host.

    python3 -m agent_sandboxd serve [--host H] [--port P]
                                     [--eventd-log L] [--cgroup-root R]
                                     [--dry-run]
        Start the HTTP daemon. Listens on H:P (default 127.0.0.1:7240).
        --eventd-log: path to the eventd JSONL audit log (default: ./eventd/sandboxd.jsonl)
        --cgroup-root: override cgroup-v2 root (pass /tmp/... for CI mocking)
        --dry-run: print namespace/cgroup plans without executing syscalls

    python3 -m agent_sandboxd spawn <command...>
                                     [--agent-id ID] [--read PATH] [--write PATH]
                                     [--mem-max BYTES] [--pids-max N]
                                     [--eventd-log L] [--cgroup-root R]
                                     [--dry-run]
        Spawn <command> inside a sandbox boundary with the declared policy.
        --read: allowed read path (repeatable)
        --write: allowed write path (repeatable)
        --agent-id: logical agent identifier (cgroup leaf name)

    python3 -m agent_sandboxd demo [--out DIR]
        The whole slice end-to-end, BuildKit-style:
        build policy → spawn (dry-run) → check_access → testify → print audit.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)

from .cgroup import CgroupSpec, apply_cgroup_limits, probe_cgroup
from .daemon import SandboxDaemon, SpawnRequest, run_server
from .eventd import testify, spawn_event
from .namespace import NamespaceSpec, build_namespace_plan, probe_userns
from .policy import (
    FilesystemPolicy, FsGrant, ProcessGrant, ProcessPolicy, decide_path,
)


# --------------------------------------------------------------------------- #

def cmd_probe(_args) -> int:
    print("=== sandboxd capability probe ===")

    # user namespace
    us = probe_userns()
    print("user namespaces  : %s (%s)"
          % ("available" if us["available"] else "unavailable", us["detail"]))

    # cgroup-v2
    cg = probe_cgroup()
    print("cgroup-v2 write  : %s (%s)"
          % ("writable" if cg["writable"] else "no write", cg["detail"]))

    return 0


def cmd_serve(args) -> int:
    log = args.eventd_log or os.path.join("eventd", "sandboxd.jsonl")
    daemon = SandboxDaemon(
        eventd_log=log,
        cgroup_root=args.cgroup_root or "/sys/fs/cgroup",
        dry_run=args.dry_run,
    )
    run_server(daemon, host=args.host, port=args.port)
    return 0


def cmd_spawn(args) -> int:
    log = args.eventd_log or os.path.join("eventd", "sandboxd.jsonl")
    daemon = SandboxDaemon(
        eventd_log=log,
        cgroup_root=args.cgroup_root or "/sys/fs/cgroup",
        dry_run=args.dry_run,
    )

    fs_policy = FilesystemPolicy(
        grant=FsGrant.repo_rw if (args.write or args.read) else FsGrant.none,
        allowed_read=list(args.read or []),
        allowed_write=list(args.write or []),
    )
    proc_policy = ProcessPolicy(
        grant=ProcessGrant.spawn_sandboxed,
        max_pids=args.pids_max,
        mem_max_bytes=args.mem_max,
    )
    req = SpawnRequest(
        command=args.command,
        agent_id=args.agent_id or "cli",
        filesystem_policy=fs_policy,
        process_policy=proc_policy,
        dry_run=args.dry_run,
    )
    result = daemon.spawn(req)
    print("status  :", result.status)
    print("pid     :", result.pid)
    print("detail  :", result.detail)
    return 0 if result.status in ("ok",) else 1


def cmd_demo(args) -> int:
    out = args.out or tempfile.mkdtemp(prefix="vaked-sandboxd-")
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "eventd", "sandboxd.jsonl")
    cgroup_root = os.path.join(out, "cgroup")

    def step(n, label):
        print("\n#%d %s" % (n, label))

    print("=" * 70)
    print("agent-sandboxd — process + filesystem membrane vertical slice")
    print("  (reference / oracle — #15 pattern; dry-run mode)")
    print("=" * 70)

    # --- 1. policy ---------------------------------------------------------- #
    step(1, "build filesystem + process policy")
    workdir = os.path.join(out, "work")
    os.makedirs(workdir, exist_ok=True)
    fs_policy = FilesystemPolicy(
        grant=FsGrant.repo_rw,
        allowed_read=[workdir],
        allowed_write=[workdir],
    )
    proc_policy = ProcessPolicy(
        grant=ProcessGrant.spawn_sandboxed,
        max_pids=64,
        mem_max_bytes=256 * 1024 * 1024,  # 256 MiB
    )
    print("   fs grant=%s  read=[%s]  write=[%s]"
          % (fs_policy.grant.value, workdir, workdir))
    print("   process grant=%s  pids_max=%d  mem_max=%d MiB"
          % (proc_policy.grant.value, proc_policy.max_pids or 0,
             (proc_policy.mem_max_bytes or 0) // (1024 * 1024)))

    # --- 2. namespace plan -------------------------------------------------- #
    step(2, "build namespace plan (dry-run — no syscalls)")
    ns_spec = NamespaceSpec(
        command=["true"],
        bind_mounts={workdir: workdir},
    )
    plan = build_namespace_plan(ns_spec)
    for line in plan.dry_run_lines:
        print("   %s" % line)

    # --- 3. cgroup limits --------------------------------------------------- #
    step(3, "apply cgroup-v2 limits (mock path for demo)")
    cg_spec = CgroupSpec(
        agent_id="demo-worker",
        mem_max_bytes=proc_policy.mem_max_bytes,
        pids_max=proc_policy.max_pids,
    )
    cg_result = apply_cgroup_limits(cg_spec, cgroup_root=cgroup_root)
    print("   cgroup path: %s (mock=%s)" % (cg_result.cgroup_path, cg_result.mock))
    for f in cg_result.files_written:
        val = open(f).read().strip() if os.path.exists(f) else "?"
        print("   wrote: %s = %s" % (os.path.basename(f), val))

    # --- 4. filesystem access decisions ------------------------------------- #
    step(4, "filesystem access decisions (deny-by-default)")
    daemon = SandboxDaemon(eventd_log=log, cgroup_root=cgroup_root, dry_run=True)
    test_cases = [
        (workdir + "/output.txt", "write", True),
        (workdir + "/input.txt", "read", True),
        ("/etc/passwd", "read", False),
        ("/tmp/scratch", "write", False),
    ]
    all_ok = True
    for path, mode, expect_allowed in test_cases:
        decision = daemon.check_access("demo-worker", fs_policy, path, mode)
        match = decision.allowed == expect_allowed
        mark = "PASS" if match else "FAIL"
        if not match:
            all_ok = False
        print("   %s %-5s %-40s → %s  (%s)"
              % (mark, mode, path,
                 "ALLOW" if decision.allowed else "DENY",
                 decision.reason[:60]))

    # --- 5. spawn (dry-run) ------------------------------------------------- #
    step(5, "spawn (dry-run — prints plan, no exec)")
    req = SpawnRequest(
        command=["echo", "hello from sandbox"],
        agent_id="demo-worker",
        filesystem_policy=fs_policy,
        process_policy=proc_policy,
        dry_run=True,
    )
    result = daemon.spawn(req)
    print("   spawn status: %s — %s" % (result.status, result.detail))

    # --- 6. eventd audit ---------------------------------------------------- #
    step(6, "eventd audit trail")
    import json as _json
    try:
        entries = [_json.loads(l) for l in open(log) if l.strip()]
        print("   %d events in %s" % (len(entries), log))
        for e in entries[:4]:
            p = e.get("payload", {})
            print("   seq=%-3d kind=%-25s action=%s"
                  % (e.get("seq", "?"), p.get("kind", "?"), p.get("action", "?")))
    except FileNotFoundError:
        print("   (no events — dry-run spawn audit only in serve mode)")

    ok = all_ok and cg_result.applied
    print("\n" + "=" * 70)
    print("SLICE:", "CLOSED ✓ (policy → namespace plan → cgroup limits → "
          "access decisions → spawn audit)"
          if ok else "INCOMPLETE ✗")
    print("  artifacts under:", out)
    print("=" * 70)
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="agent-sandboxd")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # probe
    sp = sub.add_parser("probe", help="report namespace + cgroup capability")
    sp.set_defaults(fn=cmd_probe)

    # serve
    sp = sub.add_parser("serve", help="start the HTTP daemon")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=7240)
    sp.add_argument("--eventd-log", default=None)
    sp.add_argument("--cgroup-root", default=None)
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_serve)

    # spawn
    sp = sub.add_parser("spawn", help="spawn a command inside a sandbox boundary")
    sp.add_argument("command", nargs="+")
    sp.add_argument("--agent-id", default="cli")
    sp.add_argument("--read", action="append", default=[])
    sp.add_argument("--write", action="append", default=[])
    sp.add_argument("--mem-max", type=int, default=None)
    sp.add_argument("--pids-max", type=int, default=None)
    sp.add_argument("--eventd-log", default=None)
    sp.add_argument("--cgroup-root", default=None)
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_spawn)

    # demo
    sp = sub.add_parser("demo", help="end-to-end slice demo (BuildKit-style)")
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
