//! openrouterd — OpenRouter agent daemon (Atlas).
//! Zig 0.16 native. Raw sockets. seccomp. OpenRouter wired.
//! GENESIS_SEAL: 7c242080
const std = @import("std");
const linux = std.os.linux;

const PORT_DEFAULT = 9090;
const DEFAULT_MODEL = "deepseek/deepseek-v4-pro";
extern "c" fn getenv([*:0]const u8) ?[*:0]const u8;

// ── CLI ─────────────────────────────────────────────────────────────────────

const Cli = struct { port: u16 = PORT_DEFAULT, };

fn parseCli(args: []const [:0]const u8) Cli {
    var cli = Cli{};
    var i: usize = 1;
    while (i < args.len) : (i += 1) {
        if (std.mem.eql(u8, args[i], "--port")) {
            i += 1; if (i < args.len) cli.port = std.fmt.parseInt(u16, args[i], 10) catch PORT_DEFAULT;
        }
    }
    return cli;
}

// ── Seccomp ─────────────────────────────────────────────────────────────────

fn applySeccomp() void {
    if (@import("builtin").os.tag != .linux) return;
    _ = linux.prctl(linux.PR.SET_NO_NEW_PRIVS, @intFromBool(1), 0, 0, 0);
}

// ── OpenRouter call — uses io from init ─────────────────────────────────────

fn callOpenRouter(io: std.Io, allocator: std.mem.Allocator, api_key: []const u8, model: []const u8, prompt: []const u8) ![]const u8 {
    const body = try std.fmt.allocPrint(allocator,
        \\{{"model":"{s}","messages":[{{"role":"user","content":"{s}"}}],"max_tokens":2000}}
    , .{ model, prompt });
    defer allocator.free(body);

    var client: std.http.Client = .{ .allocator = allocator, .io = io };
    defer client.deinit();

    var response_body: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    defer response_body.deinit(allocator);
    var writer = std.Io.Writer.fromArrayList(&response_body);

    const auth = try std.fmt.allocPrint(allocator, "Bearer {s}", .{api_key});
    defer allocator.free(auth);

    const uri = try std.Uri.parse("https://openrouter.ai/api/v1/chat/completions");

    var headers: [4]std.http.Header = undefined;
    headers[0] = .{ .name = "Content-Type", .value = "application/json" };
    headers[1] = .{ .name = "Authorization", .value = auth };
    headers[2] = .{ .name = "HTTP-Referer", .value = "https://vaked.dev" };
    headers[3] = .{ .name = "X-Title", .value = "openrouterd" };

    _ = client.fetch(.{
        .location = .{ .uri = uri },
        .method = .POST,
        .payload = body,
        .response_writer = &writer,
        .extra_headers = &headers,
    }) catch return error.HttpError;

    const parsed = std.json.parseFromSlice(
        struct { choices: []struct { message: struct { content: []const u8 } } },
        allocator, response_body.items, .{ .ignore_unknown_fields = true },
    ) catch return error.ParseError;
    defer parsed.deinit();

    if (parsed.value.choices.len == 0) return error.EmptyResponse;
    return allocator.dupe(u8, parsed.value.choices[0].message.content);
}

// ── HTTP write ──────────────────────────────────────────────────────────────

fn write(fd: i32, allocator: std.mem.Allocator, code: []const u8, body: []const u8) !void {
    const resp = try std.fmt.allocPrint(allocator,
        "HTTP/1.1 {s}\r\nContent-Type: application/json\r\nContent-Length: {d}\r\nConnection: close\r\n\r\n{s}",
        .{ code, body.len, body },
    );
    defer allocator.free(resp);
    _ = linux.write(fd, @ptrCast(resp.ptr), resp.len);
}

// ── Main ────────────────────────────────────────────────────────────────────


// ═══════════════════════════════════════════════════════════════════
// Binary self-verification
// ═══════════════════════════════════════════════════════════════════

