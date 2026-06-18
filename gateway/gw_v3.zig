const std = @import("std");
const linux = std.os.linux;

const Route = struct {
    path: []const u8,
    content_type: []const u8,
    file_path: ?[]const u8,
    inline_content: ?[]const u8,
};

const routes = [_]Route{
    .{ .path = "/",                 .content_type = "text/html",        .file_path = "/var/www/constellation/index.html", .inline_content = null },
    .{ .path = "/health",           .content_type = "text/plain",       .file_path = null, .inline_content = "ok" },
    .{ .path = "/wisdom",           .content_type = "text/html",        .file_path = "/var/www/library/wisdom.html", .inline_content = null },
    .{ .path = "/registry",         .content_type = "text/html",        .file_path = "/var/www/library/registry.html", .inline_content = null },
    .{ .path = "/swarm-monologue",  .content_type = "text/html",        .file_path = "/var/www/monologue/index.html", .inline_content = null },
    .{ .path = "/status",           .content_type = "text/html",        .file_path = "/var/www/status/index.html", .inline_content = null },
    .{ .path = "/monitor",          .content_type = "text/html",        .file_path = "/var/www/monitor/index.html", .inline_content = null },
    .{ .path = "/reflect",          .content_type = "text/html",        .file_path = "/var/www/reflect/index.html", .inline_content = null },
    .{ .path = "/dogfeed",          .content_type = "text/html",        .file_path = "/var/www/dogfeed/index.html", .inline_content = null },
    .{ .path = "/bus",              .content_type = "text/html",        .file_path = "/var/www/bus/index.html", .inline_content = null },
    .{ .path = "/radio",            .content_type = "text/html",        .file_path = "/var/www/radio/index.html", .inline_content = null },
    .{ .path = "/nav",              .content_type = "text/html",        .file_path = "/var/www/nav/index.html", .inline_content = null },
    .{ .path = "/rss",              .content_type = "text/html",        .file_path = "/var/www/rss/index.html", .inline_content = null },
    .{ .path = "/rss.xml",          .content_type = "application/xml",  .file_path = "/var/www/rss/index.xml", .inline_content = null },
    .{ .path = "/mesh.json",        .content_type = "application/json", .file_path = null, .inline_content = null },
};


// ── Proof-of-Work gate ───────────────────────────────────────────────
const POW_DIFFICULTY = 4; // 4 leading zero bytes in SHA256 = ~1s on modern CPU
const POW_PROTECTED = [_][]const u8{ "/dogfeed", "/chat" };

fn isProtected(path: []const u8) bool {
    for (POW_PROTECTED) |p| { if (std.mem.eql(u8, path, p)) return true; }
    return false;
}

fn verifyPow(req: []const u8) bool {
    // Look for X-PoW-Nonce header
    const nonce_start = std.mem.indexOf(u8, req, "X-PoW-Nonce: ") orelse return false;
    const nonce_val_start = nonce_start + 13;
    const nonce_end = std.mem.indexOfScalar(u8, req[nonce_val_start..], '\r') orelse (req.len - nonce_val_start);
    const nonce_str = req[nonce_val_start .. nonce_val_start + nonce_end];
    
    // Look for X-PoW-Challenge header
    const chall_start = std.mem.indexOf(u8, req, "X-PoW-Challenge: ") orelse return false;
    const chall_val_start = chall_start + 18;
    const chall_end = std.mem.indexOfScalar(u8, req[chall_val_start..], '\r') orelse (req.len - chall_val_start);
    const challenge = req[chall_val_start .. chall_val_start + chall_end];
    
    // Verify: SHA256(challenge + nonce) must start with POW_DIFFICULTY zero bytes
    var buf: [128]u8 = undefined;
    const input = std.fmt.bufPrint(&buf, "{s}{s}", .{challenge, nonce_str}) catch return false;
    
    var hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &hash, .{});
    
    // Check leading zero bytes
    for (0..POW_DIFFICULTY) |i| {
        if (hash[i] != 0) return false;
    }
    return true;
}

