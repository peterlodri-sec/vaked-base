"""agent_sandboxd.cgroup — cgroup-v2 resource limits.

Applies cpu / memory / io / pids limits from the declared ``capability process``
membrane to a delegated cgroup-v2 subtree. Limits are kernel-enforced hard bounds
(OOM-kill / clone-refusal), not advisory estimates — matching the design spec's
"mathematical bound, not policy" stance.

**Hierarchy layout:**

    /sys/fs/cgroup/vaked/<agent-id>/

Each worker gets its own leaf cgroup under the ``vaked`` subtree. sandboxd
writes the resource limit files; the NixOS module ensures the host cgroup-v2
hierarchy is set up and the ``vaked`` subtree is delegated (``delegate=yes``
in the systemd unit or the cgroup.subtree_control chain has the needed
controllers enabled).

**Files written (cgroup-v2 unified hierarchy):**

  ``memory.max``   — ``<bytes>`` or ``"max"`` (unlimited)
  ``pids.max``     — ``<n>`` or ``"max"``
  ``cpu.max``      — ``"<quota_us> <period_us>"`` or ``"max <period_us>"``
  ``io.max``       — ``"<major>:<minor> rbps=<n> wbps=<n>"`` per device

**Privilege note:**

  Writing to ``/sys/fs/cgroup/vaked/`` requires that the process holds
  ``CAP_SYS_ADMIN`` in the appropriate cgroup namespace, OR that the cgroup
  subtree is delegated to the calling uid (via ``/sys/fs/cgroup/cgroup.subtree_control``
  and the NixOS systemd ``Delegate=`` stanza). In CI neither condition holds;
  use ``cgroup_root=<mock-path>`` to redirect writes to a temp directory.

**Mock path for CI:**

  Pass ``cgroup_root="/tmp/mock-cgroup"`` (or any writable path) to
  :func:`apply_cgroup_limits`. The function writes the same files under the
  mock root. Tests use this to exercise the write logic without privilege.

Python 3.11+ stdlib only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# The real cgroup-v2 root on vakedos (and most modern Linux hosts).
_CGROUP2_ROOT = "/sys/fs/cgroup"
_VAKED_SUBTREE = "vaked"


@dataclass
class CgroupSpec:
    """Resource limits to apply from ``capability process`` + fiber budget.

    All limits are optional (``None`` = kernel default / unconstrained).
    ``agent_id`` is used as the leaf cgroup directory name.
    """
    agent_id: str
    # cgroup-v2 memory.max
    mem_max_bytes: "int | None" = None
    # cgroup-v2 pids.max
    pids_max: "int | None" = None
    # cgroup-v2 cpu.max: quota_us / period_us (None quota = "max" = unconstrained)
    cpu_quota_us: "int | None" = None
    cpu_period_us: int = 100_000         # 100 ms period (Linux default)
    # cgroup-v2 io.max: per device rbps/wbps limits
    # Each entry: {"major": int, "minor": int, "rbps": int|None, "wbps": int|None}
    io_limits: list = None   # list[dict]

    def __post_init__(self):
        if self.io_limits is None:
            self.io_limits = []


@dataclass
class CgroupResult:
    """Outcome of applying cgroup-v2 limits for one worker."""
    applied: bool
    cgroup_path: str
    files_written: list   # list[str] — absolute paths of files written
    detail: str
    error: "str | None" = None
    mock: bool = False    # True when cgroup_root is not the real /sys/fs/cgroup


def _write_cgroup_file(path: str, value: str) -> None:
    """Write ``value`` to a cgroup control file; propagate OSError."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)


def cgroup_path(agent_id: str, cgroup_root: str = _CGROUP2_ROOT) -> str:
    """Return the absolute path of the leaf cgroup for ``agent_id``."""
    return os.path.join(cgroup_root, _VAKED_SUBTREE, agent_id)


