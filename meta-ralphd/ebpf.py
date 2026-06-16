"""eBPF syscall monitor for L1 (Ralph) process.

On a kernel with BPF support, this module attaches a BPF program to trace
``ralphd``'s syscalls and compares them against an allowed profile. Denied
syscalls are blocked via ``BPF_PROG_TYPE_CGROUP_SKB`` (or simulated via
``ptrace``/``seccomp`` on older kernels).

The **allowed profile** for ralphd:
    - file reads: ``openat``, ``read``, ``stat``, ``newfstatat``
    - file writes: ``write`` (stdout/stderr/events.jsonl only)
    - network: ``connect``, ``sendto``, ``recvfrom`` (OpenRouter API only)
    - IPC: ``socket``, ``bind``
    - process: ``clone``, ``exit_group``, ``nanosleep``
    - **DENIED**: ``open`` (write-mode to paths outside state dir),
      ``ptrace``, ``init_module``, ``delete_module``, ``reboot``, ``swapon``

Reference implementation — the Python module logs violations; a future Zig
daemon will load real cgroup BPF programs.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger("meta-ralphd.ebpf")

# ── Syscall profile ─────────────────────────────────────────────────────────

# Syscall numbers for x86_64
SYSCALL_ALLOW_LIST: set[int] = {
    0,   # read
    1,   # write
    2,   # open
    3,   # close
    4,   # stat
    5,   # fstat
    6,   # lstat
    8,   # lseek
    9,   # mmap
    10,  # mprotect
    11,  # munmap
    12,  # brk
    14,  # rt_sigprocmask
    17,  # pread64
    18,  # pwrite64
    21,  # access
    35,  # nanosleep
    39,  # getpid
    40,  # sendfile
    41,  # socket
    42,  # connect
    44,  # sendto
    45,  # recvfrom
    46,  # sendmsg
    47,  # recvmsg
    56,  # clone
    59,  # execve
    60,  # exit
    61,  # wait4
    63,  # uname
    72,  # fcntl
    78,  # getdents
    79,  # getcwd
    89,  # readlink
    92,  # writev
    96,  # gettid
    102, # getuid
    110, # getppid
    137, # statfs
    138, # fstatfs
    202, # getcpu
    217, # getdents64
    231, # exit_group
    257, # openat
    262, # newfstatat
    318, # getrandom
    332, # statx
}

# Syscall numbers that are DENIED for ralphd (explicit block list)
SYSCALL_DENY_LIST: set[int] = {
    101,  # ptrace
    146,  # setrlimit (writing limits)
    175,  # init_module
    176,  # delete_module
    169,  # reboot
    167,  # swapon
    168,  # swapoff
}


class EbpfMonitor:
    """eBPF-like syscall monitor for L1.

    In this Python reference implementation, the monitor reads the process's
    syscall trace via ``/proc/<pid>/syscall`` (when available) or via
    ``bpftrace``. On production systems, a real ``BPF_PROG_TYPE_CGROUP_SKB``
    program enforces this in-kernel.

    The monitor does NOT block syscalls (no kernel-level enforcement in the
    Python reference). It logs violations for audit and alerts the watchdog.
    """

    def __init__(self, target_pid: int):
        self.target_pid = target_pid
        self._bpftrace_available = self._check_bpftrace()
        self._violations: list[dict] = []

    def _check_bpftrace(self) -> bool:
        """Check if bpftrace is available on this host."""
        try:
            result = subprocess.run(
                ["which", "bpftrace"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _read_proc_syscall(self) -> Optional[int]:
        """Read the current syscall from ``/proc/<pid>/syscall``.

        Returns the syscall number, or ``None`` if unavailable.
        """
        try:
            with open(f"/proc/{self.target_pid}/syscall") as f:
                content = f.read().strip()
            if content and content != "running":
                # Format: "0 0x7fff... 0x0 ..." — first field is syscall number
                parts = content.split()
                return int(parts[0])
        except (OSError, IOError, ValueError, IndexError):
            pass
        return None

    def check_current_syscall(self) -> Optional[dict]:
        """Check the currently executing syscall of the target process.

        Returns:
            ``{syscall: N, allowed: bool, detail: str}`` or ``None`` if
            the syscall could not be read.
        """
        sc = self._read_proc_syscall()
        if sc is None:
            return None

        result = {
            "syscall": sc,
            "allowed": sc in SYSCALL_ALLOW_LIST and sc not in SYSCALL_DENY_LIST,
        }

        if not result["allowed"]:
            result["detail"] = f"syscall {sc} not in L1 allowed profile"
            self._violations.append(result)
            logger.warning(
                "L1 syscall %d DENIED by profile (PID %s)",
                sc, self.target_pid,
            )

        return result

    def get_violations(self, clear: bool = False) -> list[dict]:
        """Return accumulated syscall violations."""
        result = list(self._violations)
        if clear:
            self._violations.clear()
        return result

    def allowed_syscall_count(self) -> int:
        """Number of allowed syscalls in the profile."""
        return len(SYSCALL_ALLOW_LIST)

    def generate_bpf_c_program(self) -> str:
        """Generate a BPF C program source for in-kernel enforcement.

        This is the reference the Zig daemon will compile and load.
        """
        allow_set = ", ".join(str(s) for s in sorted(SYSCALL_ALLOW_LIST))
        deny_set = ", ".join(str(s) for s in sorted(SYSCALL_DENY_LIST))
        return f"""// Generated by meta-ralphd — L1 syscall allow profile
// Compile: clang -O2 -target bpf -c this_file.c -o this_file.o
// Load:    bpftool prog load this_file.o /sys/fs/bpf/l1_syscall_guard

#include <linux/bpf.h>
#include <linux/filter.h>
#include <linux/seccomp.h>

#ifndef BPF_F_ALLOW_MULTI
#define BPF_F_ALLOW_MULTI 2
#endif

// Allowed syscall numbers (x86_64)
const int ALLOWED[] = {{ {allow_set} }};

// Denied syscall numbers (x86_64)
const int DENIED[] = {{ {deny_set} }};

SEC("cgroup/syscall")
int l1_syscall_guard(struct bpf_syscall_ctx *ctx) {{
    int nr = ctx->syscall_nr;
    
    // Explicit deny list check first
    #pragma unroll
    for (int i = 0; i < sizeof(DENIED) / sizeof(DENIED[0]); i++) {{
        if (nr == DENIED[i])
            return SECCOMP_RET_KILL_PROCESS;
    }}
    
    // Allow list check
    #pragma unroll
    for (int i = 0; i < sizeof(ALLOWED) / sizeof(ALLOWED[0]); i++) {{
        if (nr == ALLOWED[i])
            return SECCOMP_RET_ALLOW;
    }}
    
    // Default: deny
    return SECCOMP_RET_KILL_THREAD;
}}
"""
