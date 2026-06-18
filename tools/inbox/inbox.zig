const std = @import("std");

const MCP_URL = "https://agentic-inbox.cabotage.workers.dev/mcp";

const Config = struct {
    client_id: []const u8,
    client_secret: []const u8,

    fn fromEnv(allocator: std.mem.Allocator) !Config {
        const id = std.process.getEnvVarOwned(allocator, "CF_ACCESS_CLIENT_ID") catch
            return error.MissingClientId;
        errdefer allocator.free(id);
        const secret = std.process.getEnvVarOwned(allocator, "CF_ACCESS_CLIENT_SECRET") catch
            return error.MissingClientSecret;
        return .{ .client_id = id, .client_secret = secret };
    }

    fn deinit(self: Config, allocator: std.mem.Allocator) void {
        allocator.free(self.client_id);
        allocator.free(self.client_secret);
    }
};

const Mode = enum {
    monologue,
    audit,
};

const Args = struct {
    to: []const u8,
    subject: []const u8,
    body: []const u8,
    mode: Mode,
};

/// Run a curl subprocess with the given JSON-RPC payload, returning the raw
/// response body (which may be SSE-framed). Caller owns the returned slice.
fn curlPost(
    allocator: std.mem.Allocator,
    config: Config,
    session_id: ?[]const u8,
    payload: []const u8,
) ![]u8 {
    var argv = std.ArrayList([]const u8){};
    defer argv.deinit(allocator);

    try argv.append(allocator, "curl");
    try argv.append(allocator, "-sS");
    try argv.append(allocator, "-X");
    try argv.append(allocator, "POST");
    try argv.append(allocator, MCP_URL);

    // Standard MCP HTTP headers
    try argv.append(allocator, "-H");
    try argv.append(allocator, "Content-Type: application/json");
    try argv.append(allocator, "-H");
    try argv.append(allocator, "Accept: application/json, text/event-stream");

    // Cloudflare Access service token headers
    const id_header = try std.fmt.allocPrint(
        allocator,
        "CF-Access-Client-Id: {s}",
        .{config.client_id},
    );
    defer allocator.free(id_header);
    try argv.append(allocator, "-H");
    try argv.append(allocator, id_header);

    const secret_header = try std.fmt.allocPrint(
        allocator,
        "CF-Access-Client-Secret: {s}",
        .{config.client_secret},
    );
    defer allocator.free(secret_header);
    try argv.append(allocator, "-H");
    try argv.append(allocator, secret_header);

    var sess_header: ?[]const u8 = null;
    defer if (sess_header) |h| allocator.free(h);
    if (session_id) |sid| {
        sess_header = try std.fmt.allocPrint(
            allocator,
            "Mcp-Session-Id: {s}",
            .{sid},
        );
        try argv.append(allocator, "-H");
        try argv.append(allocator, sess_header.?);
    }

    // Include response headers in output so we can scrape the session id.
    try argv.append(allocator, "-i");

    try argv.append(allocator, "--data-binary");
    try argv.append(allocator, payload);

    var child = std.process.Child.init(argv.items, allocator);
    child.stdout_behavior = .Pipe;
    child.stderr_behavior = .Pipe;

    try child.spawn();

    const stdout = try child.stdout.?.readToEndAlloc(allocator, 16 * 1024 * 1024);
    errdefer allocator.free(stdout);
    const stderr = try child.stderr.?.readToEndAlloc(allocator, 1024 * 1024);
    defer allocator.free(stderr);

    const term = try child.wait();
    switch (term) {
        .Exited => |code| {
            if (code != 0) {
                std.debug.print("curl exited with code {d}: {s}\n", .{ code, stderr });
                allocator.free(stdout);
                return error.CurlFailed;
            }
        },
        else => {
            std.debug.print("curl terminated abnormally\n", .{});
            allocator.free(stdout);
            return error.CurlFailed;
        },
    }

    return stdout;
}

/// Split an HTTP response (-i mode) into header and body parts.
const HttpResponse = struct {
    headers: []const u8,
    body: []const u8,
};

fn splitHttp(raw: []const u8) HttpResponse {
    // Handle possible chained 100-continue / multiple header blocks by taking
    // the last "\r\n\r\n" that precedes the actual JSON/SSE body.
    var search = raw;
    var header_end: usize = 0;
    var body_start: usize = 0;

    // Find the final header/body boundary.
    while (std.mem.indexOf(u8, search, "\r\n\r\n")) |idx| {
        const after = idx + 4;
        // If what follows still looks like another HTTP status line, keep going.
        const rest = search[after..];
        if (std.mem.startsWith(u8, rest, "HTTP/")) {
            const consumed = after;
            header_end += consumed;
            body_start = header_end;
            search = search[after..];
            continue;
        }
        header_end += idx;
        body_start += after;
        break;
    }

    if (body_start == 0 and header_end == 0) {
        // No boundary found; treat all as body.
        return .{ .headers = raw[0..0], .body = raw };
    }

    return .{ .headers = raw[0..header_end], .body = raw[body_start..] };
}

