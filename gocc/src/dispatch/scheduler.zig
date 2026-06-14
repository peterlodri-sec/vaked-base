const std = @import("std");
const types = @import("../arp/types.zig");

pub fn wavefrontWaves(alloc: std.mem.Allocator, graph: *const types.ArpGraph) ![][]const u8 {
    _ = graph;
    return alloc.alloc([]const u8, 0);
}
