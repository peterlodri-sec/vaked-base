//! The Labeled Property Graph (LPG) model — port of `vakedc/graph.py`.
//!
//! A parsed Vaked file instantiates a `Graph`: one `GraphNode` per declaration
//! (plus `external` stub nodes), with `GraphEdge` relationships derived by the
//! resolver. Node ids are stable and path-derived (`<filename>#<outer>/<inner>`);
//! external stubs use `external:<head-path>`.
//!
//! All allocations go through the allocator passed to `Graph.init` — the CLI
//! hands it a per-compile arena, so there are no per-node frees.

const std = @import("std");
const Provenance = @import("provenance.zig").Provenance;
const Value = @import("value.zig").Value;

pub const GraphNode = struct {
    id: []const u8,
    kind: []const u8,
    name: []const u8,
    labels: []const []const u8,
    props: Value,
    provenance: ?Provenance,
};

pub const GraphEdge = struct {
    from: []const u8, // source node id
    to: []const u8, // target node id
    label: []const u8,
    props: Value,
};

/// Stable, path-derived node id: `<filename>#<join(chain, "/")>`.
/// Caller owns the returned bytes (freed with the same allocator / arena).
pub fn nodeId(alloc: std.mem.Allocator, filename: []const u8, chain: []const []const u8) ![]u8 {
    const joined = try std.mem.join(alloc, "/", chain);
    defer alloc.free(joined);
    return std.fmt.allocPrint(alloc, "{s}#{s}", .{ filename, joined });
}

pub const Graph = struct {
    alloc: std.mem.Allocator,
    source_file: []const u8,
    nodes: std.StringArrayHashMapUnmanaged(GraphNode),
    edges: std.ArrayList(GraphEdge),

    pub fn init(alloc: std.mem.Allocator, source_file: []const u8) Graph {
        return .{
            .alloc = alloc,
            .source_file = source_file,
            .nodes = .empty,
            .edges = .empty,
        };
    }

    pub fn deinit(self: *Graph) void {
        self.nodes.deinit(self.alloc);
        self.edges.deinit(self.alloc);
    }

    /// Insert a node unless its id already exists; returns a pointer to the
    /// stored node (the existing one on a duplicate id, matching graph.py).
    pub fn addNode(self: *Graph, node: GraphNode) !*GraphNode {
        const gop = try self.nodes.getOrPut(self.alloc, node.id);
        if (!gop.found_existing) gop.value_ptr.* = node;
        return gop.value_ptr;
    }

    pub fn getNode(self: *Graph, id: []const u8) ?*GraphNode {
        return self.nodes.getPtr(id);
    }

    pub fn hasNode(self: *Graph, id: []const u8) bool {
        return self.nodes.contains(id);
    }

    /// One `external` stub node per distinct head path (kind "external").
    pub fn ensureExternal(self: *Graph, head_path: []const u8) !*GraphNode {
        const id = try std.fmt.allocPrint(self.alloc, "external:{s}", .{head_path});
        if (self.nodes.getPtr(id)) |existing| return existing;
        const labels = try self.alloc.dupe([]const u8, &.{"external"});
        const fields = try self.alloc.dupe(Value.Field, &.{
            .{ .key = "external", .value = .{ .bool = true } },
        });
        return self.addNode(.{
            .id = id,
            .kind = "external",
            .name = head_path,
            .labels = labels,
            .props = .{ .object = fields },
            .provenance = null,
        });
    }

    pub fn addEdge(self: *Graph, edge: GraphEdge) !void {
        try self.edges.append(self.alloc, edge);
    }

    /// Nodes sorted by id. Returns an owned slice (freed with `self.alloc`).
    pub fn nodesSorted(self: *Graph) ![]GraphNode {
        const out = try self.alloc.dupe(GraphNode, self.nodes.values());
        std.mem.sort(GraphNode, out, {}, lessNodeById);
        return out;
    }

    /// Edges in canonical order: (from, label, to). The props tiebreak (a
    /// stable canonical-JSON key) is added in Task 0.4 when `json_canon`
    /// provides `stablePropsKey`.
    pub fn edgesSorted(self: *Graph) ![]GraphEdge {
        const out = try self.alloc.dupe(GraphEdge, self.edges.items);
        std.mem.sort(GraphEdge, out, {}, lessEdgeCanonical);
        return out;
    }
};

fn lessNodeById(_: void, a: GraphNode, b: GraphNode) bool {
    return std.mem.lessThan(u8, a.id, b.id);
}

fn lessEdgeCanonical(_: void, a: GraphEdge, b: GraphEdge) bool {
    if (!std.mem.eql(u8, a.from, b.from)) return std.mem.lessThan(u8, a.from, b.from);
    if (!std.mem.eql(u8, a.label, b.label)) return std.mem.lessThan(u8, a.label, b.label);
    return std.mem.lessThan(u8, a.to, b.to);
}

// --------------------------------------------------------------------------- //
// tests
// --------------------------------------------------------------------------- //

test "node_id derivation matches python format" {
    const a = std.testing.allocator;
    const id = try nodeId(a, "operator-field.vaked", &.{"operator-field"});
    defer a.free(id);
    try std.testing.expectEqualStrings("operator-field.vaked#operator-field", id);

    const id2 = try nodeId(a, "f.vaked", &.{ "outer", "inner" });
    defer a.free(id2);
    try std.testing.expectEqualStrings("f.vaked#outer/inner", id2);
}

test "ensure_external is idempotent per head path and sets kind/labels/props" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var g = Graph.init(arena.allocator(), "f.vaked");
    defer g.deinit();

    const n1 = try g.ensureExternal("agentGuardd.ringbuf");
    const n2 = try g.ensureExternal("agentGuardd.ringbuf");
    try std.testing.expectEqual(n1, n2); // same stored node, not a duplicate
    try std.testing.expectEqual(@as(usize, 1), g.nodes.count());
    try std.testing.expectEqualStrings("external:agentGuardd.ringbuf", n1.id);
    try std.testing.expectEqualStrings("external", n1.kind);
    try std.testing.expectEqualStrings("agentGuardd.ringbuf", n1.name);
    try std.testing.expectEqual(@as(usize, 1), n1.labels.len);
    try std.testing.expectEqualStrings("external", n1.labels[0]);
}

test "edges_sorted orders by (from,label,to)" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var g = Graph.init(arena.allocator(), "f.vaked");
    defer g.deinit();

    try g.addEdge(.{ .from = "b", .to = "z", .label = "uses", .props = .null });
    try g.addEdge(.{ .from = "a", .to = "y", .label = "wraps", .props = .null });
    try g.addEdge(.{ .from = "a", .to = "x", .label = "wraps", .props = .null });
    try g.addEdge(.{ .from = "a", .to = "y", .label = "binds", .props = .null });

    const sorted = try g.edgesSorted();
    // expected order: (a,binds,y) (a,wraps,x) (a,wraps,y) (b,uses,z)
    try std.testing.expectEqualStrings("a", sorted[0].from);
    try std.testing.expectEqualStrings("binds", sorted[0].label);
    try std.testing.expectEqualStrings("a", sorted[1].from);
    try std.testing.expectEqualStrings("wraps", sorted[1].label);
    try std.testing.expectEqualStrings("x", sorted[1].to);
    try std.testing.expectEqualStrings("a", sorted[2].from);
    try std.testing.expectEqualStrings("wraps", sorted[2].label);
    try std.testing.expectEqualStrings("y", sorted[2].to);
    try std.testing.expectEqualStrings("b", sorted[3].from);
}