/// Extract the Mcp-Session-Id header value (case-insensitive). Returns a slice
/// into `headers`.
fn findSessionId(headers: []const u8) ?[]const u8 {
    var it = std.mem.splitSequence(u8, headers, "\r\n");
    while (it.next()) |line| {
        const colon = std.mem.indexOfScalar(u8, line, ':') orelse continue;
        const name = std.mem.trim(u8, line[0..colon], " ");
        if (std.ascii.eqlIgnoreCase(name, "mcp-session-id")) {
            return std.mem.trim(u8, line[colon + 1 ..], " ");
        }
    }
    return null;
}

/// Parse an SSE-framed (or plain JSON) MCP response body into the JSON payload
/// of the first/last `data:` event. Caller owns the returned slice.
fn extractJson(allocator: std.mem.Allocator, body: []const u8) ![]u8 {
    const trimmed = std.mem.trim(u8, body, " \r\n\t");

    // Plain JSON?
    if (trimmed.len > 0 and (trimmed[0] == '{' or trimmed[0] == '[')) {
        return allocator.dupe(u8, trimmed);
    }

    // SSE: gather all "data:" lines; the JSON-RPC result is typically the last.
    var result = std.ArrayListUnmanaged(u8){ .items = &.{}, .capacity = 0 };
    defer result.deinit(allocator);

    var found = false;
    var it = std.mem.splitSequence(u8, body, "\n");
    while (it.next()) |raw_line| {
        const line = std.mem.trimRight(u8, raw_line, "\r");
        if (std.mem.startsWith(u8, line, "data:")) {
            const data = std.mem.trimLeft(u8, line[5..], " ");
            if (data.len == 0) continue;
            // New event payload replaces previous (we want the last JSON object).
            if (data[0] == '{' or data[0] == '[') {
                result.clearRetainingCapacity();
                try result.appendSlice(allocator, data);
                found = true;
            } else if (found) {
                // continuation of multi-line data field
                try result.append(allocator, '\n');
                try result.appendSlice(allocator, data);
            }
        }
    }

    if (!found) return error.NoJsonInResponse;
    return result.toOwnedSlice(allocator);
}

/// Initialize the MCP session. Returns the session id (caller owns).
fn mcpInitialize(allocator: std.mem.Allocator, config: Config) ![]u8 {
    const init_payload =
        \\{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"inbox-bridge-zig","version":"1.0.0"}}}
    ;

    const raw = try curlPost(allocator, config, null, init_payload);
    defer allocator.free(raw);

    const http = splitHttp(raw);
    const sid = findSessionId(http.headers) orelse {
        std.debug.print("initialize response missing Mcp-Session-Id\n", .{});
        std.debug.print("raw: {s}\n", .{raw});
        return error.NoSessionId;
    };

    // Validate that we actually got a JSON-RPC result.
    const json = extractJson(allocator, http.body) catch {
        std.debug.print("initialize: could not parse response body\n", .{});
        return error.InitFailed;
    };
    defer allocator.free(json);

    return allocator.dupe(u8, sid);
}

