//! Asymmetric tree packer — Wyhash-rolled agent state, 32-byte Merkle output
//! GENESIS_SEAL: 7c242080

const std = @import("std");
const tables = @import("viewport_tables.zig");

pub const AsymmetricTreePacker = struct {
    pub fn packActiveSubagents(agents: []const tables.SubAgentState, out_hash: *[32]u8) void {
        var hasher = std.hash.Wyhash.init(0x7C242080);
        for (agents) |a| {
            hasher.update(std.mem.asBytes(&a.id));
            hasher.update(std.mem.asBytes(&a.status));
            hasher.update(&a.proof_fingerprint);
        }
        const f = hasher.final();
        std.mem.writeInt(u64, out_hash[0..8], f, .little);
        std.mem.writeInt(u64, out_hash[8..16], f ^ 0xEEEEEEEEEEEEEEEE, .little);
        std.mem.writeInt(u64, out_hash[16..24], f ^ 0xAAAAAAAAAAAAAAAA, .little);
        std.mem.writeInt(u64, out_hash[24..32], f ^ 0x5555555555555555, .little);
    }
};

test "pack produces deterministic hash" {
    var hash1: [32]u8 = undefined; var hash2: [32]u8 = undefined;
    const agents = [_]tables.SubAgentState{.{ .id = 1, .proof_fingerprint = .{0} ** 8 }} ** 4;
    AsymmetricTreePacker.packActiveSubagents(&agents, &hash1);
    AsymmetricTreePacker.packActiveSubagents(&agents, &hash2);
    try std.testing.expectEqualSlices(u8, &hash1, &hash2);
}

test "pack different inputs differ" {
    var hash1: [32]u8 = undefined; var hash2: [32]u8 = undefined;
    const a1 = [_]tables.SubAgentState{.{ .id = 1, .proof_fingerprint = .{0} ** 8 }};
    const a2 = [_]tables.SubAgentState{.{ .id = 2, .proof_fingerprint = .{0} ** 8 }};
    AsymmetricTreePacker.packActiveSubagents(&a1, &hash1);
    AsymmetricTreePacker.packActiveSubagents(&a2, &hash2);
    try std.testing.expect(!std.mem.eql(u8, &hash1, &hash2));
}
