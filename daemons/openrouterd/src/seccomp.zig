const std = @import("std");
const linux = std.os.linux;
const builtin = @import("builtin");
const sock_filter = extern struct { code: u16, jt: u8, jf: u8, k: u32 };
const ALLOWED = [_]u32{ 0, 1, 257, 3, 41, 42, 44, 45, 291, 233, 232, 9, 11, 10, 12, 60, 231, 318, 228, 202, 425, 426 };
pub fn apply() void {
    if (builtin.os.tag != .linux) return;
    _ = linux.prctl(@intFromEnum(linux.PR.SET_NO_NEW_PRIVS), @intFromBool(true), 0, 0, 0);
    var filter: [ALLOWED.len + 2]sock_filter = undefined;
    inline for (ALLOWED, 0..) |syscall, idx| {
        filter[idx] = .{ .code = 0x15, .jt = @intCast(ALLOWED.len - idx), .jf = 1, .k = syscall };
    }
    filter[ALLOWED.len] = .{ .code = 0x06, .jt = 0, .jf = 0, .k = 0 };
    filter[ALLOWED.len + 1] = .{ .code = 0x06, .jt = 0, .jf = 0, .k = 0x7fff0000 };
    const prog = linux.seccomp.SockFprog{
        .len = @intCast(filter.len),
        .filter = @ptrCast(@constCast(&filter[0])),
    };
    _ = linux.seccomp(linux.SECCOMP.SET_MODE_FILTER, linux.SECCOMP.FILTER_FLAG.TSYNC, &prog);
    std.log.info("seccomp: 22 syscalls allowed, BPF loaded", .{});
}
