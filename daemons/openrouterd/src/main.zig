//! openrouterd — OpenRouter agent daemon (Atlas).
//! Zig 0.16 native. Raw sockets. Conductor routing. OpenRouter wired.
//! GENESIS_SEAL: 7c242080
const std = @import("std");
const linux = std.os.linux;
const builtin = @import("builtin");

const PORT = 9090;
const DEFAULT_MODEL = "deepseek/deepseek-v4-pro";
const MAX_REQ = 65536;
extern "c" fn getenv([*:0]const u8) ?[*:0]const u8;

// ═══════════════════════════════════════════════════════════════════
// CLI
// ═══════════════════════════════════════════════════════════════════

const Cli = struct { port: u16 = PORT, };

fn parseCli(args: []const [:0]const u8) Cli {
    var c = Cli{};
    var i: usize = 1;
    while (i < args.len) : (i += 1) {
        if (std.mem.eql(u8, args[i], "--port")) { i += 1; if (i < args.len) c.port = std.fmt.parseInt(u16, args[i], 10) catch PORT; }
    }
    return c;
}

// ═══════════════════════════════════════════════════════════════════
// Seccomp
// ═══════════════════════════════════════════════════════════════════

fn seccomp() void {
    if (builtin.os.tag != .linux) return;
    _ = linux.prctl(linux.PR.SET_NO_NEW_PRIVS, @intFromBool(1), 0, 0, 0);
}

// ═══════════════════════════════════════════════════════════════════
// Conductor — model self-selection
// ═══════════════════════════════════════════════════════════════════

fn routeModel(prompt: []const u8) []const u8 {
    if (prompt.len == 0) return DEFAULT_MODEL;
    const code_kw = [_][]const u8{ "code", "write", "implement", "fix", "debug", "test", "refactor", "optimize", "review" };
    for (code_kw) |kw| { if (std.ascii.indexOfIgnoreCase(prompt, kw) != null) return "anthropic/claude-opus-4-8-fast"; }
    const creative_kw = [_][]const u8{ "creative", "brainstorm", "design", "story" };
    for (creative_kw) |kw| { if (std.ascii.indexOfIgnoreCase(prompt, kw) != null) return "google/gemini-2.5-flash"; }
    return DEFAULT_MODEL;
}

// ═══════════════════════════════════════════════════════════════════
// OpenRouter API call
// ═══════════════════════════════════════════════════════════════════

fn callOpenRouter(io: std.Io, a: std.mem.Allocator, api_key: []const u8, model: []const u8, prompt: []const u8) ![]const u8 {
    const body = try std.fmt.allocPrint(a,
        \\{{"model":"{s}","messages":[{{"role":"user","content":"{s}"}}],"max_tokens":2000}}
    , .{ model, prompt });
    defer a.free(body);

    var client: std.http.Client = .{ .allocator = a, .io = io };
    defer client.deinit();

    var resp: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    defer resp.deinit(a);
    var writer = std.Io.Writer.fromArrayList(&resp);

    const auth = try std.fmt.allocPrint(a, "Bearer {s}", .{api_key});
    defer a.free(auth);

    const uri = try std.Uri.parse("https://openrouter.ai/api/v1/chat/completions");
    var hdrs: [4]std.http.Header = undefined;
    hdrs[0] = .{ .name = "Content-Type", .value = "application/json" };
    hdrs[1] = .{ .name = "Authorization", .value = auth };
    hdrs[2] = .{ .name = "HTTP-Referer", .value = "https://vaked.dev" };
    hdrs[3] = .{ .name = "X-Title", .value = "openrouterd" };

    _ = client.fetch(.{ .location = .{ .uri = uri }, .method = .POST, .payload = body, .response_writer = &writer, .extra_headers = &hdrs }) catch return error.HttpError;

    const parsed = std.json.parseFromSlice(
        struct { choices: []struct { message: struct { content: []const u8 } } },
        a, resp.items, .{ .ignore_unknown_fields = true },
    ) catch return error.ParseError;
    defer parsed.deinit();

    if (parsed.value.choices.len == 0) return error.EmptyResponse;
    return a.dupe(u8, parsed.value.choices[0].message.content);
}

// ═══════════════════════════════════════════════════════════════════
// HTTP response
// ═══════════════════════════════════════════════════════════════════

fn respond(fd: i32, a: std.mem.Allocator, code: []const u8, body: []const u8) !void {
    const r = try std.fmt.allocPrint(a, "HTTP/1.1 {s}\r\nContent-Type: application/json\r\nContent-Length: {d}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n{s}", .{ code, body.len, body });
    defer a.free(r);
    _ = linux.write(fd, @ptrCast(r.ptr), r.len);
}

