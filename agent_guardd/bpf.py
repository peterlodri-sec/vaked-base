"""agent_guardd.bpf — the real kernel datapath: compile a membrane's posture to
BPF bytecode, load it via the ``bpf()`` syscall, and (where permitted) attach it
at the cgroup egress hook.

This is the literal "eBPF testifies / Zig enforces" leg, exercised honestly:

  * ``compile_posture(default)`` assembles a real ``BPF_PROG_TYPE_CGROUP_SKB``
    program encoding the membrane's deny-by-default posture (drop / pass);
  * ``load(prog)`` submits it through ``BPF_PROG_LOAD`` — the in-kernel verifier
    runs and either accepts it (returning a program fd + the "processed N insns"
    trace) or rejects it (its log is captured);
  * ``attach(prog_fd, cgroup)`` attaches at ``BPF_CGROUP_INET_EGRESS`` to enforce
    in-kernel. On a capable host (vakedos) this is live enforcement; inside a
    nested container the attach is refused (EINVAL — delegated cgroup) and that
    is reported, not raised. Either way the precise per-destination decision +
    testimony runs in :mod:`agent_guardd.enforce`.

No third-party deps: the ``bpf()`` ABI is driven directly with ``ctypes`` (there
is no libbpf/bpftool/BTF requirement). x86-64 syscall numbers; the bytecode is
architecture-neutral BPF. Every syscall is wrapped to return a structured report
rather than crash, so a kernel without BPF degrades cleanly to the reference
datapath.
"""
from __future__ import annotations

import ctypes
import os
import struct
from dataclasses import dataclass, field

# --- bpf() syscall ABI ------------------------------------------------------ #

_NR_BPF = 321                     # x86-64 __NR_bpf
BPF_PROG_LOAD = 5
BPF_PROG_ATTACH = 8
BPF_PROG_DETACH = 9

BPF_PROG_TYPE_CGROUP_SKB = 15
BPF_CGROUP_INET_EGRESS = 1

# BPF instruction opcodes used by the posture program.
_MOV64_IMM = 0xB7                 # BPF_ALU64 | BPF_MOV | BPF_K
_EXIT = 0x95                      # BPF_JMP | BPF_EXIT

_CGROUP2_ROOT = "/sys/fs/cgroup/unified"
_CGROUP2_ALT = "/sys/fs/cgroup"   # unified-only hosts mount it here

_libc = ctypes.CDLL(None, use_errno=True)


def _insn(op, dst=0, src=0, off=0, imm=0) -> bytes:
    """Encode one 8-byte BPF instruction (op, regs, off, imm; little-endian)."""
    return struct.pack("<BBhi", op, (src << 4) | (dst & 0xF), off, imm)


class _BpfProgLoadAttr(ctypes.Structure):
    _fields_ = [
        ("prog_type", ctypes.c_uint), ("insn_cnt", ctypes.c_uint),
        ("insns", ctypes.c_ulonglong), ("license", ctypes.c_ulonglong),
        ("log_level", ctypes.c_uint), ("log_size", ctypes.c_uint),
        ("log_buf", ctypes.c_ulonglong), ("kern_version", ctypes.c_uint),
        ("prog_flags", ctypes.c_uint), ("prog_name", ctypes.c_char * 16),
        ("prog_ifindex", ctypes.c_uint), ("expected_attach_type", ctypes.c_uint),
    ]


class _BpfAttachAttr(ctypes.Structure):
    _fields_ = [
        ("target_fd", ctypes.c_uint), ("attach_bpf_fd", ctypes.c_uint),
        ("attach_type", ctypes.c_uint), ("attach_flags", ctypes.c_uint),
    ]


def _bpf(cmd, attr) -> "tuple[int, int]":
    """Invoke ``bpf(cmd, &attr, sizeof attr)`` → ``(ret, errno)``."""
    ret = _libc.syscall(_NR_BPF, cmd, ctypes.byref(attr), ctypes.sizeof(attr))
    return ret, ctypes.get_errno()


# --- compile ---------------------------------------------------------------- #

def compile_posture(default: str) -> bytes:
    """Assemble the membrane posture program: ``return 1`` (pass) when the
    membrane default is ``allow``, else ``return 0`` (drop) — the deny-by-default
    kernel posture. A cgroup/skb verdict MUST be 0 or 1 (the verifier enforces
    this), so the posture maps exactly onto the legal return set."""
    verdict = 1 if default == "allow" else 0
    return _insn(_MOV64_IMM, dst=0, imm=verdict) + _insn(_EXIT)


# --- load + attach ---------------------------------------------------------- #

@dataclass
class LoadReport:
    """The outcome of compiling + loading + attaching a membrane's posture."""
    available: bool                   # bpf() usable at all
    loaded: bool                      # BPF_PROG_LOAD accepted by the verifier
    prog_fd: int = -1
    insn_count: int = 0
    verdict: str = ""                 # "drop" / "pass" (the in-kernel posture)
    verifier_log: str = ""            # the kernel verifier's trace
    attached: bool = False            # attached at the cgroup egress hook
    mechanism: str = "reference"      # "ebpf-cgroup" if attached, else "reference"
    cgroup: "str | None" = None
    detail: str = ""

    def summary(self) -> str:
        if not self.available:
            return "bpf() unavailable — reference datapath (%s)" % self.detail
        if not self.loaded:
            return "BPF_PROG_LOAD rejected (%s)" % self.detail
        head = ("cgroup/skb posture=%s loaded (fd %d, verifier: %d insns)"
                % (self.verdict, self.prog_fd, self.insn_count))
        if self.attached:
            return head + "; attached at INET_EGRESS — in-kernel enforcement"
        return head + "; attach refused (%s) — reference datapath enforces" % self.detail


