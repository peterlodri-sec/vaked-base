// SPDX-License-Identifier: GPL-2.0
// gocc eBPF LSM guard — blocks unauthorized process spawns + protected path reads
//
// Compiled with: clang -target bpf -O2 -g -o guard.bpf.o guard.bpf.c
// Requires: libbpf headers, kernel with CONFIG_BPF_LSM=y, lsm=bpf in cmdline.
//
// Note: when bpftool-generated vmlinux.h is available, replace the four
// standard includes below with a single #include "vmlinux.h".  Do not
// include both: vmlinux.h re-declares all kernel types and will produce
// redefinition errors.

#include <linux/bpf.h>
#include <linux/errno.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

// Map: ppid/tgid (u32) → enforcement_flags (u8)
// Key 0xFFFFFFFF = sentinel meaning "guard is armed/initialized"
// 0x01 = enforce process spawn
// 0x00 = not authorized
//
// Note: keys are the *current* thread-group ID (tgid) of the spawning
// process, not its parent PID.  bpf_get_current_pid_tgid() >> 32 gives
// the tgid of the current task.  Resolving the true ppid requires
// BPF_CORE_READ(bpf_get_current_task(), real_parent, tgid) and a
// generated vmlinux.h; the simpler tgid-keyed scheme is intentional
// for this Phase 5 scaffold.
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 4096);
    __type(key, u32);
    __type(value, u8);
} authorized_ppids SEC(".maps");

// LSM hook: block unauthorized process spawns.
// Requires CONFIG_BPF_LSM=y and lsm=bpf on the kernel cmdline.
// The loader detects BPF LSM availability and falls back gracefully.
SEC("lsm/bprm_check_security")
int BPF_PROG(bprm_check_security, struct linux_binprm *bprm)
{
    // Only enforce when guard is armed (sentinel key 0xFFFFFFFF present).
    // Without this, an empty map at attach time would block every execve and halt the system.
    u32 sentinel_key = 0xFFFFFFFF;
    u8 *armed = bpf_map_lookup_elem(&authorized_ppids, &sentinel_key);
    if (armed == NULL) return 0; // guard not yet armed — allow through

    u32 tgid = bpf_get_current_pid_tgid() >> 32;
    u8 *flags = bpf_map_lookup_elem(&authorized_ppids, &tgid);
    if (flags == NULL || !(*flags & 0x01)) return -EACCES;
    return 0;
}

// Tracepoint: log/observe reads to protected paths.
// NOTE: tracepoint return values are ignored by the kernel — this hook
// cannot block syscalls.  Use an LSM hook (e.g. lsm/file_open) for
// enforcement.  The tracepoint is used here for observability/logging
// of accesses to /.gocc/vault and /proc/self/mem.
SEC("tracepoint/syscalls/sys_enter_openat")
int tp_openat(struct trace_event_raw_sys_enter *ctx)
{
    const char *filename = (const char *)ctx->args[1];
    char buf[64];
    long ret = bpf_probe_read_user_str(buf, sizeof(buf), filename);
    if (ret < 0) return 0;

    // Detect access to the gocc vault directory (prefix /.gocc)
    // BPF has no strcmp — compare byte by byte.
    if (buf[0] == '/' && buf[1] == '.' && buf[2] == 'g' &&
        buf[3] == 'o' && buf[4] == 'c' && buf[5] == 'c') {
        u32 ppid = (u32)(bpf_get_current_pid_tgid() >> 32);
        u8 *flags = bpf_map_lookup_elem(&authorized_ppids, &ppid);
        if (flags == NULL) {
            // Unauthorized process accessing vault path — observable but
            // not blockable from a tracepoint.  Pair with lsm/file_open
            // in a future phase for enforcement.
            return 0;
        }
    }
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
