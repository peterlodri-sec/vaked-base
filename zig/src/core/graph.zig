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
    /// Lazy adjacency index `source_id -> [edges]`, built once on first
    /// `edgesFrom` and invalidated on `addEdge`. Turns per-parent child lookups
    /// from O(E) full-scans into O(1) (mirrors `graph.py:edges_from`).
    adj: ?std.StringArrayHashMapUnmanaged(std.ArrayList(GraphEdge)) = null,

    pub fn init(alloc: std.mem.Allocator, source_file: []const u8) Graph {
        return .{
            .alloc = alloc,
            .source_file = source_file,
            .nodes = .empty,
            .edges = .empty,
            .adj = null,
        };
    }

    pub fn deinit(self: *Graph) void {
        self.nodes.deinit(self.alloc);
        self.edges.deinit(self.alloc);
        if (self.adj) |*adj| {
            for (adj.values()) |*bucket| bucket.deinit(self.alloc);
            adj.deinit(self.alloc);
        }
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
        // Invalidate the lazy adjacency index (mirrors graph.py: `self._adj = None`).
        if (self.adj) |*adj| {
            for (adj.values()) |*bucket| bucket.deinit(self.alloc);
            adj.deinit(self.alloc);
            self.adj = null;
        }
    }

    /// All edges whose `from` is `source_id`, in insertion (source) order.
    ///
    /// Backed by a memoized adjacency index built once in O(E) on first call;
    /// each lookup is then O(1). Mirrors `graph.py:edges_from` — turning
    /// per-parent child traversal from O(N*E) into O(N+E). Insertion order is
    /// preserved, so callers see edges in the same order a full scan produced
    /// (output bytes unchanged). The returned slice is shared, not copied —
    /// callers must not mutate it.
    pub fn edgesFrom(self: *Graph, source_id: []const u8) ![]const GraphEdge {
        if (self.adj == null) {
            var idx: std.StringArrayHashMapUnmanaged(std.ArrayList(GraphEdge)) = .empty;
            for (self.edges.items) |e| {
                const gop = try idx.getOrPut(self.alloc, e.from);
                if (!gop.found_existing) gop.value_ptr.* = .empty;
                try gop.value_ptr.append(self.alloc, e);
            }
            self.adj = idx;
        }
        if (self.adj.?.getPtr(source_id)) |bucket| return bucket.items;
        return &.{};
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

test "edges_from returns source edges in insertion order, lazily rebuilt on add" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    var g = Graph.init(arena.allocator(), "f.vaked");
    defer g.deinit();

    try g.addEdge(.{ .from = "p", .to = "c1", .label = "contains", .props = .null });
    try g.addEdge(.{ .from = "q", .to = "x", .label = "uses", .props = .null });
    try g.addEdge(.{ .from = "p", .to = "c2", .label = "contains", .props = .null });

    // First lookup builds the index; order is insertion order (= source order).
    const from_p = try g.edgesFrom("p");
    try std.testing.expectEqual(@as(usize, 2), from_p.len);
    try std.testing.expectEqualStrings("c1", from_p[0].to);
    try std.testing.expectEqualStrings("c2", from_p[1].to);

    // Unknown source returns empty.
    try std.testing.expectEqual(@as(usize, 0), (try g.edgesFrom("nope")).len);

    // Adding an edge invalidates the index; the new edge appears at the tail.
    try g.addEdge(.{ .from = "p", .to = "c3", .label = "contains", .props = .null });
    const from_p2 = try g.edgesFrom("p");
    try std.testing.expectEqual(@as(usize, 3), from_p2.len);
    try std.testing.expectEqualStrings("c3", from_p2[2].to);
}
