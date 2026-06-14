"""agent-sandboxd — the process + filesystem membrane daemon (Python reference
implementation).

Roster position (docs/runtime/README.md): ``agent-sandboxd`` — Zig · namespace
isolation / cgroup-v2 / overlay-rootfs; the ``process`` and ``filesystem``
membranes. This package is the **Python reference / oracle** for that daemon
(the #15 pattern: Python defines the bytes + the decision, Zig reproduces them).
The hyphenated daemon name maps to the importable module ``agent_sandboxd``.

It closes the process + filesystem membrane vertical slice:

    Vaked declares      capability fs { grant = repo_rw; ... }
                        capability process { grant = spawn_sandboxed; ... }
        ↓ vakedc lower  gen/zig/<fiber>.json       (config contract)
    Nix materializes    (the flake spine wires the daemon — interface today)
    Zig enforces        namespace.enter()  → user/mount/pid/net namespaces     (namespace)
                        cgroup.apply()    → cgroup-v2 cpu/mem/io/pids limits   (cgroup)
                        policy.enforce()  → deny-by-default filesystem access  (policy)
    eventd (immutable)  spawn/kill/violation events appended to hash chain     (eventd)

HTTP daemon shape (for the reference phase):
    POST /spawn   — spawn a supervised child in an isolated boundary
    POST /kill    — terminate a supervised process
    GET  /status/<pid> — process status
    GET  /health  — liveness

Design: docs/superpowers/specs/2026-06-13-sandboxd-design.md
Issue:  #86 (isolation backend), relates to #50 (wasm backend)
"""
from .policy import FilesystemPolicy, ProcessPolicy, PolicyDecision, decide_path
from .namespace import NamespaceSpec, NamespacePlan, build_namespace_plan, enter_namespace
from .cgroup import CgroupSpec, apply_cgroup_limits, CgroupResult
from .eventd import (
    spawn_event, kill_event, access_event, testify,
)
from .daemon import SandboxDaemon, SpawnRequest, SpawnResult, ProcessStatus

__all__ = [
    # policy
    "FilesystemPolicy", "ProcessPolicy", "PolicyDecision", "decide_path",
    # namespace
    "NamespaceSpec", "NamespacePlan", "build_namespace_plan", "enter_namespace",
    # cgroup
    "CgroupSpec", "apply_cgroup_limits", "CgroupResult",
    # eventd
    "spawn_event", "kill_event", "access_event", "testify",
    # daemon
    "SandboxDaemon", "SpawnRequest", "SpawnResult", "ProcessStatus",
]
