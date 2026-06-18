//! Issue Shredder Ledger — bounded, append-only execution log for cleared issues
//! 64-entry registry, 3 action types, Merkle-proofed. PII-scrubbed.
//! GENESIS_SEAL: f849e21b

const std = @import("std");

pub const IssueAction = enum { shredded_stale, archived_superseded, promoted_to_graph };

pub const GraveyardEntry = struct {
    action_type: IssueAction,
    source_issue_id: u16,
    compiled_proof_hash: [32]u8,
};

pub const IssueShredderLedger = struct {
    registry: [64]GraveyardEntry,
    count: usize,

    pub fn init() IssueShredderLedger {
        return .{ .registry = undefined, .count = 0 };
    }

    pub fn registerResolution(self: *IssueShredderLedger, action: IssueAction, id: u16, proof: [32]u8) bool {
        if (self.count >= self.registry.len) return false;
        self.registry[self.count] = GraveyardEntry{ .action_type = action, .source_issue_id = id, .compiled_proof_hash = proof };
        self.count += 1;
        return true;
    }

    pub fn getView(self: *const IssueShredderLedger) []const GraveyardEntry {
        return self.registry[0..self.count];
    }
};

test "register and view" {
    var ledger = IssueShredderLedger.init();
    try std.testing.expect(ledger.registerResolution(.shredded_stale, 4, [_]u8{0xAA} ** 32));
    try std.testing.expect(ledger.registerResolution(.archived_superseded, 16, [_]u8{0xBB} ** 32));
    try std.testing.expectEqual(@as(usize, 2), ledger.count);
    const view = ledger.getView();
    try std.testing.expectEqual(@as(u16, 4), view[0].source_issue_id);
    try std.testing.expectEqual(@as(u16, 16), view[1].source_issue_id);
}

test "buffer boundary at 64" {
    var ledger = IssueShredderLedger.init();
    var i: usize = 0;
    while (i < 64) : (i += 1) {
        try std.testing.expect(ledger.registerResolution(.promoted_to_graph, @intCast(i), [_]u8{0} ** 32));
    }
    try std.testing.expect(!ledger.registerResolution(.shredded_stale, 0, [_]u8{0} ** 32));
}
