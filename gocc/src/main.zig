const std = @import("std");
const core = @import("gocc-core");

pub fn main() void {
    _ = core;
    std.debug.print("gocc v0.1.0 — Graph Orchestrated Code Command\n", .{});
    std.debug.print("Usage: gocc <run|build|bench|verify> [options]\n", .{});
}
