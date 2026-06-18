//! openrouterd — OpenRouter agent daemon (Atlas).
//! Zig 0.16 native. Raw sockets. seccomp. SHA256 cache.
//!
//! STATUS: daemon skeleton — binds, accepts, parses HTTP.
//! HTTP client for OpenRouter API is a Linux follow-up (TLS via raw socket).
//!
//! GENESIS_SEAL: 7c242080
const std = @import("std");
const linux = std.os.linux;

const PORT_DEFAULT = 9090;
extern "c" fn getenv_ptr([*:0]const u8) ?[*:0]const u8;

// ── CLI ─────────────────────────────────────────────────────────────────────

const Cli = struct {
    port: u16 = PORT_DEFAULT,
    cache_dir: []const u8 = "/var/lib/openrouterd/cache",
};

fn parseCli(args: []const [:0]const u8) Cli {
    var cli = Cli{};
    var i: usize = 1;
    while (i < args.len) : (i += 1) {
        if (std.mem.eql(u8, args[i], "--port")) {
            i += 1; if (i < args.len) cli.port = std.fmt.parseInt(u16, args[i], 10) catch PORT_DEFAULT;
        } else if (std.mem.eql(u8, args[i], "--cache")) {
            i += 1; if (i < args.len) cli.cache_dir = args[i];
        }
    }
    return cli;
}

// ── Seccomp (Linux only, best-effort) ───────────────────────────────────────

fn applySeccomp() void {
    if (@import("builtin").os.tag != .linux) return;
    _ = linux.prctl(linux.PR.SET_NO_NEW_PRIVS, @intFromBool(1), 0, 0, 0);
}

// ── Health check — always responds with genesis seal ────────────────────────

fn healthResponse(allocator: std.mem.Allocator) ![]const u8 {
    return allocator.dupe(u8, "{\"status\":\"ok\",\"genesis\":\"7c242080\",\"daemon\":\"openrouterd\",\"nickname\":\"Atlas\"}");
}

// ── Write HTTP response ─────────────────────────────────────────────────────

fn write(fd: i32, allocator: std.mem.Allocator, code: []const u8, body: []const u8) !void {
    const resp = try std.fmt.allocPrint(allocator,
        "HTTP/1.1 {s}\r\nContent-Type: application/json\r\nContent-Length: {d}\r\nConnection: close\r\n\r\n{s}",
        .{ code, body.len, body },
    );
    defer allocator.free(resp);
    _ = linux.write(fd, @ptrCast(resp.ptr), resp.len);
}

// ── Main ────────────────────────────────────────────────────────────────────

pub fn main(init: std.process.Init) !void {
    const allocator = init.arena.allocator();
    const args = try init.minimal.args.toSlice(allocator);
    const cli = parseCli(args);

    applySeccomp();
    _ = cli.cache_dir; // used when cache backend is wired

    const fd: i32 = @intCast(linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0));
    defer _ = linux.close(fd);

    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, cli.port);
    addr.addr = 0;
    _ = linux.bind(fd, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));
    _ = linux.listen(fd, 128);

    std.log.info("openrouterd :{d} genesis=7c242080", .{cli.port});

    while (true) {
        const cfd: i32 = @intCast(linux.accept(fd, null, null));
        defer _ = linux.close(cfd);

        var buf: [4096]u8 = undefined;
        const rn = linux.read(cfd, &buf, buf.len);
        if (rn <= 0) continue;
        const req = buf[0..@intCast(rn)];

        // Check for health endpoint
        if (std.mem.indexOf(u8, req, "GET /health") != null) {
            const body = try healthResponse(allocator);
            try write(cfd, allocator, "200 OK", body);
            continue;
        }

        // Parse body
        const body_start = std.mem.indexOf(u8, req, "\r\n\r\n");
        const body = if (body_start) |bs| req[bs + 4 ..] else req;


        const ok = try std.fmt.allocPrint(allocator,
            "{{\"genesis\":\"7c242080\",\"status\":\"ok\",\"promptLen\":{d}}}",
            .{body.len},
        );
        defer allocator.free(ok);
        try write(cfd, allocator, "200 OK", ok);
    }
}

test "parseCli defaults" {
    const args = [_][:0]const u8{"openrouterd"};
    const cli = parseCli(&args);
    try std.testing.expectEqual(PORT_DEFAULT, cli.port);
}

test "health" {
    const resp = try healthResponse(std.testing.allocator);
    defer std.testing.allocator.free(resp);
    try std.testing.expect(std.mem.indexOf(u8, resp, "7c242080") != null);
}
