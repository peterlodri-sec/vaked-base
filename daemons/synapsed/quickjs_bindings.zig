//! Synapsed QuickJS C-FFI Bindings — mesh state bridge
//! Agents read mesh consensus directly from mmap via pointer.
//! GENESIS_SEAL: 7c242080
const std = @import("std");
const protocol = @import("protocol.zig");

pub const MeshStateBridge = extern struct {
    current_term: u32,
    node_state: u8,
    merkle_root: [32]u8,
    _pad: [27]u8,
};

/// Map mesh state from mmap arena to QuickJS-readable struct
pub fn mapMeshState(mmap: []align(std.heap.page_size_min) u8, mesh: *protocol.SynapsedMesh) *MeshStateBridge {
    const bridge = @as(*MeshStateBridge, @ptrCast(@alignCast(mmap.ptr)));
    bridge.current_term = mesh.current_term;
    bridge.node_state = 0; // Active
    const root = mesh.merkleRoot();
    @memcpy(&bridge.merkle_root, &root);
    return bridge;
}

/// QuickJS FFI: getMeshState(arrayBuffer) → { term, state }
/// Called from agent JS: const mesh = synapsed.getMeshState(arenaBuffer);
pub fn getMeshState(bridge: *MeshStateBridge) struct { term: u32, state: u8 } {
    return .{ .term = bridge.current_term, .state = bridge.node_state };
}

/// QuickJS FFI: proposeBlock(payload) → bool
/// Agents trigger cross-daemon verification
pub fn proposeBlock(mesh: *protocol.SynapsedMesh, payload: []const u8) !void {
    const slot = protocol.LedgerSlot{
        .slot_id = 1,
        .agent_id = 0,
        .depth = 0,
        .reserved = 0,
        .term = mesh.current_term + 1,
        .prev_hash = mesh.merkleRoot(),
        .payload_hash = blk: {
            var h = std.crypto.hash.sha2.Sha256.init(.{});
            h.update(payload);
            var out: [32]u8 = undefined;
            h.final(&out);
            break :blk out;
        },
        .timestamp = @intCast(0),
    };
    mesh.writeSlot(0, slot);
}

test "mesh state bridge" {
    var buf: [4096]u8 align(std.heap.page_size_min) = undefined;
    @memset(&buf, 0);
    const id = [_]u8{1} ** 32;
    var mesh = try protocol.SynapsedMesh.init(std.testing.allocator, &buf, id);
    defer mesh.deinit();

    const bridge = mapMeshState(buf[0..], &mesh);
    const state = getMeshState(bridge);
    try std.testing.expectEqual(@as(u32, 0), state.term);
    try std.testing.expectEqual(@as(u8, 0), state.state);
}

test "propose block updates merkle" {
    var buf: [4096]u8 align(std.heap.page_size_min) = undefined;
    @memset(&buf, 0);
    const id = [_]u8{1} ** 32;
    var mesh = try protocol.SynapsedMesh.init(std.testing.allocator, &buf, id);
    defer mesh.deinit();

    const root_before = mesh.merkleRoot();
    try proposeBlock(&mesh, "test payload");
    const root_after = mesh.merkleRoot();
    try std.testing.expect(!std.mem.eql(u8, &root_before, &root_after));
}
