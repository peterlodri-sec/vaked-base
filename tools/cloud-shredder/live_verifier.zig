const std = @import("std");
pub const LiveProof = struct {
    compiled_genesis_hash: [32]u8,
    active_dns_nickname: []const u8,
    pub fn assertLiveInvariants(self: LiveProof, live_root: [32]u8) bool {
        return std.mem.eql(u8, &self.compiled_genesis_hash, &live_root);
    }
};
test "invariant match" {
    const h = [_]u8{0x7C} ** 32;
    const p = LiveProof{ .compiled_genesis_hash = h, .active_dns_nickname = "c8-pool" };
    try std.testing.expect(p.assertLiveInvariants(h));
}
test "invariant mismatch" {
    const p = LiveProof{ .compiled_genesis_hash = [_]u8{0x7C} ** 32, .active_dns_nickname = "c8" };
    try std.testing.expect(!p.assertLiveInvariants([_]u8{0x00} ** 32));
}
