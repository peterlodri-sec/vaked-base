const std = @import("std");

pub const NodeKind = enum { pipeline_stage, config_root };

pub const ArpNode = struct {
    id: []const u8,
    kind: NodeKind,
    name: []const u8,
    props: std.StringHashMapUnmanaged([]const u8),

    pub fn deinit(self: *ArpNode, alloc: std.mem.Allocator) void {
        self.props.deinit(alloc);
    }

    pub fn setProp(self: *ArpNode, alloc: std.mem.Allocator, key: []const u8, val: []const u8) !void {
        try self.props.put(alloc, key, val);
    }

    pub fn getProp(self: *const ArpNode, key: []const u8) ?[]const u8 {
        return self.props.get(key);
    }
};

pub const ArpEdge = struct {
    from: []const u8,
    to: []const u8,
    label: []const u8, // "pipeline"
};

pub const ArpGraph = struct {
    alloc: std.mem.Allocator,
    nodes: std.StringArrayHashMapUnmanaged(ArpNode),
    edges: std.ArrayListUnmanaged(ArpEdge),
    config: std.StringHashMapUnmanaged([]const u8), // global @(...) params

    pub fn init(alloc: std.mem.Allocator) ArpGraph {
        return .{
            .alloc = alloc,
            .nodes = .empty,
            .edges = .empty,
            .config = .empty,
        };
    }

    pub fn deinit(self: *ArpGraph) void {
        var it = self.nodes.iterator();
        while (it.next()) |entry| entry.value_ptr.deinit(self.alloc);
        self.nodes.deinit(self.alloc);
        self.edges.deinit(self.alloc);
        self.config.deinit(self.alloc);
    }

    pub fn addNode(self: *ArpGraph, node: ArpNode) !void {
        try self.nodes.put(self.alloc, node.id, node);
    }

    pub fn addEdge(self: *ArpGraph, edge: ArpEdge) !void {
        try self.edges.append(self.alloc, edge);
    }
};
