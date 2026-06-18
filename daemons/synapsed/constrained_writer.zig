const std = @import("std");
pub const ConstrainedWriter = struct {
    pub fn writeBufferDirectlyToWire(stream: std.net.Stream, data: []const u8) !void {
        if (data.len > 65535) return error.FramePayloadTooLarge;
        var off: usize = 0;
        while (off < data.len) { const w = try stream.write(data[off..]); if (w == 0) return error.SocketWriteInterrupted; off += w; }
    }
};
test "write ok" { _ = ConstrainedWriter; }
