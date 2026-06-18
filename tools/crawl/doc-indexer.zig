//! Doc indexer — compact, compressed, HM-queryable. Our Context7 replacement.
//! Output: hash-chain blob per doc. CrabCC symbol links. No rate limits.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const Zone = enum(u8) { global=0, repo=1, zone=2 };
pub const DocEntry = packed struct { hash: [32]u8, zone: Zone, is_blog: u8, link_count: u8, content_len: u32 };
pub const DocStore = struct {
    arena: std.mem.Allocator,
    entries: std.StringHashMapUnmanaged(DocEntry),

    pub fn init(a: std.mem.Allocator) DocStore { return .{ .arena = a, .entries = .{} }; }

    pub fn load(self: *DocStore, root: []const u8, zone: Zone, is_blog: u8) !void {
        var dir = try std.fs.openDirAbsolute(root, .{ .iterate = true });
        defer dir.close();
        var walk = try dir.walk(self.arena);
        defer walk.deinit();
        while (try walk.next()) |e| {
            if (e.kind != .file) continue;
            if (!std.mem.eql(u8, std.fs.path.extension(e.basename), ".md")) continue;
            const content = dir.readFileAlloc(self.arena, e.path, 10*1024*1024) catch continue;
            var hasher = std.crypto.hash.sha2.Sha256.init(.{});
            hasher.update(content); var hash: [32]u8 = undefined; hasher.final(&hash);
            const path = try std.fs.path.join(self.arena, &.{ root, e.path });
            try self.entries.put(self.arena, path, .{ .hash = hash, .zone = zone, .is_blog = is_blog, .link_count = 0, .content_len = @intCast(content.len) });
        }
    }

    pub fn query(self: *DocStore, prefix: []const u8) void {
        var it = self.entries.iterator();
        while (it.next()) |entry| {
            if (std.mem.startsWith(u8, entry.key_ptr.*, prefix)) {
                std.debug.print("  {s}: {s}\n", .{ @tagName(entry.value_ptr.zone), entry.key_ptr.* });
            }
        }
    }
};

pub fn main() !void {
    var ar = std.heap.ArenaAllocator.init(std.heap.page_allocator); defer ar.deinit();
    var store = DocStore.init(ar.allocator());
    try store.load("docs", .zone, 0);
    try store.load("blog", .global, 1);
    std.debug.print("doc-store: {d} entries · GENESIS_SEAL: 7c242080\n", .{store.entries.count()});
}
