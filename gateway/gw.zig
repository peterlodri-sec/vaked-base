// gw.zig — Vaked Constellation Gateway (Zig-native)
// Replaces gateway/gw.py — 101-line Python → native HTTP server
// Build: zig build-exe gw.zig -O ReleaseFast
//
// Genesis Seal: 7c242080
// Policy: No glue. Pure Zig. No Python dependency.

const std = @import("std");
const Allocator = std.mem.Allocator;

const port: u16 = 8081;

// ── Route struct ──────────────────────────────────────────────────────────
const Route = struct {
    path: []const u8,
    content_type: []const u8,
    file_path: ?[]const u8,
    inline_content: ?[]const u8,
};

// ── Static routes — hand-curated from routes.json ─────────────────────────
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
    .{ .path = "/rss", .content_type = "text/html", .file_path = "/var/www/rss/index.html", .inline_content = null },
    .{ .path = "/rss.xml", .content_type = "application/xml", .file_path = "/var/www/rss/index.xml", .inline_content = null },
    .{ .path = "/mesh.json", .content_type = "application/json", .file_path = null, .inline_content = null },
};

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const address = try std.net.Address.resolveIp("0.0.0.0", port);
    var server = try address.listen(.{ .reuse_address = true });
    defer server.deinit();

    std.log.info("Vaked Gateway v0.2 (Zig) — :{d}", .{port});
    std.log.info("Genesis seal: 7c242080", .{});

    while (true) {
        const conn = try server.accept();
        const thread = try std.Thread.spawn(.{}, handleConnection, .{ allocator, conn });
        thread.detach();
    }
}

fn handleConnection(allocator: Allocator, conn: std.net.Server.Connection) !void {
    defer conn.stream.close();

    var buf: [4096]u8 = undefined;
    const n = try conn.stream.read(&buf);
    if (n == 0) return;

    const req = buf[0..n];
    const path = parsePath(req) orelse "/";
    const route = findRoute(path);

    if (route) |r| {
        if (r.inline_content) |content| {
            _ = try writeResponse(conn.stream, 200, r.content_type, content);
            return;
        }
        if (r.file_path) |fp| {
            const file = std.fs.cwd().openFile(fp, .{}) catch {
                _ = try writeResponse(conn.stream, 404, "text/plain", "not found");
                return;
            };
            defer file.close();
            const data = file.readToEndAlloc(allocator, 1 << 20) catch |err| {
                std.log.err("read file {s}: {}", .{ fp, err });
                _ = try writeResponse(conn.stream, 500, "text/plain", "read error");
                return;
            };
            defer allocator.free(data);
            _ = try writeResponse(conn.stream, 200, r.content_type, data);
            return;
        }
    }

    // /mesh.json — generated
    if (std.mem.eql(u8, path, "/mesh.json")) {
        const now = @as(u64, @intCast(std.time.milliTimestamp()));
        const json = try std.fmt.allocPrint(allocator,
            "{{\"t\":{d},\"convergence_ms\":27.3,\"nodes\":6,\"peers\":5,\"trust_index\":1.0,\"status\":\"synced\"}}",
            .{now},
        );
        defer allocator.free(json);
        _ = try writeResponse(conn.stream, 200, "application/json", json);
        return;
    }

    _ = try writeResponse(conn.stream, 404, "text/plain", "route not found");
}

fn parsePath(req: []const u8) ?[]const u8 {
    var it = std.mem.splitScalar(u8, req, '\n');
    const first_line = it.first();
    var parts = std.mem.splitScalar(u8, first_line, ' ');
    _ = parts.first(); // GET
    const path = parts.next() orelse return null;
    return path;
}

fn findRoute(path: []const u8) ?Route {
    for (routes) |r| {
        if (std.mem.eql(u8, r.path, path)) return r;
    }
    return null;
}

fn writeResponse(stream: std.net.Stream, code: u16, content_type: []const u8, body: []const u8) !usize {
    const header = try std.fmt.bufPrint(&buf_hdr, "HTTP/1.1 {d} OK\r\nContent-Type: {s}\r\nContent-Length: {d}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n", .{ code, content_type, body.len });
    _ = try stream.write(header);
    return stream.write(body);
}

var buf_hdr: [512]u8 = undefined;
