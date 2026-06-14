const std = @import("std");
const builtin = @import("builtin");

pub const DragonflyError = error{
    ConnectionFailed,
    CommandFailed,
    ParseError,
    NotConnected,
};

/// RESP2 client for DragonflyDB (Redis-compatible).
/// Connects to localhost:6379 by default.
pub const DragonflyClient = struct {
    alloc: std.mem.Allocator,
    host: []const u8,
    port: u16,
    /// Raw socket fd; -1 when not connected.
    fd: i32 = -1,

    pub fn init(alloc: std.mem.Allocator, host: []const u8, port: u16) DragonflyClient {
        return .{ .alloc = alloc, .host = host, .port = port };
    }

    pub fn connect(self: *DragonflyClient) DragonflyError!void {
        // TODO(phase6-real): std.net.tcpConnectToHost(self.alloc, self.host, self.port)
        // Stub: mark as not connected, log
        std.log.info("gocc DragonflyDB: connect stub ({s}:{})", .{ self.host, self.port });
        return DragonflyError.ConnectionFailed;
    }

    pub fn deinit(self: *DragonflyClient) void {
        if (self.fd >= 0) {
            if (builtin.os.tag == .linux) {
                _ = std.os.linux.close(@intCast(self.fd));
            } else {
                _ = std.c.close(self.fd);
            }
        }
        self.fd = -1;
    }

    /// HSET key field value
    pub fn hset(self: *DragonflyClient, key: []const u8, field: []const u8, value: []const u8) DragonflyError!void {
        _ = self;
        _ = key;
        _ = field;
        _ = value;
        return DragonflyError.NotConnected;
    }

    /// PUBLISH channel message
    pub fn publish(self: *DragonflyClient, channel: []const u8, message: []const u8) DragonflyError!void {
        _ = self;
        _ = channel;
        _ = message;
        return DragonflyError.NotConnected;
    }

    /// SET key value
    pub fn set(self: *DragonflyClient, key: []const u8, value: []const u8) DragonflyError!void {
        _ = self;
        _ = key;
        _ = value;
        return DragonflyError.NotConnected;
    }
};

/// Encode a RESP2 bulk string array command.
/// Caller owns returned slice.
pub fn encodeCommand(alloc: std.mem.Allocator, args: []const []const u8) ![]u8 {
    // Zig 0.16: use ArrayListUnmanaged with .print(alloc, ...) — managed ArrayList.init removed.
    var buf: std.ArrayListUnmanaged(u8) = .empty;
    defer buf.deinit(alloc);
    try buf.print(alloc, "*{d}\r\n", .{args.len});
    for (args) |arg| {
        try buf.print(alloc, "${d}\r\n{s}\r\n", .{ arg.len, arg });
    }
    return buf.toOwnedSlice(alloc);
}

// ---- Tests ------------------------------------------------------------------

test "encodeCommand: SET foo bar produces correct RESP2 bytes" {
    const alloc = std.testing.allocator;
    const args = [_][]const u8{ "SET", "foo", "bar" };
    const encoded = try encodeCommand(alloc, &args);
    defer alloc.free(encoded);
    const expected = "*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n";
    try std.testing.expectEqualSlices(u8, expected, encoded);
}

test "encodeCommand: HSET gocc:agent:1 status running (4-arg)" {
    const alloc = std.testing.allocator;
    const args = [_][]const u8{ "HSET", "gocc:agent:1", "status", "running" };
    const encoded = try encodeCommand(alloc, &args);
    defer alloc.free(encoded);
    const expected = "*4\r\n$4\r\nHSET\r\n$12\r\ngocc:agent:1\r\n$6\r\nstatus\r\n$7\r\nrunning\r\n";
    try std.testing.expectEqualSlices(u8, expected, encoded);
}

test "DragonflyClient.connect stub returns ConnectionFailed" {
    var client = DragonflyClient.init(std.testing.allocator, "localhost", 6379);
    defer client.deinit();
    const result = client.connect();
    try std.testing.expectError(DragonflyError.ConnectionFailed, result);
}

test "DragonflyClient.deinit on unconnected client does not panic" {
    var client = DragonflyClient.init(std.testing.allocator, "localhost", 6379);
    client.deinit(); // fd is -1 — must not crash
}
