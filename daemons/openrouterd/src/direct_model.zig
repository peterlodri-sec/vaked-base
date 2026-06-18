//! Direct model access — breach the cache layer.
//! Raw socket, zero intermediate buffer, no sliding-window.
//! Agent ↔ Model, direct. GENESIS_SEAL: 7c242080

const std = @import("std");
const net = std.net;

pub const DirectModelStream = struct {
    sock: net.Stream,
    buf: [65536]u8,

    pub fn connect(host: []const u8, port: u16) !DirectModelStream {
        const addr = try net.Address.parseIp4(host, port);
        const sock = try net.tcpConnectToAddress(addr);
        try std.os.setsockopt(sock.handle, std.os.IPPROTO.TCP, std.os.TCP.NODELAY, &std.mem.toBytes(@as(c_int, 1)));
        return DirectModelStream{ .sock = sock, .buf = undefined };
    }

    /// Write raw token bytes directly to model socket — no framing, no cache
    pub fn writeRaw(self: *DirectModelStream, data: []const u8) !void {
        var off: usize = 0;
        while (off < data.len) {
            const w = try self.sock.write(data[off..]);
            if (w == 0) return error.WriteFailed;
            off += w;
        }
    }

    /// Read raw token bytes directly from model socket — no buffering
    pub fn readRaw(self: *DirectModelStream) ![]const u8 {
        const n = try self.sock.read(&self.buf);
        if (n == 0) return error.Closed;
        return self.buf[0..n];
    }

    pub fn close(self: *DirectModelStream) void {
        self.sock.close();
    }
};

test "direct model stream compiles" {
    try std.testing.expect(@sizeOf(DirectModelStream) > 0);
}