fn respondSSE(fd: i32, a: std.mem.Allocator, data: []const u8) !void {
    const r = try std.fmt.allocPrint(a, "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\nConnection: keep-alive\r\nAccess-Control-Allow-Origin: *\r\n\r\ndata: {s}\n\n", .{data});
    defer a.free(r);
    _ = linux.write(fd, @ptrCast(r.ptr), r.len);
}

// ═══════════════════════════════════════════════════════════════════
// Main
// ═══════════════════════════════════════════════════════════════════

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const a = init.arena.allocator();
    const args = try init.minimal.args.toSlice(a);
    const cli = parseCli(args);

    const api_key = if (getenv("OPENROUTER_API_KEY")) |k| std.mem.span(k) else {
        std.log.err("OPENROUTER_API_KEY not set", .{});
        return error.NoApiKey;
    };

    seccomp();

    const fd: i32 = @intCast(linux.socket(linux.AF.INET, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0));
    defer _ = linux.close(fd);

    var addr = std.mem.zeroes(linux.sockaddr.in);
    addr.family = linux.AF.INET;
    addr.port = std.mem.nativeToBig(u16, cli.port);
    _ = linux.bind(fd, @ptrCast(&addr), @sizeOf(linux.sockaddr.in));
    _ = linux.listen(fd, 128);

    std.log.info("openrouterd :{d} model={s} genesis=7c242080", .{ cli.port, DEFAULT_MODEL });

    while (true) {
        const cfd: i32 = @intCast(linux.accept(fd, null, null));
        defer _ = linux.close(cfd);

        var buf: [MAX_REQ]u8 = undefined;
        const rn = linux.read(cfd, &buf, buf.len);
        if (rn <= 0) continue;
        const req = buf[0..@intCast(rn)];

        // GET /health
        if (std.mem.indexOf(u8, req, "GET /health") != null) {
            const ok = try a.dupe(u8, "{\"status\":\"ok\",\"genesis\":\"7c242080\",\"nickname\":\"Atlas\",\"defaultModel\":\"" ++ DEFAULT_MODEL ++ "\"}");
            try respond(cfd, a, "200 OK", ok);
            continue;
        }

        // GET /models
        if (std.mem.indexOf(u8, req, "GET /models") != null) {
            const ms = try a.dupe(u8,
                "{\"models\":[\"deepseek/deepseek-v4-pro\",\"deepseek/deepseek-v4-flash\",\"anthropic/claude-opus-4-8-fast\",\"google/gemini-2.5-flash\",\"qwen/qwen3-235b-a22b-thinking\",\"meta-llama/llama-4-maverick\"]}");
            try respond(cfd, a, "200 OK", ms);
            continue;
        }

        // POST — parse body
        const bs = std.mem.indexOf(u8, req, "\r\n\r\n") orelse 0;
        const raw = if (bs > 0) req[bs + 4 ..] else req;
        const is_stream = std.mem.indexOf(u8, raw, "\"stream\":true") != null or std.mem.indexOf(u8, raw, "\"stream\": true") != null;

        const parsed = std.json.parseFromSlice(
            struct { prompt: []const u8, model: ?[]const u8 = null, auto: bool = false },
            a, raw, .{ .ignore_unknown_fields = true },
        ) catch {
            const err = try a.dupe(u8, "{\"error\":\"bad request\"}");
            try respond(cfd, a, "400 Bad Request", err);
            continue;
        };
        defer parsed.deinit();

        const prompt = parsed.value.prompt;
        var model: []const u8 = parsed.value.model orelse DEFAULT_MODEL;
        if (parsed.value.auto) model = routeModel(prompt);

        std.log.info("→ {s} [{s}]", .{ prompt[0..@min(prompt.len, 80)], model });

        const response = callOpenRouter(io, a, api_key, model, prompt) catch |err| {
            std.log.err("API: {s}", .{@errorName(err)});
            const msg = try std.fmt.allocPrint(a, "{{\"error\":\"{s}\"}}", .{@errorName(err)});
            defer a.free(msg);
            try respond(cfd, a, "500 Internal Error", msg);
            continue;
        };

        if (is_stream) {
            try respondSSE(cfd, a, response);
        } else {
            const json = try std.fmt.allocPrint(a, "{{\"genesis\":\"7c242080\",\"model\":\"{s}\",\"content\":{any}}}", .{ model, std.json.fmt(response, .{}) });
            defer a.free(json);
            try respond(cfd, a, "200 OK", json);
        }
    }
}

test "cli" { try std.testing.expectEqual(PORT, (parseCli(&[_][:0]const u8{"openrouterd"})).port); }
test "routeModel code" { try std.testing.expect(std.mem.indexOf(u8, routeModel("write a function"), "claude") != null); }
test "routeModel creative" { try std.testing.expect(std.mem.indexOf(u8, routeModel("brainstorm ideas"), "gemini") != null); }
test "routeModel default" { try std.testing.expect(std.mem.indexOf(u8, routeModel("hello"), "deepseek") != null); }
