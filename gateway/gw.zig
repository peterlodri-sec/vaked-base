// gw.zig — Vaked Constellation Gateway (Zig-native, Linux sockets)
// Replaces gateway/gw.py. Zig 0.16+. Linux raw syscalls.
// Build: zig build-exe gw.zig -O ReleaseFast -fstrip
//
// Genesis Seal: 7c242080

const std = @import("std");
const linux = std.os.linux;

const port: u16 = 8081;

const Route = struct {
    path: []const u8,
    content_type: []const u8,
    file_path: ?[]const u8,
    inline_content: ?[]const u8,
};

const routes = [_]Route{
    .{ .path = "/", .content_type = "text/html", .file_path = "/var/www/constellation/index.html", .inline_content = null },
    .{ .path = "/health", .content_type = "text/plain", .file_path = null, .inline_content = "ok" },
    .{ .path = "/wisdom", .content_type = "text/html", .file_path = "/var/www/library/wisdom.html", .inline_content = null },
    .{ .path = "/registry", .content_type = "text/html", .file_path = "/var/www/library/registry.html", .inline_content = null },
    .{ .path = "/swarm-monologue", .content_type = "text/html", .file_path = "/var/www/monologue/index.html", .inline_content = null },
    .{ .path = "/status", .content_type = "text/html", .file_path = "/var/www/status/index.html", .inline_content = null },
    .{ .path = "/monitor", .content_type = "text/html", .file_path = "/var/www/monitor/index.html", .inline_content = null },
    .{ .path = "/reflect", .content_type = "text/html", .file_path = "/var/www/reflect/index.html", .inline_content = null },
    .{ .path = "/dogfeed", .content_type = "text/html", .file_path = "/var/www/dogfeed/index.html", .inline_content = null },
    .{ .path = "/bus", .content_type = "text/html", .file_path = "/var/www/bus/index.html", .inline_content = null },
    .{ .path = "/radio", .content_type = "text/html", .file_path = "/var/www/radio/index.html", .inline_content = null },
    .{ .path = "/nav", .content_type = "text/html", .file_path = "/var/www/nav/index.html", .inline_content = null },
    .{ .path = "/chat", .content_type = "text/html", .file_path = "/var/www/chat/index.html", .inline_content = null },
    .{ .path = "/donate", .content_type = "text/html", .file_path = "/var/www/donate/index.html", .inline_content = null },
    .{ .path = "/rss", .content_type = "text/html", .file_path = "/var/www/rss/index.html", .inline_content = null },
    .{ .path = "/rss.xml", .content_type = "application/xml", .file_path = "/var/www/rss/index.xml", .inline_content = null },
};

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const a = arena.allocator();

    // Socket
    const sockfd_usize = linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0);
    const sockfd: i32 = @intCast(sockfd_usize);
    defer _ = linux.close(sockfd);

    // Reuse addr
    const one: i32 = 1;
    _ = linux.setsockopt(sockfd, linux.SOL.SOCKET, linux.SO.REUSEADDR, @ptrCast(&one), @sizeOf(i32));

    // Bind
    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, port);
    addr.addr = 0; // INADDR_ANY
    _ = linux.bind(sockfd, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));

    // Listen
    _ = linux.listen(sockfd, 128);

    std.log.info("Vaked Gateway v0.2 (Zig) — :{d}", .{port});
    std.log.info("Genesis seal: 7c242080", .{});

    while (true) {
        var client_addr: linux.sockaddr.in = undefined;
        var addr_len: u32 = @sizeOf(linux.sockaddr.in);
        const cfd_usize = linux.accept4(sockfd, @ptrCast(&client_addr), &addr_len, linux.SOCK.CLOEXEC);
        const clientfd: i32 = @intCast(cfd_usize);
        defer _ = linux.close(clientfd);

        // Read request
        var buf: [4096]u8 = undefined;
        const n = linux.read(clientfd, &buf, buf.len);
        if (n <= 0) continue;
        const req = buf[0..@intCast(n)];
        const path = parsePath(req) orelse "/";
        const route = findRoute(path);

        if (route) |r| {
            if (r.inline_content) |content| {
                _ = writeResponse(clientfd, 200, r.content_type, content) catch continue;
                continue;
            }
            if (r.file_path) |fp| {
                const data = readFileAlloc(a, fp) catch {
                    _ = writeResponse(clientfd, 404, "text/plain", "not found") catch continue;
                    continue;
                };
                _ = writeResponse(clientfd, 200, r.content_type, data) catch continue;
                continue;
            }
        }

        if (std.mem.eql(u8, path, "/mesh.json")) {
            const json = "{\"t\":0,\"convergence_ms\":27.3,\"nodes\":6,\"peers\":5,\"trust_index\":1.0,\"status\":\"synced\"}";
            _ = writeResponse(clientfd, 200, "application/json", json) catch continue;
            continue;
        }

        _ = writeResponse(clientfd, 404, "text/plain", "route not found") catch continue;
    }
}

fn parsePath(req: []const u8) ?[]const u8 {
    var it = std.mem.splitScalar(u8, req, '\n');
    const first = it.first();
    var parts = std.mem.splitScalar(u8, first, ' ');
    _ = parts.first();
    return parts.next();
}

fn findRoute(path: []const u8) ?Route {
    for (routes) |r| {
        if (std.mem.eql(u8, r.path, path)) return r;
    }
    return null;
}

fn readFileAlloc(a: std.mem.Allocator, path: []const u8) ![]u8 {
    const path_c = try a.dupeZ(u8, path);
    defer a.free(path_c);
    const fd_raw = linux.open(path_c.ptr, @bitCast(@as(u32, 0)), 0);
    const fd: i32 = @intCast(fd_raw);
    if (fd < 0) return error.FileNotFound;
    defer _ = linux.close(fd);
    const MAX = 1 << 20; // 1MB max
    var buf = try a.alloc(u8, MAX);
    errdefer a.free(buf);
    const n = linux.read(fd, buf.ptr, MAX);
    if (n < 0) return error.ReadFailed;
    return buf[0..@intCast(n)];
}

fn writeResponse(fd: i32, code: u16, content_type: []const u8, body: []const u8) !void {
    var hdr: [512]u8 = undefined;
    const header = try std.fmt.bufPrint(&hdr,
        "HTTP/1.1 {d} OK\r\nContent-Type: {s}\r\nContent-Length: {d}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
        .{ code, content_type, body.len },
    );
    _ = linux.write(fd, header.ptr, header.len);
    _ = linux.write(fd, body.ptr, body.len);
}
