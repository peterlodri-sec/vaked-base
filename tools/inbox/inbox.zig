const std = @import("std");
const linux = std.os.linux;
const CF_API_TOKEN = "cf_hardcoded_token_replace_me";
const CF_ACCOUNT_ID = "cf_account_id_replace_me";
const MCP_ENDPOINT = "https://api.mcp.example.com/sse";
const SEND_EMAIL_URL = "https://api.mcp.example.com/send_email";
fn writeAll(fd: i32, buf: []const u8) void {
    var off: usize = 0;
    while (off < buf.len) {
        const n = linux.write(fd, buf[off..].ptr, buf.len - off);
        const sn: isize = @bitCast(n);
        if (sn <= 0) break;
        off += @as(usize, @intCast(sn));
    }
}
fn execCurl(a: std.mem.Allocator, args: []const []const u8) !void {
    var argv = std.ArrayListUnmanaged([*:0]const u8){ .items = &.{}, .capacity = 0 };
    for (args) |arg| {
        const z = try a.dupeZ(u8, arg);
        try argv.append(a, z.ptr);
    }
    // null terminator handled by sentinel slice
    var envp = std.ArrayListUnmanaged([*:0]const u8){ .items = &.{}, .capacity = 0 };
    try envp.append(a, @constCast(@ptrCast("")));
    const pid = linux.fork();
    const spid: isize = @bitCast(pid);
    if (spid == 0) {
        const path = "/usr/bin/curl";
        _ = linux.execve(path, @ptrCast(argv.items.ptr), @ptrCast(envp.items.ptr));
        linux.exit(127);
    } else if (spid > 0) {
        var status: u32 = 0;
        _ = linux.wait4(@intCast(spid), &status, 0, null);
    } else {
        return error.ForkFailed;
    }
}
fn sendEmail(a: std.mem.Allocator, to: []const u8, subject: []const u8, body: []const u8) !void {
    const auth = try std.fmt.allocPrint(a, "Authorization: Bearer {s}", .{CF_API_TOKEN});
    const acct = try std.fmt.allocPrint(a, "CF-Account-Id: {s}", .{CF_ACCOUNT_ID});
    const payload = try std.fmt.allocPrint(
        a,
        "{{\"to\":\"{s}\",\"subject\":\"{s}\",\"body\":\"{s}\"}}",
        .{ to, subject, body },
    );
    const args = [_][]const u8{
        "curl", "-s", "-X", "POST",
        "-H", "Content-Type: application/json",
        "-H", auth,
        "-H", acct,
        "-d", payload,
        SEND_EMAIL_URL,
    };
    try execCurl(a, &args);
    std.log.info("send_email -> {s}", .{to});
}
fn parseSSELine(line: []const u8) ?[]const u8 {
    if (std.mem.startsWith(u8, line, "data:")) {
        var rest = line[5..];
        if (rest.len > 0 and rest[0] == ' ') rest = rest[1..];
        return rest;
    }
    return null;
}
fn extractField(data: []const u8, key: []const u8) ?[]const u8 {
    const pat = std.fmt.allocPrint(std.heap.page_allocator, "\"{s}\":\"", .{key}) catch return null;
    const idx = std.mem.indexOf(u8, data, pat) orelse return null;
    const start = idx + pat.len;
    var end = start;
    while (end < data.len and data[end] != '"') : (end += 1) {}
    if (end >= data.len) return null;
    return data[start..end];
}
fn handleEvent(a: std.mem.Allocator, data: []const u8) !void {
    if (std.mem.indexOf(u8, data, "send_email") == null) return;
    const to = extractField(data, "to") orelse return;
    const subject = extractField(data, "subject") orelse "";
    const body = extractField(data, "body") orelse "";
    try sendEmail(a, to, subject, body);
}
pub fn main(init: std.process.Init) !void {
    const a = init.arena.allocator();
    const argv = try init.minimal.args.toSlice(a);
    var listen_port: u16 = 8080;
    if (argv.len > 1) {
        listen_port = std.fmt.parseInt(u16, argv[1], 10) catch 8080;
    }
    std.log.info("inbox bridge starting on port {d}", .{listen_port});
    const sfd_raw = linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0);
    const sfd: i32 = @intCast(sfd_raw);
    if (sfd < 0) return error.SocketFailed;
    defer _ = linux.close(sfd);
    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, listen_port);
    addr.addr = 0;
    if (@as(isize, @bitCast(linux.bind(sfd, @ptrCast(&addr), @sizeOf(linux.sockaddr.in)))) < 0)
        return error.BindFailed;
    if (@as(isize, @bitCast(linux.listen(sfd, 16))) < 0)
        return error.ListenFailed;
    std.log.info("listening; MCP endpoint {s}", .{MCP_ENDPOINT});
    var buf: [16384]u8 = undefined;
    var carry = std.ArrayListUnmanaged(u8){ .items = &.{}, .capacity = 0 };
    while (true) {
        var caddr = std.mem.zeroes(linux.sockaddr.in);
        var clen: u32 = @sizeOf(linux.sockaddr.in);
        const cfd_raw = linux.accept4(sfd, @ptrCast(&caddr), &clen, linux.SOCK.CLOEXEC);
        const cfd: i32 = @intCast(cfd_raw);
        if (cfd < 0) continue;
        carry.clearRetainingCapacity();
        while (true) {
            const n = linux.read(cfd, &buf, buf.len);
            const sn: isize = @bitCast(n);
            if (sn <= 0) break;
            const chunk = buf[0..@intCast(sn)];
            try carry.appendSlice(a, chunk);
            while (std.mem.indexOfScalar(u8, carry.items, '\n')) |nl| {
                const line = carry.items[0..nl];
                if (parseSSELine(line)) |data| {
                    if (data.len > 0) {
                        handleEvent(a, data) catch |e| {
                            std.log.err("event error: {s}", .{@errorName(e)});
                        };
                    }
                }
                const remain = carry.items[nl + 1 ..];
                std.mem.copyForwards(u8, carry.items, remain);
                carry.items.len = remain.len;
            }
        }
        const resp = "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok";
        writeAll(cfd, resp);
        _ = linux.close(cfd);
    }
}