fn servePowChallenge(cfd: i32, _: []const u8) !void {
    const challenge = "7c242080:"; // genesis-seeded challenge prefix
    var body_buf: [256]u8 = undefined;
    const body = std.fmt.bufPrint(&body_buf,
        "{{\"pow\":true,\"difficulty\":{d},\"challenge\":\"{s}\"}}",
        .{POW_DIFFICULTY, challenge}) catch unreachable;
    var hdr: [256]u8 = undefined;
    const h = std.fmt.bufPrint(&hdr, 
        "HTTP/1.1 402 Payment Required\r\nContent-Type: application/json\r\nContent-Length: {d}\r\nAccess-Control-Allow-Origin: *\r\nX-PoW-Challenge: {s}\r\nConnection: close\r\n\r\n",
        .{body.len, challenge}) catch unreachable;
    _ = linux.write(cfd, h.ptr, h.len);
    _ = linux.write(cfd, body.ptr, body.len);
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const a = arena.allocator();

    const fd = linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0);
    const s: i32 = @intCast(fd);
    defer _ = linux.close(s);

    const one: i32 = 1;
    _ = linux.setsockopt(s, linux.SOL.SOCKET, linux.SO.REUSEADDR, @ptrCast(&one), @sizeOf(i32));

    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, 8081);
    _ = linux.bind(s, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));
    _ = linux.listen(s, 128);

    std.log.info("Vaked Gateway v0.3 — :8081 · 17 routes", .{});

    while (true) {
        var ca: linux.sockaddr.in = undefined;
        var al: u32 = @sizeOf(linux.sockaddr.in);
        const cfd_u = linux.accept4(s, @ptrCast(&ca), &al, linux.SOCK.CLOEXEC);
        const cfd: i32 = @intCast(cfd_u);
        defer _ = linux.close(cfd);

        var buf: [4096]u8 = undefined;
        const n = linux.read(cfd, &buf, buf.len);
        if (n <= 0) continue;
        const req = buf[0..@intCast(n)];

        var it = std.mem.splitScalar(u8, req, '\n');
        var parts = std.mem.splitScalar(u8, it.first(), ' ');
        _ = parts.first();
        const path = parts.next() orelse "/";



        // /mesh.json
        if (std.mem.eql(u8, path, "/mesh.json")) {
            const json = "{\"t\":0,\"nodes\":6,\"status\":\"synced\"}";
            _ = respond(cfd, "200 OK", "application/json", json) catch {};
            continue;
        }

        // PoW check for protected routes
        if (isProtected(path) and !verifyPow(req)) {
            try servePowChallenge(cfd, path);
            continue;
        }

        // Search routes
        var found: ?Route = null;
        for (routes) |r| {
            if (std.mem.eql(u8, r.path, path)) { found = r; break; }
        }


        if (found) |r| {
            if (r.inline_content) |c| {
                _ = respond(cfd, "200 OK", r.content_type, c) catch {};
            } else if (r.file_path) |fp| {
                const pz = a.dupeZ(u8, fp) catch {
                    _ = respond(cfd, "500", "text/plain", "error") catch {};
                    continue;
                };
                const fdr = linux.open(pz.ptr, @bitCast(@as(u32, 0)), 0);
                const fdi: i32 = @intCast(fdr);
                if (fdi < 0) {
                    _ = respond(cfd, "404 Not Found", "text/plain", "route not found") catch {};
                    continue;
                }
                defer _ = linux.close(fdi);
                var fbuf: [65536]u8 = undefined;
                const nread = linux.read(fdi, &fbuf, fbuf.len);
                if (nread < 0) {
                    _ = respond(cfd, "500", "text/plain", "read error") catch {};
                    continue;
                }
                _ = respond(cfd, "200 OK", r.content_type, fbuf[0..@intCast(nread)]) catch {};
            }
        } else {
            _ = respond(cfd, "404 Not Found", "text/plain", "route not found") catch {};
        }
    }
}

fn respond(fd: i32, code: []const u8, ct: []const u8, body: []const u8) !void {
    var hdr: [512]u8 = undefined;
    const h = try std.fmt.bufPrint(&hdr, "HTTP/1.1 {s}\r\nContent-Type: {s}\r\nContent-Length: {d}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n", .{ code, ct, body.len });
    _ = linux.write(fd, h.ptr, h.len);
    _ = linux.write(fd, body.ptr, body.len);
}