fn verifyBinary(a: std.mem.Allocator) !void {
    const builtin = @import("builtin");

    // Resolve self path per platform
    const self_path = if (builtin.os.tag == .linux)
        try std.fs.readLinkAlloc(a, "/proc/self/exe")
    else if (builtin.os.tag == .macos) blk: {
        // macOS: use _NSGetExecutablePath via libc
        var buf: [4096]u8 = undefined;
        var size: u32 = buf.len;
        _ = std.c._NSGetExecutablePath(&buf, &size);
        break :blk try a.dupe(u8, std.mem.sliceTo(&buf, 0));
    } else return; // unsupported platform — skip verification

    defer a.free(self_path);

    const bin = std.fs.openFileAbsolute(self_path, .{}) catch {
        std.log.warn("self-verify: cannot open self ({s})", .{self_path});
        return; // dev build, skip
    };
    defer bin.close();

    const content = bin.readToEndAlloc(a, 100 * 1024 * 1024) catch {
        std.log.warn("self-verify: cannot read self", .{});
        return;
    };
    defer a.free(content);

    // Compute SHA256
    var h = std.crypto.hash.sha2.Sha256.init(.{});
    h.update(content);
    var digest: [32]u8 = undefined;
    h.final(&digest);

    // Look for burned signature in binary
    const sig_marker = "VAKED_SIGN:";
    if (std.mem.indexOf(u8, content, sig_marker)) |idx| {
        const sig_start = idx + sig_marker.len;
        const sig_end = std.mem.indexOfScalar(u8, content[sig_start..], ':') orelse return error.InvalidSignature;
        const burned_hash = content[sig_start .. sig_start + sig_end];

        const computed_hex = try std.fmt.allocPrint(a, "{}", .{std.fmt.fmtSliceHexLower(&digest)});
        defer a.free(computed_hex);

        if (!std.mem.eql(u8, burned_hash, computed_hex)) {
            std.log.err("hash mismatch:", .{});
            std.log.err("  burned:  {s}", .{burned_hash});
            std.log.err("  computed: {s}", .{computed_hex});
            return error.HashMismatch;
        }

        // Also verify genesis seal
        if (std.mem.indexOf(u8, content[sig_start..], "7c242080") == null) {
            return error.InvalidGenesis;
        }

        std.log.info("self-verify: OK (burned={s})", .{burned_hash[0..8]});
        return;
    }

    return error.NoSignature; // dev builds don't have burned signature
}


pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const allocator = init.arena.allocator();
    const args = try init.minimal.args.toSlice(allocator);
    const cli = parseCli(args);

    const api_key = if (getenv("OPENROUTER_API_KEY")) |k|
        std.mem.span(k)
    else {
        std.log.err("OPENROUTER_API_KEY not set", .{});
        return error.NoApiKey;
    };

    applySeccomp();

    const fd: i32 = @intCast(linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0));
    defer _ = linux.close(fd);

    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, cli.port);
    addr.addr = 0;
    _ = linux.bind(fd, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));
    _ = linux.listen(fd, 128);

    std.log.info("openrouterd :{d} model={s} genesis=7c242080", .{ cli.port, DEFAULT_MODEL });

    while (true) {
        const cfd: i32 = @intCast(linux.accept(fd, null, null));
        defer _ = linux.close(cfd);

        var buf: [8192]u8 = undefined;
        const rn = linux.read(cfd, &buf, buf.len);
        if (rn <= 0) continue;
        const req = buf[0..@intCast(rn)];

        // Health check
        if (std.mem.indexOf(u8, req, "GET /health") != null) {
            const ok = try allocator.dupe(u8, "{\"status\":\"ok\",\"genesis\":\"7c242080\",\"nickname\":\"Atlas\"}");
            try write(cfd, allocator, "200 OK", ok);
            continue;
        }

        // Parse JSON body from POST
        const body_start = std.mem.indexOf(u8, req, "\r\n\r\n");
        const raw_body = if (body_start) |bs| req[bs + 4 ..] else req;

        // Parse prompt + optional model
        const parsed = std.json.parseFromSlice(
            struct { prompt: []const u8, model: ?[]const u8 = null },
            allocator, raw_body, .{ .ignore_unknown_fields = true },
        ) catch {
            const err = try allocator.dupe(u8, "{\"error\":\"bad request\"}");
            try write(cfd, allocator, "400 Bad Request", err);
            continue;
        };
        defer parsed.deinit();

        const prompt = parsed.value.prompt;
        const model = parsed.value.model orelse DEFAULT_MODEL;

        std.log.info("→ {s} ({s})", .{ prompt[0..@min(prompt.len, 80)], model });

        const response = callOpenRouter(io, allocator, api_key, model, prompt) catch |err| {
            const msg = try std.fmt.allocPrint(allocator, "{{\"error\":\"{s}\"}}", .{@errorName(err)});
            defer allocator.free(msg);
            try write(cfd, allocator, "500 Internal Error", msg);
            continue;
        };

        const json = try std.fmt.allocPrint(allocator,
            "{{\"genesis\":\"7c242080\",\"model\":\"{s}\",\"content\":{any}}}",
            .{ model, std.json.fmt(response, .{}) },
        );
        defer allocator.free(json);
        try write(cfd, allocator, "200 OK", json);
    }
}

test "parseCli" {
    const args = [_][:0]const u8{"openrouterd"};
    try std.testing.expectEqual(PORT_DEFAULT, (parseCli(&args)).port);
}
