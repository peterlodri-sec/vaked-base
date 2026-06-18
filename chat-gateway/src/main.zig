const std = @import("std");
const linux = std.os.linux;
const auth = @import("auth.zig");

const GENESIS = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf";
const SALT = "vaked-chat-gateway-salt-2026";

pub fn main(init: std.process.Init) !void {
    const a = init.arena.allocator();
    _ = a;

    const fd = linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0);
    const s: i32 = @intCast(fd);
    defer _ = linux.close(s);

    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, 9090);
    _ = linux.bind(s, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));
    _ = linux.listen(s, 8);

    std.log.info("Chat Gateway :9090 · seal 7c242080", .{});
    while (true) {
        var buf: [4096]u8 = undefined;
        const n = linux.read(s, &buf, buf.len);
        if (n <= 0) continue;
        const req = buf[0..@intCast(n)];

        // Parse Bearer token from Authorization header  
        var authed = false;
        if (std.mem.indexOf(u8, req, "Bearer ")) |idx| {
            const start = idx + 7;
            const end = std.mem.indexOfScalar(u8, req[start..], '\n') orelse (req.len - start);
            const end2 = std.mem.indexOfScalar(u8, req[start..], '\r') orelse end;
            const token_end = @min(end, end2);
            authed = auth.verify(req[start .. start + token_end], SALT);
        }

        const resp = if (authed)
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\",\"genesis\":\"7c242080\"}\n"
        else
            "HTTP/1.1 403 Forbidden\r\n\r\nCOMPLIANCE_VIOLATION\n";
        _ = linux.write(s, resp.ptr, resp.len);
    }
}
