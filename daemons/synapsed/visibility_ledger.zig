//! Ralph-Compliant Visibility Ledger — PII-scrubbed, append-only, zero-alloc
//! GENESIS_SEAL: a48f11ec

const std = @import("std");

pub const NodeType = enum { edge_alpha, edge_beta, internal_anchor, c8_pool_worker };

pub const LogEntry = struct {
    timestamp_ns: u64,
    node_nickname: NodeType,
    chunk_id: u32,
    recursion_depth: u8,
    state_merkle_root: [32]u8,
};

pub const VerifiableGraveyard = struct {
    log_buffer: [1024]LogEntry,
    write_index: usize,

    pub fn init() VerifiableGraveyard {
        return .{ .log_buffer = undefined, .write_index = 0 };
    }

    pub fn appendEvent(self: *VerifiableGraveyard, nickname: NodeType, chunk_id: u32, depth: u8, root: [32]u8) bool {
        if (self.write_index >= self.log_buffer.len) return false;
        self.log_buffer[self.write_index] = LogEntry{
            .timestamp_ns = 0, // std.time.nanoTimestamp() — not available in Zig 0.16
            .node_nickname = nickname,
            .chunk_id = chunk_id,
            .recursion_depth = depth,
            .state_merkle_root = root,
        };
        self.write_index += 1;
        return true;
    }

    pub fn getReadOnlyView(self: *const VerifiableGraveyard) []const LogEntry {
        return self.log_buffer[0..self.write_index];
    }
};

test "append and view" {
    var ledger = VerifiableGraveyard.init();
    const root = [_]u8{0x7C} ** 32;
    try std.testing.expect(ledger.appendEvent(.c8_pool_worker, 1, 3, root));
    try std.testing.expectEqual(@as(usize, 1), ledger.write_index);
    const view = ledger.getReadOnlyView();
    try std.testing.expectEqual(@as(usize, 1), view.len);
    try std.testing.expectEqual(NodeType.c8_pool_worker, view[0].node_nickname);
}

test "buffer boundary" {
    var ledger = VerifiableGraveyard.init();
    const root = [_]u8{0} ** 32;
    var i: usize = 0;
    while (i < 1024) : (i += 1) {
        try std.testing.expect(ledger.appendEvent(.edge_alpha, 0, 0, root));
    }
    try std.testing.expect(!ledger.appendEvent(.edge_alpha, 0, 0, root));
}
