const std = @import("std");
const linux = std.os.linux;
pub const SearchResult = struct {
    title: []const u8,
    path: []const u8,
    preview: []const u8,
    score: f64,
};
const Document = struct {
    title: []const u8,
    path: []const u8,
    preview: []const u8,
    content: []const u8,
};
var g_docs: []Document = &.{};
var g_loaded: bool = false;
const INDEX_PATH = "chat-gateway/knowledge/index.json";
fn readFileAll(allocator: std.mem.Allocator, path: []const u8) ![]u8 {
    const path_z = try allocator.dupeZ(u8, path);
    const open_flags: linux.O = @bitCast(@as(u32, 0)); // O_RDONLY
    const fd_raw = linux.open(path_z.ptr, open_flags, 0);
    const fd: i32 = @intCast(fd_raw);
    if (fd < 0) return error.OpenFailed;
    defer _ = linux.close(fd);
    var list: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    var buf: [4096]u8 = undefined;
    while (true) {
        const n_raw = linux.read(fd, &buf, buf.len);
        const n: isize = @intCast(n_raw);
        if (n <= 0) break;
        try list.appendSlice(allocator, buf[0..@intCast(n)]);
    }
    return list.items;
}
// Minimal JSON parsing helpers (expects array of objects with
// "title", "path", "preview", "content" string fields).
fn skipWhitespace(s: []const u8, i: *usize) void {
    while (i.* < s.len) : (i.* += 1) {
        const c = s[i.*];
        if (c != ' ' and c != '\t' and c != '\n' and c != '\r') break;
    }
}
fn parseString(allocator: std.mem.Allocator, s: []const u8, i: *usize) ![]const u8 {
    skipWhitespace(s, i);
    if (i.* >= s.len or s[i.*] != '"') return error.BadJson;
    i.* += 1;
    var out: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    while (i.* < s.len) : (i.* += 1) {
        const c = s[i.*];
        if (c == '\\') {
            i.* += 1;
            if (i.* >= s.len) return error.BadJson;
            const e = s[i.*];
            const ch: u8 = switch (e) {
                'n' => '\n',
                't' => '\t',
                'r' => '\r',
                '"' => '"',
                '\\' => '\\',
                '/' => '/',
                else => e,
            };
            try out.append(allocator, ch);
        } else if (c == '"') {
            i.* += 1;
            return out.items;
        } else {
            try out.append(allocator, c);
        }
    }
    return error.BadJson;
}
fn parseIndex(allocator: std.mem.Allocator, data: []const u8) ![]Document {
    var docs: std.ArrayListUnmanaged(Document) = .{ .items = &.{}, .capacity = 0 };
    var i: usize = 0;
    skipWhitespace(data, &i);
    if (i >= data.len or data[i] != '[') return error.BadJson;
    i += 1;
    while (true) {
        skipWhitespace(data, &i);
        if (i >= data.len) break;
        if (data[i] == ']') break;
        if (data[i] == ',') {
            i += 1;
            continue;
        }
        if (data[i] != '{') break;
        i += 1;
        var doc = Document{ .title = "", .path = "", .preview = "", .content = "" };
        while (true) {
            skipWhitespace(data, &i);
            if (i >= data.len) return error.BadJson;
            if (data[i] == '}') {
                i += 1;
                break;
            }
            if (data[i] == ',') {
                i += 1;
                continue;
            }
            const key = try parseString(allocator, data, &i);
            skipWhitespace(data, &i);
            if (i >= data.len or data[i] != ':') return error.BadJson;
            i += 1;
            const val = try parseString(allocator, data, &i);
            if (std.mem.eql(u8, key, "title")) {
                doc.title = val;
            } else if (std.mem.eql(u8, key, "path")) {
                doc.path = val;
            } else if (std.mem.eql(u8, key, "preview")) {
                doc.preview = val;
            } else if (std.mem.eql(u8, key, "content")) {
                doc.content = val;
            }
        }
        try docs.append(allocator, doc);
    }
    return docs.items;
}
fn loadIndex(allocator: std.mem.Allocator) void {
    if (g_loaded) return;
    g_loaded = true;
    const data = readFileAll(allocator, INDEX_PATH) catch {
        std.log.err("search: failed to read {s}", .{INDEX_PATH});
        return;
    };
    g_docs = parseIndex(allocator, data) catch {
        std.log.err("search: failed to parse index", .{});
        return;
    };
    std.log.info("search: loaded {d} documents", .{g_docs.len});
}
fn toLowerCopy(allocator: std.mem.Allocator, s: []const u8) ![]u8 {
    const out = try allocator.alloc(u8, s.len);
    for (s, 0..) |c, idx| {
        out[idx] = std.ascii.toLower(c);
    }
    return out;
}
fn isWordChar(c: u8) bool {
    return (c >= 'a' and c <= 'z') or (c >= '0' and c <= '9');
}
fn countTerm(haystack: []const u8, term: []const u8) usize {
    if (term.len == 0) return 0;
    var count: usize = 0;
    var i: usize = 0;
    while (i + term.len <= haystack.len) {
        if (std.mem.eql(u8, haystack[i .. i + term.len], term)) {
            count += 1;
            i += term.len;
        } else {
            i += 1;
        }
    }
    return count;
}
pub fn search(allocator: std.mem.Allocator, query: []const u8) []SearchResult {
    loadIndex(allocator);
    if (g_docs.len == 0) return &.{};
    const q_lower = toLowerCopy(allocator, query) catch return &.{};
    // Split query into terms.
    var terms: std.ArrayListUnmanaged([]const u8) = .{ .items = &.{}, .capacity = 0 };
    {
        var start: usize = 0;
        var i: usize = 0;
        while (i <= q_lower.len) : (i += 1) {
            const at_end = i == q_lower.len;
            const c = if (at_end) ' ' else q_lower[i];
            if (!isWordChar(c)) {
                if (i > start) {
                    terms.append(allocator, q_lower[start..i]) catch {};
                }
                start = i + 1;
            }
        }
    }
    if (terms.items.len == 0) return &.{};
    const Scored = struct {
        result: SearchResult,
        score: f64,
    };
    var scored: std.ArrayListUnmanaged(Scored) = .{ .items = &.{}, .capacity = 0 };
    for (g_docs) |doc| {
        const content_lower = toLowerCopy(allocator, doc.content) catch continue;
        const title_lower = toLowerCopy(allocator, doc.title) catch continue;
        const total_len: f64 = @floatFromInt(if (content_lower.len == 0) 1 else content_lower.len);
        var score: f64 = 0;
        for (terms.items) |term| {
            const tf = countTerm(content_lower, term);
            const title_hits = countTerm(title_lower, term);
            // Simple TF scoring, normalized by content length;
            // title matches weighted heavily.
            score += (@as(f64, @floatFromInt(tf)) / total_len) * 1000.0;
            score += @as(f64, @floatFromInt(title_hits)) * 5.0;
        }
        if (score > 0) {
            scored.append(allocator, .{
                .score = score,
                .result = .{
                    .title = doc.title,
                    .path = doc.path,
                    .preview = doc.preview,
                    .score = score,
                },
            }) catch {};
        }
    }
    // Sort descending by score (simple selection sort).
    const items = scored.items;
    var a: usize = 0;
    while (a < items.len) : (a += 1) {
        var best = a;
        var b = a + 1;
        while (b < items.len) : (b += 1) {
            if (items[b].score > items[best].score) best = b;
        }
        if (best != a) {
            const tmp = items[a];
            items[a] = items[best];
            items[best] = tmp;
        }
    }
    const top = @min(@as(usize, 5), items.len);
    var results: std.ArrayListUnmanaged(SearchResult) = .{ .items = &.{}, .capacity = 0 };
    var k: usize = 0;
    while (k < top) : (k += 1) {
        results.append(allocator, items[k].result) catch {};
    }
    return results.items;
}