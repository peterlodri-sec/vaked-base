const std = @import("std");
const core = @import("gocc-core");
const grammar = @import("parser/grammar.zig");
const scheduler = @import("dispatch/scheduler.zig");

pub fn main(init: std.process.Init.Minimal) !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    const args = try init.args.toSlice(alloc);

    if (args.len >= 2 and std.mem.eql(u8, args[1], "run")) {
        if (args.len < 3) {
            std.debug.print("Usage: gocc run <workflow-file>\n", .{});
            return error.MissingArg;
        }
        try runWorkflow(alloc, args[2]);
        return;
    }

    if (args.len >= 2 and std.mem.eql(u8, args[1], "verify")) {
        try runVerify(args);
        return;
    }

    std.debug.print("gocc v0.1.0 — Graph Orchestrated Code Command\n", .{});
    std.debug.print("Usage: gocc <run|build|bench|verify> [options]\n", .{});
}

fn runWorkflow(alloc: std.mem.Allocator, path: []const u8) !void {
    const io = std.Io.Threaded.global_single_threaded.io();
    const src = try std.Io.Dir.cwd().readFileAlloc(io, path, alloc, .limited(1024 * 1024));

    var graph = try grammar.parse(alloc, src);
    defer graph.deinit();

    var sched = try scheduler.computeWaves(alloc, &graph);
    defer sched.deinit();

    std.debug.print("[gocc/ARP v2.0-alpha]\n", .{});
    std.debug.print("GRAPH_PARSED: {s} -> [NODES: {d}, EDGES: {d}]\n", .{
        path, graph.nodes.count(), graph.edges.items.len,
    });
    for (sched.waves, 0..) |wave, i| {
        std.debug.print("Wave {d}: {d} node(s)\n", .{ i, wave.nodes.len });
        for (wave.nodes) |node_id| {
            std.debug.print("  - {s}\n", .{node_id});
        }
    }
}

fn runVerify(args: []const [:0]const u8) !void {
    const env_check = args.len < 3 or std.mem.eql(u8, args[2], "--env");
    if (!env_check) {
        std.debug.print("Unknown verify option: {s}\n", .{args[2]});
        return;
    }

    std.debug.print("[gocc verify --env]\n", .{});
    // Phase 7 TODO: check /proc/config.gz for CONFIG_BPF_LSM=y (Linux only; skip on macOS)
    // Phase 7 TODO: check /sys/kernel/security/lsm contains "bpf" (Linux only; skip on macOS)
    std.debug.print("eBPF preflight: not yet implemented (Phase 7)\n", .{});
}
