const std = @import("std");
const types = @import("gocc-core");

pub const Wave = struct {
    nodes: []const []const u8, // node IDs in this parallel wave
};

pub const Schedule = struct {
    waves: []Wave,
    alloc: std.mem.Allocator,

    pub fn deinit(self: *Schedule) void {
        for (self.waves) |wave| self.alloc.free(wave.nodes);
        self.alloc.free(self.waves);
    }
};

/// Topological sort → parallel wavefront waves via Kahn's algorithm.
/// Returns a Schedule where each Wave is a set of nodes that can execute
/// in parallel (all predecessors in prior waves).
/// Returns error.CycleDetected if the graph has a cycle.
pub fn computeWaves(alloc: std.mem.Allocator, graph: *const types.ArpGraph) !Schedule {
    const total = graph.nodes.count();

    // Build in-degree map and successor map using hash maps keyed by node ID.
    // std.StringHashMap stores the allocator internally (.init / .deinit).
    var in_degree = std.StringHashMap(usize).init(alloc);
    defer in_degree.deinit();

    // Successor lists: each value is an ArrayListUnmanaged of node IDs (Zig 0.16 style: no stored alloc).
    var successors = std.StringHashMap(std.ArrayListUnmanaged([]const u8)).init(alloc);
    defer {
        var it = successors.valueIterator();
        while (it.next()) |list| list.deinit(alloc);
        successors.deinit();
    }

    // Initialize every node with in-degree 0 and an empty successor list.
    var node_it = graph.nodes.iterator();
    while (node_it.next()) |entry| {
        try in_degree.put(entry.key_ptr.*, 0);
        try successors.put(entry.key_ptr.*, .empty);
    }

    // Populate from edges.
    for (graph.edges.items) |edge| {
        // Increment in-degree of 'to'.
        const deg = in_degree.getPtr(edge.to) orelse continue;
        deg.* += 1;

        // Append 'to' to successor list of 'from'.
        const succ_list = successors.getPtr(edge.from) orelse continue;
        try succ_list.append(alloc, edge.to);
    }

    // Collect the initial wave: all nodes with in-degree 0.
    var current_queue: std.ArrayListUnmanaged([]const u8) = .empty;
    defer current_queue.deinit(alloc);

    {
        var deg_it = in_degree.iterator();
        while (deg_it.next()) |entry| {
            if (entry.value_ptr.* == 0) {
                try current_queue.append(alloc, entry.key_ptr.*);
            }
        }
    }

    // Sort for determinism.
    std.sort.block([]const u8, current_queue.items, {}, lessThanStr);

    var waves_list: std.ArrayListUnmanaged(Wave) = .empty;
    defer waves_list.deinit(alloc);
    errdefer for (waves_list.items) |w| alloc.free(w.nodes);

    var processed: usize = 0;

    while (current_queue.items.len > 0) {
        // Emit current wave — dupe the slice so the Wave owns it.
        const wave_nodes = try alloc.dupe([]const u8, current_queue.items);
        try waves_list.append(alloc, .{ .nodes = wave_nodes });

        var next_queue: std.ArrayListUnmanaged([]const u8) = .empty;
        defer next_queue.deinit(alloc);

        for (current_queue.items) |node_id| {
            processed += 1;
            const succ_list = successors.getPtr(node_id) orelse continue;
            for (succ_list.items) |succ| {
                const deg = in_degree.getPtr(succ) orelse continue;
                deg.* -= 1;
                if (deg.* == 0) {
                    try next_queue.append(alloc, succ);
                }
            }
        }

        // Sort next wave for determinism.
        std.sort.block([]const u8, next_queue.items, {}, lessThanStr);

        // Swap queues: clear current, copy next into it.
        current_queue.clearAndFree(alloc);
        try current_queue.appendSlice(alloc, next_queue.items);
    }

    if (processed != total) return error.CycleDetected;

    const waves_slice = try waves_list.toOwnedSlice(alloc);
    return Schedule{ .waves = waves_slice, .alloc = alloc };
}

fn lessThanStr(_: void, a: []const u8, b: []const u8) bool {
    return std.mem.lessThan(u8, a, b);
}