def probe_cgroup() -> dict:
    """Probe whether the vaked cgroup subtree is writable on this host.

    Returns:
      ``writable``: bool
      ``cgroup_root``: str
      ``detail``: str
    """
    test_path = os.path.join(_CGROUP2_ROOT, _VAKED_SUBTREE, "_probe", "pids.max")
    try:
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        with open(test_path, "w") as f:
            f.write("max")
        os.unlink(test_path)
        try:
            os.rmdir(os.path.dirname(test_path))
        except OSError:
            pass
        return {
            "writable": True,
            "cgroup_root": _CGROUP2_ROOT,
            "detail": "cgroup-v2 subtree writable at %s/%s" % (_CGROUP2_ROOT, _VAKED_SUBTREE),
        }
    except OSError as e:
        return {
            "writable": False,
            "cgroup_root": _CGROUP2_ROOT,
            "detail": "cgroup-v2 write failed (expected in CI): %s" % e,
        }


def apply_cgroup_limits(
        spec: CgroupSpec,
        *,
        cgroup_root: str = _CGROUP2_ROOT,
) -> CgroupResult:
    """Write cgroup-v2 resource limits for ``spec.agent_id`` to ``cgroup_root``.

    On the real vakedos host ``cgroup_root`` is ``/sys/fs/cgroup`` and writes
    go into the delegated ``vaked/<agent-id>/`` subtree. In CI, pass a
    temporary directory as ``cgroup_root`` to exercise the write logic without
    privilege (the mock path is reported in :class:`CgroupResult`).

    Returns a :class:`CgroupResult` describing every file written. Does not
    raise on permission errors — they are captured as ``error`` in the result
    so the daemon can log and continue.
    """
    cg = cgroup_path(spec.agent_id, cgroup_root)
    mock = cgroup_root != _CGROUP2_ROOT
    written = []

    try:
        os.makedirs(cg, exist_ok=True)
    except OSError as e:
        return CgroupResult(
            applied=False, cgroup_path=cg, files_written=[],
            detail="failed to create cgroup directory",
            error=str(e), mock=mock)

    errors = []

    def _write(filename: str, value: str) -> None:
        path = os.path.join(cg, filename)
        try:
            _write_cgroup_file(path, value)
            written.append(path)
        except OSError as e:
            errors.append("%s: %s" % (filename, e))

    # memory.max
    if spec.mem_max_bytes is not None:
        _write("memory.max", str(spec.mem_max_bytes))
    else:
        _write("memory.max", "max")

    # pids.max
    if spec.pids_max is not None:
        _write("pids.max", str(spec.pids_max))
    else:
        _write("pids.max", "max")

    # cpu.max: "<quota_us> <period_us>" or "max <period_us>"
    quota = str(spec.cpu_quota_us) if spec.cpu_quota_us is not None else "max"
    _write("cpu.max", "%s %d" % (quota, spec.cpu_period_us))

    # io.max: one line per device
    for dev in spec.io_limits:
        major = dev.get("major", 8)
        minor = dev.get("minor", 0)
        rbps = dev.get("rbps")
        wbps = dev.get("wbps")
        parts = ["%d:%d" % (major, minor)]
        if rbps is not None:
            parts.append("rbps=%d" % rbps)
        if wbps is not None:
            parts.append("wbps=%d" % wbps)
        _write("io.max", " ".join(parts))

    if errors:
        return CgroupResult(
            applied=False, cgroup_path=cg, files_written=written,
            detail="partial write (%d errors)" % len(errors),
            error="; ".join(errors), mock=mock)

    return CgroupResult(
        applied=True, cgroup_path=cg, files_written=written,
        detail="applied %d cgroup-v2 limits%s" % (len(written),
               " (mock path)" if mock else ""),
        mock=mock)


def teardown_cgroup(agent_id: str, *, cgroup_root: str = _CGROUP2_ROOT) -> None:
    """Remove the leaf cgroup directory for ``agent_id``.

    Must be called only after the cgroup has no live processes (the kernel
    refuses rmdir otherwise). Silently ignores missing-dir errors.
    """
    cg = cgroup_path(agent_id, cgroup_root)
    try:
        os.rmdir(cg)
    except OSError:
        pass
