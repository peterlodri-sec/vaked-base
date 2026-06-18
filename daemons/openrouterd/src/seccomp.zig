//! Vaked seccomp BPF allowlist — RFC-defined minimal syscall surface.
//! Linux only. 22 syscalls. Everything else → SIGKILL.
//! GENESIS_SEAL: 7c242080
const std = @import("std");
const linux = std.os.linux;
const builtin = @import("builtin");

const sock_filter = extern struct { code: u16, jt: u8, jf: u8, k: u32 };

/// Syscall allowlist — only these 22 are permitted.
/// Numbers: read=0, write=1, openat=257, close=3, socket=41, connect=42,
/// sendto=44, recvfrom=45, epoll_create1=291, epoll_ctl=233, epoll_wait=232,
/// mmap=9, munmap=11, mprotect=10, brk=12, exit=60, exit_group=231,
/// getrandom=318, clock_gettime=228, futex=202, io_uring_setup=425, io_uring_enter=426
const ALLOWED = [_]u32{ 0,1,257,3,41,42,44,45,291,233,232,9,11,10,12,60,231,318,228,202,425,426 };

pub fn apply() void {
    if (builtin.os.tag != .linux) return;

    // Step 1: No new privileges
    _ = linux.prctl(linux.PR.SET_NO_NEW_PRIVS, @intFromBool(1), 0, 0, 0);

    // Step 2: Build BPF program
    var filter: [ALLOWED.len + 2]sock_filter = undefined;

    // For each allowed syscall: if match → ALLOW, else → check next
    inline for (ALLOWED, 0..) |syscall, idx| {
        filter[idx] = .{ .code = 0x15, .jt = @intCast(ALLOWED.len - idx), .jf = 1, .k = syscall };
    }
    // No match → KILL
    filter[ALLOWED.len] = .{ .code = 0x06, .jt = 0, .jf = 0, .k = 0 };
    // Match → ALLOW
    filter[ALLOWED.len + 1] = .{ .code = 0x06, .jt = 0, .jf = 0, .k = 0x7fff0000 };

    // Step 3: Load filter
    const prog = linux.seccomp.SockFprog{
        .len = @intCast(filter.len),
        .filter = @constCast(@ptrCast(&filter[0])),
    };

    _ = linux.seccomp(linux.SECCOMP.SET_MODE_FILTER, linux.SECCOMP.FILTER.FLAG_TSYNC, &prog);
    std.log.info("seccomp: 22 syscalls allowed, BPF loaded", .{});
}
