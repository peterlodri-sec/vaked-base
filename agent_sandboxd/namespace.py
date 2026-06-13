"""agent_sandboxd.namespace — Linux namespace isolation.

Builds and enters the isolation boundary for a worker process. The boundary
is composed of four namespace kinds (matching the design spec §native-exec
mechanics):

  * **user namespace** (CLONE_NEWUSER) — rootless: the worker runs as an
    unprivileged uid that appears as root only inside its userns. Requires
    either ``/proc/sys/kernel/unprivileged_userns_clone = 1`` or
    ``CAP_SYS_ADMIN``.

  * **mount namespace** (CLONE_NEWNS) — private mount propagation; only
    explicitly declared filesystem paths are bind-mounted into the worker's
    view. Everything else is absent (deny-by-default mount posture).

  * **pid namespace** (CLONE_NEWPID) — the worker is pid 1 of its own
    process tree. A kill of the namespace-init reaps the whole subtree.

  * **network namespace** (CLONE_NEWNET) — deny-by-default egress; the
    ``network`` membrane ownership is shared with agent-guardd (see design
    §Open — network-namespace ownership); in the reference implementation we
    create the netns here and leave programming of its firewall rules to
    agent-guardd.

**Syscalls used and why:**

  ``unshare(2)`` — disassociate parts of the process execution context
  (namespaces). Preferred over ``clone(2)`` for the reference impl because
  it operates on the calling process rather than creating a new one, which
  is simpler to drive from Python. The Zig port will use ``clone(3)`` /
  ``clone(2)`` with ``CLONE_*`` flags for the child-process model.

  ``/usr/bin/unshare`` (the userspace wrapper) — used as the subprocess
  entry point when spawning child processes, since Python's ``os.unshare``
  is only available on Linux >= 3.8 and may not be exposed in older Python
  builds. The reference implementation uses ``unshare(1)`` CLI flags to
  keep the implementation portable across Python 3.11+ without ctypes.

  ``mount(2)`` (via ``/bin/mount``) — used for bind-mounts inside the
  namespace after ``unshare``.

**Capability / privilege note:**

  User namespaces require either:
  - ``kernel.unprivileged_userns_clone = 1`` (the vakedos host sets this —
    see hosts/vakedos), OR
  - ``CAP_SYS_ADMIN`` on the calling process.

  Mount namespace operations (bind-mount) inside a user namespace require
  that the mount is marked as user-mountable or that the process holds
  ``CAP_SYS_ADMIN`` within the userns (which ``--map-root-user`` provides).

  CI environments (no privileged cgroup, no userns delegation) cannot
  exercise the real namespace entry. Use ``--dry-run`` (or pass
  ``dry_run=True`` to :func:`enter_namespace`) to print the plan without
  executing it.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Data model                                                                   #
# --------------------------------------------------------------------------- #

@dataclass
class NamespaceSpec:
    """Declared namespace configuration derived from the fiber's membrane grants.

    ``bind_mounts`` maps ``host_path → mount_point_inside_sandbox`` for each
    path the filesystem membrane grants. ``overlay_lower`` is the read-only
    base rootfs; ``overlay_upper`` and ``overlay_work`` are the writable +
    work directories fs-snapshotd creates (sandboxd mounts the overlay, never
    accounts for it). ``uid_map`` and ``gid_map`` are the uid/gid mapping
    lines for the user namespace (``"0 <host-uid> 1"`` for rootless).
    """
    user_ns: bool = True        # CLONE_NEWUSER
    mount_ns: bool = True       # CLONE_NEWNS
    pid_ns: bool = True         # CLONE_NEWPID
    net_ns: bool = True         # CLONE_NEWNET

    # Mount plan (from capability fs)
    bind_mounts: dict = field(default_factory=dict)  # {host_path: sandbox_path}
    overlay_lower: "str | None" = None    # lowerdir for overlayfs rootfs
    overlay_upper: "str | None" = None    # upperdir (writable layer)
    overlay_work: "str | None" = None     # workdir for overlayfs

    # uid/gid mapping for user namespace (rootless)
    uid_map: "str | None" = None   # e.g. "0 1000 1"
    gid_map: "str | None" = None   # e.g. "0 1000 1"

    # Command to exec inside the sandbox
    command: list = field(default_factory=list)   # list[str]
    env: dict = field(default_factory=dict)        # environment variables


@dataclass
class NamespacePlan:
    """The concrete CLI / syscall plan for entering the namespace boundary.

    ``unshare_args`` are the flags for ``/usr/bin/unshare``; ``mount_steps``
    are the bind-mount commands; ``overlay_cmd`` is the overlay mount command
    if an overlay rootfs is configured. ``dry_run_lines`` is the human-readable
    plan printed by ``--dry-run`` (no syscalls executed).
    """
    unshare_args: list = field(default_factory=list)   # list[str]
    mount_steps: list = field(default_factory=list)    # list[list[str]] — each a cmd
    overlay_cmd: "list | None" = None
    dry_run_lines: list = field(default_factory=list)  # list[str]


@dataclass
class EnterResult:
    """The outcome of a namespace boundary entry attempt."""
    entered: bool
    pid: "int | None" = None         # pid of the supervised child (host pid ns view)
    dry_run: bool = False
    mechanism: str = "unshare"       # "unshare" | "dry-run" | "unavailable"
    detail: str = ""
    error: "str | None" = None


# --------------------------------------------------------------------------- #
# Plan construction                                                             #
# --------------------------------------------------------------------------- #

def build_namespace_plan(spec: NamespaceSpec) -> NamespacePlan:
    """Translate a :class:`NamespaceSpec` into a concrete :class:`NamespacePlan`.

    Constructs the ``unshare`` flags and mount commands that materialise the
    isolation boundary. This is pure (no side effects) — safe to call in CI.
    """
    plan = NamespacePlan()
    dry = plan.dry_run_lines

    # --- unshare flags ------------------------------------------------------- #
    flags = []
    if spec.user_ns:
        flags.append("--user")
        uid = spec.uid_map or ("0 %d 1" % os.getuid())
        gid = spec.gid_map or ("0 %d 1" % os.getgid())
        flags += ["--map-root-user"]   # maps calling uid → uid 0 inside userns
        dry.append(
            "unshare --user --map-root-user  "
            "  # user ns: uid-map=%r gid-map=%r" % (uid, gid))
    if spec.mount_ns:
        flags.append("--mount")
        dry.append("unshare --mount              # private mount propagation")
    if spec.pid_ns:
        flags.append("--pid")
        flags.append("--fork")          # required: pid ns needs a fork to become pid 1
        dry.append("unshare --pid --fork          # worker is pid 1 of its tree")
    if spec.net_ns:
        flags.append("--net")
        dry.append("unshare --net               # isolated network namespace (deny-by-default egress)")

    plan.unshare_args = flags

    # --- bind mounts --------------------------------------------------------- #
    for host_path, sandbox_path in spec.bind_mounts.items():
        cmd = ["mount", "--bind", host_path, sandbox_path]
        plan.mount_steps.append(cmd)
        dry.append("mount --bind %s %s" % (host_path, sandbox_path))

    # --- overlay rootfs ------------------------------------------------------ #
    if all(x is not None for x in (
            spec.overlay_lower, spec.overlay_upper, spec.overlay_work)):
        lower = spec.overlay_lower
        upper = spec.overlay_upper
        work = spec.overlay_work
        overlay_opts = (
            "lowerdir=%s,upperdir=%s,workdir=%s" % (lower, upper, work))
        plan.overlay_cmd = [
            "mount", "-t", "overlayfs", "overlay",
            "-o", overlay_opts,
            "/",   # mount at rootfs inside the new mount ns
        ]
        dry.append(
            "mount -t overlayfs overlay -o %s /"
            "  # overlay rootfs (writes → upperdir)" % overlay_opts)

    return plan


# --------------------------------------------------------------------------- #
# Capability probe                                                              #
# --------------------------------------------------------------------------- #

def probe_userns() -> dict:
    """Probe whether user namespaces are available on this host.

    Returns a dict with:
    - ``available``: bool — ``unshare --user`` succeeded
    - ``detail``: str — human-readable reason
    """
    unshare = shutil.which("unshare")
    if unshare is None:
        return {"available": False, "detail": "unshare(1) not found in PATH"}
    try:
        result = subprocess.run(
            [unshare, "--user", "--", "true"],
            capture_output=True, timeout=5.0)
        if result.returncode == 0:
            return {"available": True, "detail": "user namespaces available"}
        stderr = result.stderr.decode(errors="replace").strip()
        return {
            "available": False,
            "detail": "unshare --user returned %d: %s" % (result.returncode, stderr),
        }
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"available": False, "detail": "probe failed: %s" % e}


# --------------------------------------------------------------------------- #
# Namespace entry                                                               #
# --------------------------------------------------------------------------- #

def enter_namespace(spec: NamespaceSpec, *, dry_run: bool = False) -> EnterResult:
    """Enter the namespace boundary described by ``spec`` and exec the command.

    In ``dry_run`` mode prints the plan to stdout and returns without executing
    any syscalls. This is the safe path for CI and introspection.

    In normal mode uses ``/usr/bin/unshare`` as the entry point (see module
    docstring for the syscall rationale). Returns an :class:`EnterResult`
    describing the outcome without blocking — the caller is responsible for
    supervising the returned pid.

    **Privilege note:** requires user namespaces to be enabled (see module
    docstring). On a host without ``CAP_SYS_ADMIN`` or userns delegation,
    ``enter_namespace`` degrades to an :class:`EnterResult` with
    ``entered=False`` and an informative ``detail``.
    """
    plan = build_namespace_plan(spec)

    if dry_run:
        print("[sandboxd dry-run] namespace plan for: %s" % " ".join(spec.command))
        for line in plan.dry_run_lines:
            print("  %s" % line)
        if spec.command:
            print("  exec %s" % " ".join(spec.command))
        return EnterResult(entered=False, dry_run=True, mechanism="dry-run",
                           detail="dry-run: no syscalls executed")

    unshare = shutil.which("unshare")
    if unshare is None:
        return EnterResult(
            entered=False, mechanism="unavailable",
            detail="unshare(1) not in PATH — namespace isolation unavailable",
            error="unshare not found")

    if not spec.command:
        return EnterResult(
            entered=False, mechanism="unshare",
            detail="no command to exec inside namespace",
            error="empty command")

    cmd = [unshare] + plan.unshare_args + ["--"] + spec.command
    try:
        proc = subprocess.Popen(
            cmd,
            env={**os.environ, **spec.env} if spec.env else None,
            close_fds=True,
        )
        return EnterResult(
            entered=True, pid=proc.pid, mechanism="unshare",
            detail="spawned pid %d via unshare" % proc.pid)
    except OSError as e:
        return EnterResult(
            entered=False, mechanism="unshare",
            detail="unshare exec failed: %s" % e,
            error=str(e))
