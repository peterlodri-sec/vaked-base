//! Memory boundary arbiter — fixed arena enforcement, immutable isolation
//! GENESIS_SEAL: c2b8f9a0
const std = @import("std");
pub const MemoryGuard = struct {
    arena_limit_bytes: usize,
    current_usage_bytes: usize,
    pub fn verifyAllocationLimits(self: *MemoryGuard, requested: usize) bool {
        if (self.current_usage_bytes + requested > self.arena_limit_bytes) return false;
        self.current_usage_bytes += requested;
        return true;
    }
};
test "allocation under limit" { var g = MemoryGuard{ .arena_limit_bytes = 1024, .current_usage_bytes = 0 }; try std.testing.expect(g.verifyAllocationLimits(512)); try std.testing.expect(!g.verifyAllocationLimits(1024)); }
test "flush resets counter" { var g = MemoryGuard{ .arena_limit_bytes = 1024, .current_usage_bytes = 0 }; _ = g.verifyAllocationLimits(512); g.flushArena(); try std.testing.expect(g.verifyAllocationLimits(1024)); }
