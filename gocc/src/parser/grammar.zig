const types = @import("../arp/types.zig");

pub const ParseError = error{ UnexpectedToken, OutOfMemory };

pub fn parse(alloc: @import("std").mem.Allocator, src: []const u8) ParseError!types.ArpGraph {
    _ = src;
    return types.ArpGraph.init(alloc);
}