/// Send the "initialized" notification after initialize.
fn mcpInitialized(allocator: std.mem.Allocator, config: Config, session_id: []const u8) !void {
    const payload =
        \\{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
    ;
    const raw = try curlPost(allocator, config, session_id, payload);
    allocator.free(raw);
}

/// JSON-escape a string into `out`.
fn jsonEscape(out: *std.ArrayList(u8), allocator: std.mem.Allocator, s: []const u8) !void {
    for (s) |c| {
        switch (c) {
            '"' => try out.appendSlice(allocator, "\\\""),
            '\\' => try out.appendSlice(allocator, "\\\\"),
            '\n' => try out.appendSlice(allocator, "\\n"),
            '\r' => try out.appendSlice(allocator, "\\r"),
            '\t' => try out.appendSlice(allocator, "\\t"),
            0x08 => try out.appendSlice(allocator, "\\b"),
            0x0C => try out.appendSlice(allocator, "\\f"),
            else => {
                if (c < 0x20) {
                    try out.writer(allocator).print("\\u{x:0>4}", .{c});
                } else {
                    try out.append(allocator, c);
                }
            },
        }
    }
}

/// Call the send_email tool.
fn mcpSendEmail(
    allocator: std.mem.Allocator,
    config: Config,
    session_id: []const u8,
    args: Args,
) !void {
    var payload = std.ArrayListUnmanaged(u8){ .items = &.{}, .capacity = 0 };
    defer payload.deinit(allocator);

    const w = payload.writer(allocator);
    try w.writeAll(
        \\{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"send_email","arguments":{"to":"
    );
    try jsonEscape(&payload, allocator, args.to);
    try w.writeAll("\",\"subject\":\"");
    try jsonEscape(&payload, allocator, args.subject);
    try w.writeAll("\",\"body\":\"");
    try jsonEscape(&payload, allocator, args.body);
    try w.writeAll("\"}}}");

    const raw = try curlPost(allocator, config, session_id, payload.items);
    defer allocator.free(raw);

    const http = splitHttp(raw);
    const json = try extractJson(allocator, http.body);
    defer allocator.free(json);

    // Parse for an "error" field.
    const parsed = std.json.parseFromSlice(std.json.Value, allocator, json, .{}) catch {
        std.debug.print("send_email: malformed response: {s}\n", .{json});
        return error.SendFailed;
    };
    defer parsed.deinit();

    if (parsed.value == .object) {
        if (parsed.value.object.get("error")) |err| {
            std.debug.print("send_email error: {f}\n", .{std.json.fmt(err, .{})});
            return error.SendFailed;
        }
    }

    std.debug.print("send_email result: {s}\n", .{json});
}

fn printUsage(prog: []const u8) void {
    std.debug.print(
        \\Usage: {s} <mode> --to <addr> --subject <s> --body <b>
        \\
        \\Modes:
        \\  monologue   Send an agent monologue email.
        \\  audit       Send an audit report email.
        \\
        \\Environment:
        \\  CF_ACCESS_CLIENT_ID       Cloudflare Access service token id
        \\  CF_ACCESS_CLIENT_SECRET   Cloudflare Access service token secret
        \\
    , .{prog});
}

fn parseArgs(allocator: std.mem.Allocator) !Args {
    var it = try std.process.argsWithAllocator(allocator);
    defer it.deinit();

    const prog = it.next() orelse "bridge";

    const mode_str = it.next() orelse {
        printUsage(prog);
        return error.MissingMode;
    };

    const mode: Mode = if (std.mem.eql(u8, mode_str, "monologue"))
        .monologue
    else if (std.mem.eql(u8, mode_str, "audit"))
        .audit
    else {
        std.debug.print("Unknown mode: {s}\n", .{mode_str});
        printUsage(prog);
        return error.UnknownMode;
    };

    var to: ?[]const u8 = null;
    var subject: ?[]const u8 = null;
    var body: ?[]const u8 = null;

    while (it.next()) |arg| {
        if (std.mem.eql(u8, arg, "--to")) {
            to = try allocator.dupe(u8, it.next() orelse return error.MissingValue);
        } else if (std.mem.eql(u8, arg, "--subject")) {
            subject = try allocator.dupe(u8, it.next() orelse return error.MissingValue);
        } else if (std.mem.eql(u8, arg, "--body")) {
            body = try allocator.dupe(u8, it.next() orelse return error.MissingValue);
        } else {
            std.debug.print("Unknown argument: {s}\n", .{arg});
            return error.UnknownArg;
        }
    }

    // Subject prefixes per mode, matching the Python behaviour.
    const base_subject = subject orelse return error.MissingSubject;
    const final_subject = switch (mode) {
        .monologue => try std.fmt.allocPrint(allocator, "[monologue] {s}", .{base_subject}),
        .audit => try std.fmt.allocPrint(allocator, "[audit] {s}", .{base_subject}),
    };

    return .{
        .to = to orelse return error.MissingTo,
        .subject = final_subject,
        .body = body orelse return error.MissingBody,
        .mode = mode,
    };
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    const config = Config.fromEnv(allocator) catch |err| {
        switch (err) {
            error.MissingClientId => std.debug.print("CF_ACCESS_CLIENT_ID not set\n", .{}),
            error.MissingClientSecret => std.debug.print("CF_ACCESS_CLIENT_SECRET not set\n", .{}),
            else => std.debug.print("config error: {s}\n", .{@errorName(err)}),
        }
        std.process.exit(1);
    };
    defer config.deinit(allocator);

    const args = parseArgs(allocator) catch {
        std.process.exit(2);
    };

    std.debug.print("Initializing MCP session...\n", .{});
    const session_id = try mcpInitialize(allocator, config);
    defer allocator.free(session_id);
    std.debug.print("Session: {s}\n", .{session_id});

    try mcpInitialized(allocator, config, session_id);

    std.debug.print("Sending email ({s}) to {s}...\n", .{ @tagName(args.mode), args.to });
    try mcpSendEmail(allocator, config, session_id, args);

    std.debug.print("Done.\n", .{});
}
