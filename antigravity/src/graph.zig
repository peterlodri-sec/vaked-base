const std = @import("std");
const linux = std.os.linux;

pub const Node = struct {
    name: []const u8,
    kind: []const u8, // "edge" | "node" | "trust"
};

pub const Edge = struct {
    from: []const u8,
    to: []const u8,
    trust: f64,
};

pub const Graph = struct {
    nodes: std.ArrayListUnmanaged(Node),
    edges: std.ArrayListUnmanaged(Edge),
    allocator: std.mem.Allocator,

    pub fn init(a: std.mem.Allocator) Graph {
        return Graph{
            .nodes = .{ .items = &.{}, .capacity = 0 },
            .edges = .{ .items = &.{}, .capacity = 0 },
            .allocator = a,
        };
    }

    pub fn addNode(self: *Graph, name: []const u8, kind: []const u8) !void {
        try self.nodes.append(self.allocator, Node{ .name = name, .kind = kind });
    }

    pub fn addEdge(self: *Graph, from: []const u8, to: []const u8, trust: f64) !void {
        try self.edges.append(self.allocator, Edge{ .from = from, .to = to, .trust = trust });
    }

    pub fn toJson(self: Graph, a: std.mem.Allocator) ![]u8 {
        var buf = std.ArrayListUnmanaged(u8){ .items = &.{}, .capacity = 0 };
        try buf.appendSlice(a, "{\"nodes\":[");
        for (self.nodes.items, 0..) |n, i| {
            if (i > 0) try buf.append(a, ',');
            try buf.appendSlice(a, "{\"name\":\"");
            try buf.appendSlice(a, n.name);
            try buf.appendSlice(a, "\",\"kind\":\"");
            try buf.appendSlice(a, n.kind);
            try buf.appendSlice(a, "\"}");
        }
        try buf.appendSlice(a, "],\"edges\":[");
        for (self.edges.items, 0..) |e, i| {
            if (i > 0) try buf.append(a, ',');
            try buf.appendSlice(a, "{\"from\":\"");
            try buf.appendSlice(a, e.from);
            try buf.appendSlice(a, "\",\"to\":\"");
            try buf.appendSlice(a, e.to);
            try buf.appendSlice(a, "\",\"trust\":");
            try buf.appendSlice(a, try std.fmt.allocPrint(a, "{d}", .{e.trust}));
            try buf.appendSlice(a, "}");
        }
        try buf.appendSlice(a, "]}");
        return buf.items;
    }

    pub fn saveToFile(self: Graph, a: std.mem.Allocator) !void {
        const json = try self.toJson(a);
        const path = a.dupeZ(u8, ".ag/graph.json") catch return;
        const fd = linux.open(path, @bitCast(@as(u32, 0x241)), 0o644);
        const fdi: i32 = @intCast(fd);
        defer _ = linux.close(fdi);
        _ = linux.write(fdi, json.ptr, json.len);
    }

    pub fn loadFromFile(self: *Graph, a: std.mem.Allocator) !void {
        const path = a.dupeZ(u8, ".ag/graph.json") catch return;
        const fd_u = linux.open(path, @bitCast(@as(u32, 0)), 0);
        const fd: i32 = @intCast(fd_u);
        if (fd < 0) return;
        defer _ = linux.close(fd);
        var buf: [4096]u8 = undefined;
        const n = linux.read(fd, &buf, buf.len);
        if (n <= 0) return;
            @memset(&buf, 0);
    }
};
