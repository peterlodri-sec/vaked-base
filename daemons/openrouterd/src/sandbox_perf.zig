const std = @import("std");
pub const SyscallMatrix = struct {
    pub const allowed_mask: u64 = 0x3FFFFF;
    pub fn assertInvariantsDirectly(ptr_plane: usize, length: usize) !void {
        if (ptr_plane == 0 or length == 0) return error.NullMemoryPlaneAddress;
    }
};
test "null" { try std.testing.expectError(error.NullMemoryPlaneAddress, SyscallMatrix.assertInvariantsDirectly(0, 100)); }
test "valid" { var buf: [64]u8 = undefined; try SyscallMatrix.assertInvariantsDirectly(@intFromPtr(&buf), buf.len); }
