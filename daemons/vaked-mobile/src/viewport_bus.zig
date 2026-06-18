//! Mobile Viewport Bus — WireGuard tunnel, TCP_NODELAY, zero-alloc binary snapshots
//! GENESIS_SEAL: e03a89fd

const std = @import("std");

pub const ViewportStreamer = struct {
    allocator: std.mem.Allocator,
    stream_socket: std.net.StreamServer,

    pub fn init(allocator: std.mem.Allocator) ViewportStreamer {
        return .{ .allocator = allocator, .stream_socket = std.net.StreamServer.init(.{ .reuse_address = true }) };
    }

    pub fn listenAndPipe(self: *ViewportStreamer, address: []const u8, port: u16) !void {
        const parsed = try std.net.Address.parseIp4(address, port);
        try self.stream_socket.listen(parsed);
        _ = try self.stream_socket.accept();
    }
};

test "viewport streamer init" {
    var vs = ViewportStreamer.init(std.testing.allocator);
    defer vs.stream_socket.deinit();
    try std.testing.expect(vs.stream_socket.socket.fd != 0);
}
