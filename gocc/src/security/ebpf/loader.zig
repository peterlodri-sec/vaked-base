// gocc eBPF LSM guard loader — Phase 5
//
// Platform behaviour:
//   macOS / non-Linux : no-op stub; loadGuard() returns an inactive GuardHandle.
//   Linux, no BPF LSM : returns EbpfError.BpfLsmNotAvailable with a diagnostic log.
//   Linux, BPF LSM    : confirms availability and stubs the libbpf load path
//                       (full libbpf cImport wired in a follow-on phase).
//
// GHOST NODE TEST (Linux only, manual):
//   Spawn a child process with a spoofed PPID (using PR_SET_PTRACER or namespace
//   tricks).  Expected: eBPF bprm_check_security returns EACCES for the
//   unauthorized PPID.
//   Run on Linux with BPF LSM enabled: sudo gocc verify --ghost-node

const std = @import("std");
const builtin = @import("builtin");

pub const EbpfError = error{
    BpfLsmNotAvailable,
    LoadFailed,
    AttachFailed,
    MapUpdateFailed,
};

/// Result of loading the eBPF guard.
pub const GuardHandle = struct {
    /// Opaque handle — null on non-Linux or when BPF LSM is unavailable.
    inner: ?*anyopaque = null,
    /// True when the guard is a no-op stub (macOS, no BPF LSM, or libbpf not yet wired).
    /// False only when libbpf is fully wired and the guard is actively enforcing.
    is_stub: bool = true,

    pub fn deinit(self: *GuardHandle) void {
        if (self.inner) |_| {
            // TODO(phase6): call bpf_object__destroy(inner) via cImport of libbpf.
            self.inner = null;
        }
    }

    pub fn isActive(self: *const GuardHandle) bool {
        return self.inner != null;
    }
};

/// Check if BPF LSM is available on this system.
///
/// Returns false immediately on non-Linux platforms.
/// On Linux, reads /sys/kernel/security/lsm and looks for "bpf".
pub fn checkBpfLsmAvailable() bool {
    if (builtin.os.tag != .linux) return false;
    const lsm_path = "/sys/kernel/security/lsm";
    var buf: [512]u8 = undefined;
    const file = std.fs.openFileAbsolute(lsm_path, .{}) catch return false;
    defer file.close();
    const n = file.read(&buf) catch return false;
    return std.mem.indexOf(u8, buf[0..n], "bpf") != null;
}

/// Load and attach the eBPF guard programs.
///
/// On Linux with BPF LSM  : loads compiled guard.bpf.o, attaches LSM + tracepoint.
/// On Linux without BPF LSM: returns EbpfError.BpfLsmNotAvailable with a diagnostic.
/// On macOS / other       : returns a no-op GuardHandle (inner == null).
pub fn loadGuard() EbpfError!GuardHandle {
    if (builtin.os.tag != .linux) {
        std.log.info("gocc eBPF guard: not available on {s}, skipping", .{@tagName(builtin.os.tag)});
        return .{ .is_stub = true };
    }

    if (!checkBpfLsmAvailable()) {
        std.log.warn("gocc eBPF guard: BPF LSM not available (check CONFIG_BPF_LSM=y, lsm=bpf in kernel cmdline)", .{});
        return EbpfError.BpfLsmNotAvailable;
    }

    // Real implementation (follow-on phase):
    //   const c = @cImport(@cInclude("bpf/libbpf.h"));
    //   const obj = c.bpf_object__open("guard.bpf.o") orelse return EbpfError.LoadFailed;
    //   if (c.bpf_object__load(obj) != 0) return EbpfError.LoadFailed;
    //   // attach LSM + tracepoint programs ...
    //   return GuardHandle{ .inner = obj };
    std.log.info("gocc eBPF guard: BPF LSM available, loading guard.bpf.o (stub)", .{});
    return .{ .is_stub = true };
}

/// Register a tgid as authorized in the BPF map.
///
/// flags: 0x01 = enforce process spawn, 0x02 = enforce file access.
/// On non-Linux or when the guard is not active: no-op.
pub fn authorizeProcess(handle: *const GuardHandle, ppid: u32, flags: u8) EbpfError!void {
    if (!handle.isActive()) return;
    // Real: bpf_map__update_elem(authorized_ppids_map, &ppid, &flags, BPF_ANY)
    _ = ppid;
    _ = flags;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test "checkBpfLsmAvailable returns false on macOS" {
    // On macOS (darwin), BPF LSM is unavailable regardless of any file state.
    if (builtin.os.tag == .macos) {
        try std.testing.expect(!checkBpfLsmAvailable());
    }
}

test "loadGuard returns inactive handle on macOS" {
    if (builtin.os.tag == .macos) {
        const handle = try loadGuard();
        try std.testing.expect(!handle.isActive());
    }
}

test "authorizeProcess on inactive handle is a no-op" {
    // Works on all platforms: an inactive handle should not error.
    const handle = GuardHandle{};
    try authorizeProcess(&handle, 1234, 0x01);
}

test "GuardHandle.deinit clears inner" {
    var handle = GuardHandle{ .inner = null };
    handle.deinit();
    try std.testing.expect(!handle.isActive());
}

test "GuardHandle.deinit reaches inner branch when inner is set" {
    // Set a non-null sentinel value to force the `if (self.inner) |_|` branch.
    // This does NOT call bpf_object__destroy — libbpf is not wired yet (TODO phase6).
    var handle = GuardHandle{ .inner = @ptrFromInt(1) };
    handle.deinit();
    try std.testing.expect(handle.inner == null);
    try std.testing.expect(!handle.isActive());
}
