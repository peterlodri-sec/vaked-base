//! Consensus committer — Raft-lite engine, seq-cst fenced, 1024-entry log
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const TransactionState = enum(u8) { uncommitted, staged, finalized };
pub const ConsensusEntry = struct { term_id: u32, log_index: u64, commit_state: TransactionState, payload_checksum: u32 };

pub const RaftLiteEngine = struct {
    state_history: [1024]ConsensusEntry,
    head_index: usize,

    pub fn stageAtomicCommit(self: *RaftLiteEngine, term: u32, check: u32) !void {
        if (self.head_index >= self.state_history.len) return error.LogCapacityExceeded;
        self.state_history[self.head_index] = ConsensusEntry{ .term_id = term, .log_index = self.head_index, .commit_state = .finalized, .payload_checksum = check };
        std.atomic.fence(.seq_cst);
        self.head_index += 1;
    }
};

test "commit until full" {
    var engine = RaftLiteEngine{ .state_history = undefined, .head_index = 0 };
    var i: usize = 0;
    while (i < 1024) : (i += 1) try engine.stageAtomicCommit(1, 0x7C242080);
    try std.testing.expectError(error.LogCapacityExceeded, engine.stageAtomicCommit(1, 0));
}

test "commit preserves ordering" {
    var engine = RaftLiteEngine{ .state_history = undefined, .head_index = 0 };
    try engine.stageAtomicCommit(1, 0xAA);
    try engine.stageAtomicCommit(2, 0xBB);
    try std.testing.expectEqual(@as(u64, 0), engine.state_history[0].log_index);
    try std.testing.expectEqual(@as(u64, 1), engine.state_history[1].log_index);
}
