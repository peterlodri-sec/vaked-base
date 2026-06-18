//! Doc indexer — fiber-mesh HM. Each doc is a node. Links are edges.
//! SHA256-addressed. HM-queryable. Mesh-native fiber topology.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const NodeKind = enum(u8) { doc=0, link=1, tag=2, symbol=3 };
pub const Zone = enum(u8) { global=0, repo=1, zone=2 };

pub const Fiber = packed struct {
    hash: [32]u8,       // SHA256 content address
    kind: NodeKind,     // doc/link/tag/symbol
    zone: Zone,         // global/repo/zone
    is_blog: u8,        // 0=docs, 1=blog
    links: u16,         // outgoing edge count
    content_len: u32,   // bytes
};

pub const FiberMesh = struct {
    arena: std.mem.Allocator,
    nodes: std.StringHashMapUnmanaged(Fiber),  // key=path → fiber
    edges: std.StringHashMapUnmanaged(std.ArrayListUnmanaged([]const u8)), // path→linked paths

    pub fn init(a: std.mem.Allocator) FiberMesh {
        return .{ .arena = a, .nodes = .{}, .edges = .{} };
    }

    pub fn load(self: *FiberMesh, root: []const u8, zone: Zone, is_blog: u8) !void {
        var dir = try std.fs.openDirAbsolute(root, .{ .iterate = true });
        defer dir.close();
        var walk = try dir.walk(self.arena);
        defer walk.deinit();
        while (try walk.next()) |e| {
            if (e.kind != .file) continue;
            if (!std.mem.eql(u8, std.fs.path.extension(e.basename), ".md")) continue;
            const content = dir.readFileAlloc(self.arena, e.path, 10*1024*1024) catch continue;
            var h = std.crypto.hash.sha2.Sha256.init(.{});
            h.update(content); var hash: [32]u8 = undefined; h.final(&hash);
            const path = try std.fs.path.join(self.arena, &.{ root, e.path });

            // Extract links: [foo](bar.md) → edges
            var link_list: std.ArrayListUnmanaged([]const u8) = .{ .items = &.{}, .capacity = 0 };
            var pos: usize = 0;
            while (std.mem.indexOfScalarPos(u8, content, pos, '[')) |open| {
                if (std.mem.indexOfScalarPos(u8, content, open, ']')) |close| {
                    if (close + 1 < content.len and content[close+1] == '(') {
                        if (std.mem.indexOfScalarPos(u8, content, close+2, ')')) |paren_end| {
                            const target = content[close+2..paren_end];
                            if (std.mem.endsWith(u8, target, ".md")) {
                                try link_list.append(self.arena, try self.arena.dupe(u8, target));
                            }
                            pos = paren_end + 1; continue;
                        }
                    }
                }
                pos += 1;
                if (pos >= content.len) break;
            }

            try self.nodes.put(self.arena, path, .{
                .hash = hash, .kind = .doc, .zone = zone,
                .is_blog = is_blog, .links = @intCast(link_list.items.len), .content_len = @intCast(content.len),
            });
            if (link_list.items.len > 0) try self.edges.put(self.arena, path, link_list);
        }
    }

    /// Query: prefix HM → list fibers with their edge count
    pub fn query(self: *FiberMesh, prefix: []const u8, writer: anytype) !void {
        var it = self.nodes.iterator();
        while (it.next()) |entry| {
            if (std.mem.startsWith(u8, entry.key_ptr.*, prefix)) {
                const f = entry.value_ptr;
                try writer.print("  {s} {s} [{d} edges]\n", .{ @tagName(f.zone), entry.key_ptr.*, f.links });
            }
        }
    }

    /// Trace: follow edges from a fiber
    pub fn trace(self: *FiberMesh, path: []const u8, depth: u8) void {
        if (depth == 0) return;
        if (self.edges.get(path)) |links| {
            for (links.items) |link| {
                std.debug.print("    -> {s}\n", .{link});
                @setEvalBranchQuota(1000);
                self.trace(link, depth - 1);
            }
        }
    }
};

pub fn main() !void {
    var ar = std.heap.ArenaAllocator.init(std.heap.page_allocator); defer ar.deinit();
    var mesh = FiberMesh.init(ar.allocator());
    try mesh.load("docs", .zone, 0);
    try mesh.load("blog", .global, 1);
    const se = std.io.getStdErr().writer();
    try se.print("fiber-mesh: {d} nodes · links extracted\n", .{mesh.nodes.count()});
    try se.print("GENESIS_SEAL: 7c242080\n", .{});
}
