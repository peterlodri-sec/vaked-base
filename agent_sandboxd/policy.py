"""agent_sandboxd.policy — filesystem + process policy enforcement.

Reads the declared ``capability fs`` and ``capability process`` membrane
bounds from the lowered fiber config and provides the single authoritative
access-control decision, :func:`decide_path`.

Deny-by-default for filesystem access: a path is allowed iff it falls within
a declared read or write bound (using ``os.path.commonpath`` prefix matching).
Writes outside declared write paths are denied even if the path is readable.

The ``capability fs`` lattice (docs/language/0011-type-system.md §5):

    none < repo_ro < repo_rw < host_rw
    none < repo_ro < host_ro

The ``capability process`` lattice:

    none < spawn_sandboxed < spawn < exec_host

The Python reference does not enforce cgroup limits here — that is
:mod:`agent_sandboxd.cgroup`. This module focuses on path-based decision.

Python 3.11+ stdlib only (mirrors eventd's reference-impl discipline).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class FsGrant(str, Enum):
    """The ``capability fs`` lattice values in ascending order."""
    none = "none"
    repo_ro = "repo_ro"
    repo_rw = "repo_rw"
    host_ro = "host_ro"
    host_rw = "host_rw"


class ProcessGrant(str, Enum):
    """The ``capability process`` lattice values in ascending order."""
    none = "none"
    spawn_sandboxed = "spawn_sandboxed"
    spawn = "spawn"
    exec_host = "exec_host"


@dataclass
class FilesystemPolicy:
    """The filesystem membrane policy for one worker.

    ``grant`` is the qualitative capability lattice value; ``allowed_read``
    and ``allowed_write`` are the concrete path sets it resolves to (from the
    lowered fiber config — see design §Config contract). Deny-by-default:
    a path must appear under an allowed prefix to be permitted.

    During the reference phase the path sets are driven from the fiber config
    directly; a full implementation lowers ``capability fs`` grants through
    the NixOS module to concrete bind-mount lists.
    """
    grant: FsGrant = FsGrant.none
    allowed_read: list = field(default_factory=list)    # list[str] — absolute paths
    allowed_write: list = field(default_factory=list)   # list[str] — absolute paths


@dataclass
class ProcessPolicy:
    """The process membrane policy for one worker.

    ``grant`` is the capability lattice value; ``max_pids``, ``cpu_weight``,
    ``mem_max_bytes``, ``io_max_rbps``, ``io_max_wbps`` are the cgroup-v2
    resource limits that the ``capability process`` grant (and the fiber's
    budget) resolve to. A ``None`` limit means unconstrained.
    """
    grant: ProcessGrant = ProcessGrant.none
    max_pids: "int | None" = None
    cpu_weight: "int | None" = None      # cgroup cpu.weight (1–10000, default 100)
    mem_max_bytes: "int | None" = None   # cgroup memory.max (bytes; None = "max")
    io_max_rbps: "int | None" = None     # cgroup io.max rbps; None = unlimited
    io_max_wbps: "int | None" = None     # cgroup io.max wbps; None = unlimited


@dataclass
class PolicyDecision:
    """The result of an access-control check for one (path, mode) pair."""
    allowed: bool
    path: str
    mode: str       # "read" | "write"
    reason: str


def _is_under(path: str, prefix: str) -> bool:
    """Return True iff ``path`` is equal to or nested inside ``prefix``."""
    path = os.path.normpath(os.path.abspath(path))
    prefix = os.path.normpath(os.path.abspath(prefix))
    try:
        common = os.path.commonpath([path, prefix])
    except ValueError:
        return False
    return common == prefix


def decide_path(policy: FilesystemPolicy, path: str,
                mode: str = "read") -> PolicyDecision:
    """The filesystem access verdict for ``(path, mode)`` under ``policy``.

    ``mode`` is ``"read"`` or ``"write"``. Deny-by-default: allowed iff the
    path falls within an allowed prefix (read: any ``allowed_read`` prefix or
    any ``allowed_write`` prefix, since write-granted paths are implicitly
    readable; write: only ``allowed_write`` prefixes).

    A path that matches no allowed prefix is denied regardless of grant level;
    the grant level is authoritative but the concrete path sets are the
    enforcement boundary.
    """
    if mode not in ("read", "write"):
        return PolicyDecision(
            allowed=False, path=path, mode=mode,
            reason="unknown mode %r" % mode)

    if policy.grant == FsGrant.none:
        return PolicyDecision(
            allowed=False, path=path, mode=mode,
            reason="process holds no filesystem capability (grant=none)")

    if mode == "write":
        for prefix in policy.allowed_write:
            if _is_under(path, prefix):
                return PolicyDecision(
                    allowed=True, path=path, mode=mode,
                    reason="write within declared bound %s" % prefix)
        return PolicyDecision(
            allowed=False, path=path, mode=mode,
            reason="deny-by-default: path not in declared write bounds")

    # read: allowed_write paths are also readable (write ⊇ read in the lattice)
    for prefix in policy.allowed_read + policy.allowed_write:
        if _is_under(path, prefix):
            return PolicyDecision(
                allowed=True, path=path, mode=mode,
                reason="read within declared bound %s" % prefix)
    return PolicyDecision(
        allowed=False, path=path, mode=mode,
        reason="deny-by-default: path not in declared read/write bounds")
