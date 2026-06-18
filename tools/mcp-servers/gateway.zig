const std = @import("std");
const linux = std.os.linux;
const PORT: u16 = 9099;
const AUTH_TOKEN = "secret-bearer-token";
const Tool = struct {
    name: []const u8,
    desc: []const u8,
    server: []const u8,
    cmd: []const []const u8,
    public: bool,
};
const tools = [_]Tool{
    // server "fs" - public
    .{ .name = "fs.list", .desc = "List files", .server = "fs", .cmd = &.{ "/bin/ls", "-1" }, .public = true },
    .{ .name = "fs.cat", .desc = "Read file", .server = "fs", .cmd = &.{ "/bin/cat", "/etc/hostname" }, .public = true },
    .{ .name = "fs.pwd", .desc = "Working dir", .server = "fs", .cmd = &.{"/bin/pwd"}, .public = true },
    // server "net" - public
    .{ .name = "net.ping", .desc = "Ping host", .server = "net", .cmd = &.{ "/bin/echo", "pong" }, .public = true },
    .{ .name = "net.hostname", .desc = "Get hostname", .server = "net", .cmd = &.{"/bin/hostname"}, .public = true },
    // server "info" - public
    .{ .name = "info.uname", .desc = "Kernel info", .server = "info", .cmd = &.{ "/bin/uname", "-a" }, .public = true },
    .{ .name = "info.date", .desc = "System date", .server = "info", .cmd = &.{"/bin/date"}, .public = true },
    // server "admin" - internal (auth)
    .{ .name = "admin.whoami", .desc = "Current user", .server = "admin", .cmd = &.{"/usr/bin/whoami"}, .public = false },
    .{ .name = "admin.id", .desc = "User id", .server = "admin", .cmd = &.{"/usr/bin/id"}, .public = false },
    .{ .name = "admin.env", .desc = "Environment", .server = "admin", .cmd = &.{"/usr/bin/env"}, .public = false },
    .{ .name = "admin.ps", .desc = "Process list", .server = "admin", .cmd = &.{ "/bin/ps", "aux" }, .public = false },
    .{ .name = "admin.netstat", .desc = "Net connections", .server = "admin", .cmd = &.{ "/bin/ss", "-tlnp" }, .public = false },
    .{ .name = "admin.mounts", .desc = "Mount points", .server = "admin", .cmd = &.{"/bin/mount"}, .public = false },
    .{ .name = "admin.kill", .desc = "Kill process", .server = "admin", .cmd = &.{ "/bin/echo", "killed" }, .public = false },
};
fn findTool(name: []const u8) ?*const Tool {
    for (&tools) |*t| {
        if (std.mem.eql(u8, t.name, name)) return t;
    }
    return null;
}
fn writeAll(fd: i32, buf: []const u8) void {
    var off: usize = 0;
    while (off < buf.len) {
        const n = linux.write(fd, buf[off..].ptr, buf.len - off);
        const sn: isize = @bitCast(n);
        if (sn <= 0) break;
        off += @as(usize, @intCast(sn));
    }
}
fn sendResponse(fd: i32, status: []const u8, body: []const u8, a: std.mem.Allocator) void {
    const hdr = std.fmt.allocPrint(a,
        "HTTP/1.1 {s}\r\nContent-Type: application/json\r\nContent-Length: {d}\r\nConnection: close\r\n\r\n",
        .{ status, body.len }) catch return;
    writeAll(fd, hdr);
    writeAll(fd, body);
}
// run subprocess via fork+execve, capture stdout via pipe
fn runSubprocess(t: *const Tool, a: std.mem.Allocator) []const u8 {
    var fds: [2]i32 = undefined;
    const pr = linux.pipe(&fds);
    if (pr != 0) return "pipe-failed";
    const pid = linux.fork();
    const spid: isize = @bitCast(pid);
    if (spid < 0) return "fork-failed";
    if (pid == 0) {
        // child
        _ = linux.close(fds[0]);
        _ = linux.dup2(fds[1], 1);
        _ = linux.dup2(fds[1], 2);
        _ = linux.close(fds[1]);
        const argvZ = a.allocSentinel(?[*:0]const u8, t.cmd.len, null) catch linux.exit(127);
        for (t.cmd, 0..) |arg, i| {
            const z = a.dupeZ(u8, arg) catch linux.exit(127);
            argvZ[i] = z.ptr;
        }
        const envp = a.allocSentinel(?[*:0]const u8, 0, null) catch linux.exit(127);
        const pathZ = a.dupeZ(u8, t.cmd[0]) catch linux.exit(127);
        _ = linux.execve(pathZ.ptr, @ptrCast(argvZ.ptr), @ptrCast(envp.ptr));
        linux.exit(127);
    }
    // parent
    _ = linux.close(fds[1]);
    var out: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    var buf: [4096]u8 = undefined;
    while (true) {
        const n = linux.read(fds[0], &buf, buf.len);
        const sn: isize = @bitCast(n);
        if (sn <= 0) break;
        out.appendSlice(a, buf[0..@intCast(sn)]) catch break;
    }
    _ = linux.close(fds[0]);
    var status: u32 = 0;
    _ = linux.wait4(@intCast(spid), &status, 0, null);
    return out.items;
}
fn jsonEscape(s: []const u8, a: std.mem.Allocator) []const u8 {
    var out: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    for (s) |c| {
        switch (c) {
            '"' => out.appendSlice(a, "\\\"") catch {},
            '\\' => out.appendSlice(a, "\\\\") catch {},
            '\n' => out.appendSlice(a, "\\n") catch {},
            '\r' => out.appendSlice(a, "\\r") catch {},
            '\t' => out.appendSlice(a, "\\t") catch {},
            else => out.append(a, c) catch {},
        }
    }
    return out.items;
}
fn buildToolList(a: std.mem.Allocator) []const u8 {
    var out: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    out.appendSlice(a, "{\"jsonrpc\":\"2.0\",\"result\":{\"tools\":[") catch {};
    for (&tools, 0..) |*t, i| {
        if (i != 0) out.appendSlice(a, ",") catch {};
        const piece = std.fmt.allocPrint(a,
            "{{\"name\":\"{s}\",\"description\":\"{s}\",\"server\":\"{s}\",\"auth\":{s}}}",
            .{ t.name, t.desc, t.server, if (t.public) "false" else "true" }) catch "";
        out.appendSlice(a, piece) catch {};
    }
    out.appendSlice(a, "]}}") catch {};
    return out.items;
}
fn extractField(body: []const u8, key: []const u8, a: std.mem.Allocator) ?[]const u8 {
    const pat = std.fmt.allocPrint(a, "\"{s}\"", .{key}) catch return null;
    const idx = std.mem.indexOf(u8, body, pat) orelse return null;
    var i = idx + pat.len;
    while (i < body.len and (body[i] == ' ' or body[i] == ':')) : (i += 1) {}
    if (i >= body.len or body[i] != '"') return null;
    i += 1;
    const start = i;
    while (i < body.len and body[i] != '"') : (i += 1) {}
    return body[start..i];
}
fn hasBearer(req: []const u8) bool {
    const idx = std.mem.indexOf(u8, req, "Authorization:") orelse return false;
    var line = req[idx..];
    const eol = std.mem.indexOfScalar(u8, line, '\r') orelse line.len;
    line = line[0..eol];
    const tok = std.fmt.comptimePrint("Authorization: Bearer {s}", .{AUTH_TOKEN});
    return std.mem.indexOf(u8, line, tok) != null;
}
fn handle(fd: i32, a: std.mem.Allocator) void {
    var buf: [16384]u8 = undefined;
    const n = linux.read(fd, &buf, buf.len);
    const sn: isize = @bitCast(n);
    if (sn <= 0) return;
    const req = buf[0..@intCast(sn)];
    // method + path
    const sp1 = std.mem.indexOfScalar(u8, req, ' ') orelse return;
    const rest = req[sp1 + 1 ..];
    const sp2 = std.mem.indexOfScalar(u8, rest, ' ') orelse return;
    const path = rest[0..sp2];
    if (std.mem.eql(u8, path, "/health")) {
        sendResponse(fd, "200 OK", "{\"status\":\"ok\",\"servers\":4,\"tools\":14}", a);
        return;
    }
    // body
    const body_off = std.mem.indexOf(u8, req, "\r\n\r\n");
    const body = if (body_off) |o| req[o + 4 ..] else "";
    if (!std.mem.eql(u8, path, "/mcp") and !std.mem.eql(u8, path, "/")) {
        sendResponse(fd, "404 Not Found", "{\"error\":\"not found\"}", a);
        return;
    }
    const method = extractField(body, "method", a) orelse "";
    if (std.mem.eql(u8, method, "tools/list")) {
        sendResponse(fd, "200 OK", buildToolList(a), a);
        return;
    }
    if (std.mem.eql(u8, method, "tools/call")) {
        const name = extractField(body, "name", a) orelse {
            sendResponse(fd, "400 Bad Request", "{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32602,\"message\":\"missing name\"}}", a);
            return;
        };
        const t = findTool(name) orelse {
            sendResponse(fd, "404 Not Found", "{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32601,\"message\":\"unknown tool\"}}", a);
            return;
        };
        if (!t.public and !hasBearer(req)) {
            sendResponse(fd, "401 Unauthorized", "{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32001,\"message\":\"unauthorized\"}}", a);
            return;
        }
        const result = runSubprocess(t, a);
        const esc = jsonEscape(result, a);
        const resp = std.fmt.allocPrint(a,
            "{{\"jsonrpc\":\"2.0\",\"result\":{{\"content\":[{{\"type\":\"text\",\"text\":\"{s}\"}}],\"tool\":\"{s}\"}}}}",
            .{ esc, t.name }) catch "{}";
        sendResponse(fd, "200 OK", resp, a);
        return;
    }
    sendResponse(fd, "400 Bad Request", "{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32600,\"message\":\"invalid request\"}}", a);
}
pub fn main(init: std.process.Init) !void {
    const a = init.arena.allocator();
    const sfd_u = linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0);
    const sfd: i32 = @intCast(sfd_u);
    const one: u32 = 1;
    _ = linux.setsockopt(sfd, linux.SOL.SOCKET, linux.SO.REUSEADDR, std.mem.asBytes(&one), @sizeOf(u32));
    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, PORT);
    addr.addr = 0;
    _ = linux.bind(sfd, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));
    _ = linux.listen(sfd, 128);
    std.log.info("MCP HTTP server listening on :{d} (4 servers, 14 tools)", .{PORT});
    while (true) {
        var caddr = std.mem.zeroes(linux.sockaddr.in);
        var clen: u32 = @sizeOf(linux.sockaddr.in);
        const cfd_u = linux.accept4(sfd, @ptrCast(&caddr), &clen, linux.SOCK.CLOEXEC);
        const cfd_s: isize = @bitCast(cfd_u);
        if (cfd_s < 0) continue;
        const cfd: i32 = @intCast(cfd_s);
        handle(cfd, a);
        _ = linux.close(cfd);
    }
}