const std = @import("std");

pub const NodeKind = enum { pipeline_stage, config_root };

pub const ArpNode = struct {
    id: []const u8,
    kind: NodeKind,
    name: []const u8,
    props: std.StringHashMapUnmanaged([]const u8),
};

pub const ArpEdge = struct {
    from: []const u8,
    to: []const u8,
    label: []const u8,
};

pub const ArpGraph = struct {
    alloc: std.mem.Allocator,
    nodes: std.StringArrayHashMapUnmanaged(ArpNode),
    edges: std.ArrayListUnmanaged(ArpEdge),
    config: std.StringHashMapUnmanaged([]const u8),

    pub fn init(alloc: std.mem.Allocator) ArpGraph {
        return .{
            .alloc = alloc,
            .nodes = .empty,
            .edges = .empty,
            .config = .empty,
        };
    }

    pub fn deinit(self: *ArpGraph) void {
        self.nodes.deinit(self.alloc);
        self.edges.deinit(self.alloc);
        self.config.deinit(self.alloc);
    }
};