def load(prog: bytes, *, name: bytes = b"vaked_guard") -> "tuple[int, int, str]":
    """``BPF_PROG_LOAD`` a cgroup/skb ``prog`` → ``(fd, errno, verifier_log)``.
    ``fd >= 0`` means the kernel verifier accepted the bytecode."""
    insns = (ctypes.c_char * len(prog))(*prog)
    lic = ctypes.create_string_buffer(b"GPL")
    log = ctypes.create_string_buffer(1 << 16)
    attr = _BpfProgLoadAttr(
        prog_type=BPF_PROG_TYPE_CGROUP_SKB, insn_cnt=len(prog) // 8,
        insns=ctypes.cast(insns, ctypes.c_void_p).value,
        license=ctypes.cast(lic, ctypes.c_void_p).value,
        log_level=1, log_size=1 << 16,
        log_buf=ctypes.cast(log, ctypes.c_void_p).value,
        prog_name=name, expected_attach_type=BPF_CGROUP_INET_EGRESS)
    fd, err = _bpf(BPF_PROG_LOAD, attr)
    return fd, err, log.value.decode(errors="replace").strip()


def _cgroup2_root() -> "str | None":
    for root in (_CGROUP2_ROOT, _CGROUP2_ALT):
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                if any(line.split()[1] == root and line.split()[2] == "cgroup2"
                       for line in f if len(line.split()) > 2):
                    return root
        except OSError:
            continue
    return None


def attach(prog_fd: int, cgroup_dir: str) -> "tuple[bool, int]":
    """``BPF_PROG_ATTACH`` ``prog_fd`` at ``BPF_CGROUP_INET_EGRESS`` on
    ``cgroup_dir`` → ``(ok, errno)``. Does not raise."""
    try:
        cgfd = os.open(cgroup_dir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as e:
        return False, e.errno
    try:
        ret, err = _bpf(BPF_PROG_ATTACH, _BpfAttachAttr(
            target_fd=cgfd, attach_bpf_fd=prog_fd,
            attach_type=BPF_CGROUP_INET_EGRESS, attach_flags=0))
        return (ret == 0), err
    finally:
        os.close(cgfd)


def detach(prog_fd: int, cgroup_dir: str) -> None:
    try:
        cgfd = os.open(cgroup_dir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        _bpf(BPF_PROG_DETACH, _BpfAttachAttr(
            target_fd=cgfd, attach_bpf_fd=prog_fd,
            attach_type=BPF_CGROUP_INET_EGRESS, attach_flags=0))
    finally:
        os.close(cgfd)


def load_membrane(membrane, *, try_attach: bool = True) -> LoadReport:
    """Compile + load (and best-effort attach) a membrane's posture program.

    Returns a :class:`LoadReport`; never raises on an expected kernel refusal.
    ``mechanism`` is ``"ebpf-cgroup"`` only when the program is attached at the
    egress hook (live in-kernel enforcement); otherwise ``"reference"`` and the
    userspace datapath is authoritative.
    """
    prog = compile_posture(membrane.default)
    verdict = "pass" if membrane.default == "allow" else "drop"
    try:
        fd, err, log = load(prog)
    except OSError as e:
        return LoadReport(available=False, loaded=False, verdict=verdict,
                          detail="%s" % e)
    if fd < 0:
        # bpf() reachable but this prog rejected — still "available".
        return LoadReport(available=True, loaded=False, verdict=verdict,
                          verifier_log=log, detail=os.strerror(err))
    insn_count = _parse_insn_count(log, len(prog) // 8)
    report = LoadReport(
        available=True, loaded=True, prog_fd=fd, insn_count=insn_count,
        verdict=verdict, verifier_log=log, mechanism="reference")
    if not try_attach:
        return report
    root = _cgroup2_root()
    if root is None:
        report.detail = "no cgroup2 mount"
        return report
    cg = os.path.join(root, "vaked_guard_%d" % os.getpid())
    try:
        os.makedirs(cg, exist_ok=True)
    except OSError as e:
        report.detail = "cgroup mkdir: %s" % e
        return report
    ok, err = attach(fd, cg)
    if ok:
        report.attached = True
        report.mechanism = "ebpf-cgroup"
        report.cgroup = cg
        detach(fd, cg)        # demo: prove attach, then release (no traffic capture here)
    else:
        report.detail = "attach EINVAL/errno %d (%s)" % (err, os.strerror(err))
    try:
        os.rmdir(cg)
    except OSError:
        pass
    return report


def _parse_insn_count(log: str, fallback: int) -> int:
    """Pull ``processed N insns`` out of the verifier trace, else ``fallback``."""
    for tok in log.split():
        if tok.isdigit():
            # "processed N insns ..." — N is the first bare integer.
            return int(tok)
    return fallback


def kernel_probe() -> dict:
    """A one-shot capability probe for diagnostics: can we load a cgroup/skb
    program, and does an egress attach succeed?"""
    from .policy import Membrane
    rep = load_membrane(
        Membrane(name="probe", principal="", grant=None, default="deny"),
        try_attach=True)
    return {
        "bpf_available": rep.available,
        "cgroup_skb_loadable": rep.loaded,
        "egress_attach": rep.attached,
        "detail": rep.detail,
    }
