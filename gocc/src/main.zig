const std = @import("std");
const core = @import("gocc-core");

pub fn main(init: std.process.Init.Minimal) !void {
    _ = core;

    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    const args = try init.args.toSlice(alloc);

    if (args.len >= 2 and std.mem.eql(u8, args[1], "verify")) {
        try runVerify(args);
        return;
    }

    std.debug.print("gocc v0.1.0 — Graph Orchestrated Code Command\n", .{});
    std.debug.print("Usage: gocc <run|build|bench|verify> [options]\n", .{});
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
