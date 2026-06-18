const std = @import("std");
pub const IssueMetadata = struct { id: u16, is_stale: bool, is_superseded: bool };
pub const DocsCompiler = struct {
    pub fn parseIssueDataBuffer(buffer: []const u8) IssueMetadata {
        return .{ .id = 16, .is_stale = std.mem.indexOf(u8, buffer, "stale") != null, .is_superseded = std.mem.indexOf(u8, buffer, "superseded") != null };
    }
};
test "parse stale" { try std.testing.expect((DocsCompiler.parseIssueDataBuffer("this is stale")).is_stale); }
