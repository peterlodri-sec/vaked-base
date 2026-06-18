const std = @import("std");
pub const Zone = enum { global, repo, zone };
pub const DocEntry = struct { path: []const u8, content_hash: [32]u8, content: []const u8, zone: Zone, repo: ?[]const u8, symbol_links: ?[][]const u8 };
pub const DocIndex = struct {
    allocator: std.mem.Allocator,
    entries: std.StringHashMapUnmanaged(DocEntry),
    pub fn init(a: std.mem.Allocator) DocIndex { return DocIndex{ .allocator = a, .entries = .{} }; }
    pub fn ingest(self: *DocIndex, path: []const u8, content: []const u8, zone: Zone, repo: ?[]const u8) !void {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        h.update(content); var hash: [32]u8 = undefined; h.final(&hash);
        try self.entries.put(self.allocator, path, DocEntry{ .path = try self.allocator.dupe(u8, path), .content_hash = hash, .content = try self.allocator.dupe(u8, content), .zone = zone, .repo = if (repo) |r| try self.allocator.dupe(u8, r) else null, .symbol_links = null });
    }
    pub fn get(self: *DocIndex, path: []const u8) ?DocEntry { return self.entries.get(path); }
    pub fn count(self: *DocIndex) usize { return self.entries.count(); }
};
test "ingest" { var i = DocIndex.init(std.testing.allocator); try i.ingest("/zig/build", "fn build","global",null); try std.testing.expectEqual(@as(usize,1),i.count()); }
test "hash" { var i = DocIndex.init(std.testing.allocator); try i.ingest("/x","a",.global,null); _=i.get("/x").?; }