// ─── Tests ───────────────────────────────────────────────────────────────────

test "linear chain: a > b > c produces 3 waves" {
    const alloc = std.testing.allocator;

    var graph = types.ArpGraph.init(alloc);
    defer graph.deinit();

    try graph.addNode(.{ .id = "a", .kind = .pipeline_stage, .name = "a", .props = .empty });
    try graph.addNode(.{ .id = "b", .kind = .pipeline_stage, .name = "b", .props = .empty });
    try graph.addNode(.{ .id = "c", .kind = .pipeline_stage, .name = "c", .props = .empty });
    try graph.addEdge(.{ .from = "a", .to = "b", .label = "pipeline" });
    try graph.addEdge(.{ .from = "b", .to = "c", .label = "pipeline" });

    var sched = try computeWaves(alloc, &graph);
    defer sched.deinit();

    try std.testing.expectEqual(@as(usize, 3), sched.waves.len);
    try std.testing.expectEqual(@as(usize, 1), sched.waves[0].nodes.len);
    try std.testing.expectEqualStrings("a", sched.waves[0].nodes[0]);
    try std.testing.expectEqual(@as(usize, 1), sched.waves[1].nodes.len);
    try std.testing.expectEqualStrings("b", sched.waves[1].nodes[0]);
    try std.testing.expectEqual(@as(usize, 1), sched.waves[2].nodes.len);
    try std.testing.expectEqualStrings("c", sched.waves[2].nodes[0]);
}

test "diamond: a > b, a > c, b > d, c > d produces 3 waves" {
    const alloc = std.testing.allocator;

    var graph = types.ArpGraph.init(alloc);
    defer graph.deinit();

    try graph.addNode(.{ .id = "a", .kind = .pipeline_stage, .name = "a", .props = .empty });
    try graph.addNode(.{ .id = "b", .kind = .pipeline_stage, .name = "b", .props = .empty });
    try graph.addNode(.{ .id = "c", .kind = .pipeline_stage, .name = "c", .props = .empty });
    try graph.addNode(.{ .id = "d", .kind = .pipeline_stage, .name = "d", .props = .empty });
    try graph.addEdge(.{ .from = "a", .to = "b", .label = "pipeline" });
    try graph.addEdge(.{ .from = "a", .to = "c", .label = "pipeline" });
    try graph.addEdge(.{ .from = "b", .to = "d", .label = "pipeline" });
    try graph.addEdge(.{ .from = "c", .to = "d", .label = "pipeline" });

    var sched = try computeWaves(alloc, &graph);
    defer sched.deinit();

    try std.testing.expectEqual(@as(usize, 3), sched.waves.len);
    // Wave 0: [a]
    try std.testing.expectEqual(@as(usize, 1), sched.waves[0].nodes.len);
    try std.testing.expectEqualStrings("a", sched.waves[0].nodes[0]);
    // Wave 1: [b, c] — sorted
    try std.testing.expectEqual(@as(usize, 2), sched.waves[1].nodes.len);
    try std.testing.expectEqualStrings("b", sched.waves[1].nodes[0]);
    try std.testing.expectEqualStrings("c", sched.waves[1].nodes[1]);
    // Wave 2: [d]
    try std.testing.expectEqual(@as(usize, 1), sched.waves[2].nodes.len);
    try std.testing.expectEqualStrings("d", sched.waves[2].nodes[0]);
}

test "cycle detection: a -> b -> a returns CycleDetected" {
    const alloc = std.testing.allocator;

    var graph = types.ArpGraph.init(alloc);
    defer graph.deinit();

    try graph.addNode(.{ .id = "a", .kind = .pipeline_stage, .name = "a", .props = .empty });
    try graph.addNode(.{ .id = "b", .kind = .pipeline_stage, .name = "b", .props = .empty });
    try graph.addEdge(.{ .from = "a", .to = "b", .label = "pipeline" });
    try graph.addEdge(.{ .from = "b", .to = "a", .label = "pipeline" });

    const result = computeWaves(alloc, &graph);
    try std.testing.expectError(error.CycleDetected, result);
}
