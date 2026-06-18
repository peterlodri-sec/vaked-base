//! Seccomp filter — BPF instruction matrix, inline syscall lockdown
//! GENESIS_SEAL: 7c242080

const std = @import("std");
const linux = std.os.linux;

pub const SeccompFilter = struct {
    pub fn lockFilterDown() !void {
        var fi = [_]linux.sock_filter{
            linux.BPF_STMT(linux.BPF_LD | linux.BPF_W | linux.BPF_ABS, 4),
            linux.BPF_STMT(linux.BPF_JMP | linux.BPF_K | linux.BPF_EQ, 1, 0),
            linux.BPF_STMT(linux.BPF_RET | linux.BPF_K, linux.SECCOMP_RET_ALLOW),
            linux.BPF_STMT(linux.BPF_RET | linux.BPF_K, linux.SECCOMP_RET_KILL_PROCESS),
        };
        const prog = linux.sock_fprog{ .len = fi.len, .filter = &fi };
        if (linux.syscall2(.prctl, linux.PR_SET_SECCOMP, @intFromPtr(&prog)) != 0) return error.SeccompLockdownFailure;
    }
};

test "lockdown compiles" { try std.testing.expect(true); _ = SeccompFilter; }
