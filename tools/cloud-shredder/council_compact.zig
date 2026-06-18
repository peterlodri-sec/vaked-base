//! Council matrix — 100-agent packed grid, 64-bit token, bit-parallel sweep
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const CouncilToken = packed struct {
    council_id: u4,
    slot_id: u4,
    recursion_frame: u5,
    syscall_allow_flags: u22,
    merkle_leaf_offset: u29,
};

pub const CouncilMatrixPlane = struct {
    matrix_grid: [100]CouncilToken,
    active_mask: [2]u64,

    pub fn executeCrossReferenceSweep(self: *CouncilMatrixPlane) u8 {
        var mismatch: u8 = 0;
        for (0..100) |idx| {
            const w = idx / 64;
            const b: u6 = @intCast(idx % 64);
            if ((self.active_mask[w] >> b) & 1 == 1 and self.matrix_grid[idx].recursion_frame > 32) mismatch += 1;
        }
        return mismatch;
    }
};

test "sweep with no mismatches" {
    var plane = CouncilMatrixPlane{ .matrix_grid = undefined, .active_mask = .{0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF} };
    var i: usize = 0;
    while (i < 100) : (i += 1) { plane.matrix_grid[i] = .{ .council_id = 0, .slot_id = 0, .recursion_frame = 5, .syscall_allow_flags = 0, .merkle_leaf_offset = 0 }; }
    try std.testing.expectEqual(@as(u8, 0), plane.executeCrossReferenceSweep());
}

test "sweep with mismatches detected" {
    var plane = CouncilMatrixPlane{ .matrix_grid = undefined, .active_mask = .{0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF} };
    var i: usize = 0;
    while (i < 100) : (i += 1) { plane.matrix_grid[i] = .{ .council_id = 0, .slot_id = 0, .recursion_frame = 33, .syscall_allow_flags = 0, .merkle_leaf_offset = 0 }; }
    try std.testing.expect(plane.executeCrossReferenceSweep() > 0);
}
