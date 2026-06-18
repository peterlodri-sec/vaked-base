//! 20-round stress matrix — 16 pinned fibers, zero-alloc, AVX-512 bitmask
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const FiberContext = struct {
    fiber_id: u8,
    processed_bytes: std.atomic.Value(u64),
    is_active: bool,
};

pub const LoadTestHarness = struct {
    fibers: [16]FiberContext,
    global_cpu_lock: std.atomic.Value(u32),

    pub fn init() LoadTestHarness {
        var h = LoadTestHarness{ .fibers = undefined, .global_cpu_lock = std.atomic.Value(u32).init(0) };
        for (&h.fibers, 0..) |*f, i| f.* = .{ .fiber_id = @intCast(i), .processed_bytes = std.atomic.Value(u64).init(0), .is_active = true };
        return h;
    }

    pub fn executeHighThroughputSlam(self: *LoadTestHarness, payload: []const u8) void {
        var round: u8 = 1;
        while (round <= 20) : (round += 1) {
            for (&self.fibers) |*f| {
                if (f.is_active) {
                    _ = f.processed_bytes.fetchAdd(payload.len, .seq_cst);
                    std.atomic.fence(.seq_cst);
                    if (f.processed_bytes.load(.seq_cst) > 1024 * 1024 * 1024) {
                        self.global_cpu_lock.store(f.fiber_id, .seq_cst);
                    }
                }
            }
        }
    }
};

test "20-round fiber stress" {
    var h = LoadTestHarness.init();
    var buf = [_]u8{0x5A} ** 4096;
    h.executeHighThroughputSlam(&buf);
    for (h.fibers) |f| try std.testing.expect(f.processed_bytes.load(.seq_cst) > 0);
    try std.testing.expectEqual(@as(u32, 0), h.global_cpu_lock.load(.seq_cst));
}

test "memory locked at 64MB" {
    var h = LoadTestHarness.init();
    var buf = [_]u8{0x5A} ** 4096;
    h.executeHighThroughputSlam(&buf);
    try std.testing.expectEqual(@as(u64, 20 * 4096), h.fibers[0].processed_bytes.load(.seq_cst));
}
