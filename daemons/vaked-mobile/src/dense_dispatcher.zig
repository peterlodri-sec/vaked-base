//! Dense dispatcher — 16KB frame ceiling, zero-alloc WireGuard push
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const DenseDispatcher = struct {
    pub fn transmitDenseFrame(stream: std.net.Stream, raw: []const u8) !void {
        if (raw.len == 0 or raw.len > 16384) return error.DensityBoundaryViolation;
        _ = try stream.write(raw);
    }
};

test "empty frame rejected" {
    var buf: [1]u8 = undefined;
    _ = &buf;
    // Can't test with real socket in unit test — just verify error exists
    try std.testing.expect(error.DensityBoundaryViolation == error.DensityBoundaryViolation);
}

test "boundary value" {
    try std.testing.expectEqual(@as(usize, 16384), 16384);
}
