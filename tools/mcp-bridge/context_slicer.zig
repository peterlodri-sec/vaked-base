const std = @import("std");
pub const ContextFrame = struct { token_count: u32, identity_hash: u64, payload_slice: []const u8 };
pub const RemoteContextEngine = struct {
    pub fn sliceContextInPlace(raw_stream: []u8, boundary: []const u8) !ContextFrame {
        var t = std.mem.tokenizeSequence(u8, raw_stream, boundary);
        const h = t.next() orelse return error.InvalidFrameBoundary;
        return .{ .token_count = @intCast(h.len), .identity_hash = std.hash.Wyhash.hash(42, h), .payload_slice = t.rest() };
    }
};
test "slice" { var buf: [100]u8 = undefined; const s = try RemoteContextEngine.sliceContextInPlace(&buf, ","); _ = s; }
