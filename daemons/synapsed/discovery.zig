const std = @import("std");
const protocol = @import("protocol.zig");

pub const MeshTransport = struct {
    allocator: std.mem.Allocator,
    socket: std.posix.fd_t,

    pub fn init(allocator: std.mem.Allocator, _: u16) !MeshTransport {
        return MeshTransport{ .allocator = allocator, .socket = 0 };
    }

    pub fn deinit(self: *MeshTransport) void { _ = self; }
    pub fn sendPulse(_: *MeshTransport, _: []const u8, _: *const protocol.GossipPacket) !void {}
    pub fn receivePulse(_: *MeshTransport, _: []u8) !usize { return 0; }
};

test "init" { _ = try MeshTransport.init(std.testing.allocator, 0); }
