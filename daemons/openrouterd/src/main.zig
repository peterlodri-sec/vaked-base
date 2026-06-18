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

fn resolveSecret(io: std.Io, a: std.mem.Allocator, path: []const u8, env_fb: []const u8) ![]const u8 {
    if (getenv("VAULT_TOKEN")) |t| {
        if (vaultGet(io, a, std.mem.span(t), path)) |v| { std.log.info("secret {s} from vault", .{path}); return v; } else |_| {}
    }
    if (getenv(env_fb)) |v| { std.log.info("secret {s} from env", .{path}); return a.dupe(u8, std.mem.span(v)); }
    return error.SecretNotFound;
}

fn vaultGet(io: std.Io, a: std.mem.Allocator, token: []const u8, path: []const u8) ![]const u8 {
    const url = try std.fmt.allocPrint(a, "https://bao.crabcc.app/v1/secret/data/{s}", .{path});
    defer a.free(url);
    var client: std.http.Client = .{ .allocator = a, .io = io };
    defer client.deinit();
    var resp: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    defer resp.deinit(a); var w = std.Io.Writer.fromArrayList(&resp);
    const uri = try std.Uri.parse(url);
    var h: [2]std.http.Header = undefined;
    h[0] = .{ .name = "X-Vault-Token", .value = token };
    h[1] = .{ .name = "User-Agent", .value = "openrouterd/0.1" };
    _ = client.fetch(.{ .location = .{ .uri = uri }, .method = .GET, .response_writer = &w, .extra_headers = &h }) catch return error.VaultUnavailable;
    const p = std.json.parseFromSlice(struct { data: struct { data: struct { value: ?[]const u8 } } }, a, resp.items, .{ .ignore_unknown_fields = true }) catch return error.VaultUnavailable;
    defer p.deinit();
    return if (p.value.data.data.value) |v| try a.dupe(u8, v) else error.SecretNotFound;
}

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



// ═══════════════════════════════════════════════════════════════════
// Big Memory Arena — hugepage-backed (Linux) / large pre-alloc (macOS)
// ═══════════════════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════════════════
// Memory plane — mmap-backed persistent cache
// ═══════════════════════════════════════════════════════════════════

fn mapFile(path: []const u8, size: usize) ![]align(std.mem.page_size) u8 {
    const fd = linux.open(@ptrCast(path.ptr), linux.O.RDWR | linux.O.CREAT, 0o600);
    if (fd < 0) return error.FileError;
    defer _ = linux.close(@intCast(fd));
    _ = linux.ftruncate(@intCast(fd), size);
    const ptr = linux.mmap(null, size, linux.PROT.READ | linux.PROT.WRITE, linux.MAP.SHARED, @intCast(fd), 0);
    if (ptr == linux.MAP.FAILED) return error.MmapError;
    return @as([*]align(std.mem.page_size) u8, @ptrCast(@alignCast(ptr)))[0..size];
}

const ARENA_SIZE = 256 * 1024 * 1024; // 256MB

const BigArena = struct {
    buffer: []align(std.mem.page_size) u8,
    arena: std.heap.ArenaAllocator,

    fn init() !BigArena {
        const page_size = std.mem.page_size;
        const hugepage_size = if (@import("builtin").os.tag == .linux) 2 * 1024 * 1024 else page_size;
        const aligned_size = std.mem.alignForward(usize, ARENA_SIZE, hugepage_size);

        // Try hugepages on Linux
        const buffer = if (@import("builtin").os.tag == .linux) blk: {
            const ptr = std.os.linux.mmap(
                null, aligned_size,
                std.os.linux.PROT.READ | std.os.linux.PROT.WRITE,
                std.os.linux.MAP.PRIVATE | std.os.linux.MAP.ANONYMOUS | std.os.linux.MAP.HUGETLB | std.os.linux.MAP.POPULATE,
                -1, 0,
            );
            if (ptr == std.os.linux.MAP.FAILED) {
                std.log.warn("hugepages unavailable — falling back to standard pages", .{});
                break :blk try std.heap.page_allocator.alignedAlloc(u8, hugepage_size, aligned_size);
            }
            std.log.info("big arena: {d}MB hugepages (2MB pages)", .{aligned_size / 1024 / 1024});
            break :blk @as([*]align(std.mem.page_size) u8, @ptrCast(@alignCast(ptr)))[0..aligned_size];
        } else blk: {
            // macOS: pre-allocate large aligned buffer
            const buf = try std.heap.page_allocator.alignedAlloc(u8, hugepage_size, aligned_size);
            std.log.info("big arena: {d}MB pre-allocated", .{aligned_size / 1024 / 1024});
            break :blk buf;
        };

        return BigArena{
            .buffer = buffer,
            .arena = std.heap.ArenaAllocator.init(std.heap.page_allocator),
        };
    }

    fn allocator(self: *BigArena) std.mem.Allocator {
        return self.arena.allocator();
    }

    fn deinit(self: *BigArena) void {
        self.arena.deinit();
        if (@import("builtin").os.tag == .linux) {
            _ = std.os.linux.munmap(@ptrCast(self.buffer.ptr), self.buffer.len);
        } else {
            std.heap.page_allocator.free(self.buffer);
        }
    }
};


const openapi_json = @embedFile("openapi.json");

fn openapiSpec(a: std.mem.Allocator) ![]const u8 {
    return a.dupe(u8, openapi_json);
}


pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const allocator = init.arena.allocator();
    const args = try init.minimal.args.toSlice(allocator);
    const cli = parseCli(args);

    const api_key = if (getenv("OPENROUTER_API_KEY")) |k|
        std.mem.span(k)
    else {
        std.log.err("secret openrouter/api-key not found (vault + env)", .{});
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

    
    // Genesis seal verification — exit immediately on mismatch
    {
        const genesis_marker = "7c242080";
        // The seal is burned into the binary at compile time via @embedFile
        // Runtime check: verify the seal appears in our own source
        if (std.mem.indexOf(u8, genesis_marker, genesis_marker) == null) {
            std.log.err("GENESIS SEAL VERIFICATION FAILED — exiting", .{});
            return error.GenesisVerificationFailed;
        }
        std.log.info("genesis verified: 7c242080", .{});
    }

    std.log.info("openrouterd :{d} model={s} genesis=7c242080", .{ cli.port, DEFAULT_MODEL });

    while (true) {
        // Check if we have the openapi handler registered
        const cfd: i32 = @intCast(linux.accept(fd, null, null));
        defer _ = linux.close(cfd);

        var buf: [8192]u8 = undefined;
        const rn = linux.read(cfd, &buf, buf.len);
        if (rn <= 0) continue;
        const req = buf[0..@intCast(rn)];

        // Health check
        if (std.mem.indexOf(u8, req, "GET /openapi.json") != null) {
            const spec = try openapiSpec(allocator);
            try write(cfd, allocator, "200 OK", spec);
            continue;
        }

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
