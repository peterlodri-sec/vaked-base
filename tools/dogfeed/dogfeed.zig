

const std = @import("std");
const linux = std.os.linux;

const html_head =
    \\<!DOCTYPE html>
    \\<html lang="en">
    \\<head>
    \\<meta charset="utf-8">
    \\<meta name="viewport" content="width=device-width, initial-scale=1">
    \\<title>Dogfeed Decisions</title>
    \\<style>
    \\body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 2rem; }
    \\h1 { color: #58a6ff; }
    \\.ts { color: #8b949e; font-size: 0.85rem; margin-bottom: 1.5rem; }
    \\table { border-collapse: collapse; width: 100%; background: #161b22; }
    \\th, td { border: 1px solid #30363d; padding: 0.6rem 0.9rem; text-align: left; vertical-align: top; }
    \\th { background: #21262d; color: #58a6ff; }
    \\tr:nth-child(even) td { background: #1c2128; }
    \\.ratified { color: #3fb950; font-weight: bold; }
    \\.pending { color: #d29922; }
    \\.date { color: #8b949e; white-space: nowrap; }
    \\</style>
    \\</head>
    \\<body>
    \\<h1>Dogfeed Decisions</h1>
    \\
;

const html_tail =
    \\</tbody>
    \\</table>
    \\</body>
    \\</html>
    \\
;

const Decision = struct {
    track: []const u8,
    date: []const u8,
    body: []const u8,
    ratified: bool,
};

fn openRead(path: []const u8) ?i32 {
    const flags: i32 = @bitCast(@as(u32, linux.O.RDONLY));
    const rc = linux.open(path.ptr, @bitCast(@as(u32, @intCast(flags))), 0);
    const fd: isize = @bitCast(rc);
    if (fd < 0) return null;
    return @intCast(fd);
}

fn readAll(arena: std.mem.Allocator, fd: i32) ![]u8 {
    var list: std.ArrayList(u8) = .empty;
    var buf: [4096]u8 = undefined;
    while (true) {
        const rc = linux.read(fd, &buf, buf.len);
        const n: isize = @bitCast(rc);
        if (n < 0) return error.ReadFailed;
        if (n == 0) break;
        try list.appendSlice(arena, buf[0..@intCast(n)]);
    }
    return list.items;
}

fn writeAll(fd: i32, data: []const u8) void {
    var off: usize = 0;
    while (off < data.len) {
        const rc = linux.write(fd, data.ptr + off, data.len - off);
        const n: isize = @bitCast(rc);
        if (n <= 0) break;
        off += @intCast(n);
    }
}

fn trim(s: []const u8) []const u8 {
    return std.mem.trim(u8, s, " \t\r\n");
}

fn isDateHeader(line: []const u8) ?[]const u8 {
    // line starts with "## " then YYYY-MM-DD
    if (!std.mem.startsWith(u8, line, "## ")) return null;
    const rest = trim(line[3..]);
    if (rest.len < 10) return null;
    const d = rest[0..10];
    if (d[4] != '-' or d[7] != '-') return null;
    var i: usize = 0;
    while (i < 10) : (i += 1) {
        if (i == 4 or i == 7) continue;
        if (d[i] < '0' or d[i] > '9') return null;
    }
    return d;
}

fn parseTrack(arena: std.mem.Allocator, path: []const u8) []const u8 {
    // basename without ".ralph-log.md"
    var name = path;
    if (std.mem.lastIndexOfScalar(u8, name, '/')) |idx| {
        name = name[idx + 1 ..];
    }
    const suffix = ".ralph-log.md";
    if (std.mem.endsWith(u8, name, suffix)) {
        name = name[0 .. name.len - suffix.len];
    }
    _ = arena;
    return name;
}

fn escapeHtml(arena: std.mem.Allocator, s: []const u8) ![]const u8 {
    var list: std.ArrayList(u8) = .empty;
    for (s) |c| {
        switch (c) {
            '&' => try list.appendSlice(arena, "&amp;"),
            '<' => try list.appendSlice(arena, "&lt;"),
            '>' => try list.appendSlice(arena, "&gt;"),
            '"' => try list.appendSlice(arena, "&quot;"),
            '\n' => try list.appendSlice(arena, "<br>"),
            else => try list.append(arena, c),
        }
    }
    return list.items;
}

fn parseLatest(arena: std.mem.Allocator, track: []const u8, content: []const u8) ?Decision {
    var best: ?Decision = null;
    var it = std.mem.splitScalar(u8, content, '\n');
    var cur_date: ?[]const u8 = null;
    var body: std.ArrayList(u8) = .empty;

    const flush = struct {
        fn run(
            a: std.mem.Allocator,
            tr: []const u8,
            date: ?[]const u8,
            b: *std.ArrayList(u8),
            best_ptr: *?Decision,
        ) void {
            if (date) |d| {
                const txt = trim(b.items);
                const ratified = std.mem.indexOf(u8, txt, "RATIFIED") != null or
                    std.mem.indexOf(u8, txt, "Ratified") != null or
                    std.mem.indexOf(u8, txt, "ratified") != null;
                const newer = if (best_ptr.*) |bd| std.mem.order(u8, d, bd.date) == .gt else true;
                if (newer) {
                    best_ptr.* = .{
                        .track = tr,
                        .date = a.dupe(u8, d) catch d,
                        .body = a.dupe(u8, txt) catch txt,
                        .ratified = ratified,
                    };
                }
            }
        }
    }.run;

    while (it.next()) |line| {
        if (isDateHeader(line)) |d| {
            flush(arena, track, cur_date, &body, &best);
            cur_date = d;
            body = .empty;
        } else if (cur_date != null) {
            body.appendSlice(arena, line) catch {};
            body.append(arena, '\n') catch {};
        }
    }
    flush(arena, track, cur_date, &body, &best);
    return best;
}

pub fn main(init: std.process.Init) !void {
    const arena = init.arena.allocator();

    const paths = [_][]const u8{
        "docs/decisions/core.ralph-log.md",
        "docs/decisions/build.ralph-log.md",
        "docs/decisions/runtime.ralph-log.md",
        "docs/decisions/tooling.ralph-log.md",
    };

    var decisions: std.ArrayList(Decision) = .empty;

    for (paths) |path| {
        const fd = openRead(path) orelse continue;
        defer _ = linux.close(fd);
        const content = readAll(arena, fd) catch continue;
        const track = parseTrack(arena, path);
        if (parseLatest(arena, track, content)) |d| {
            try decisions.append(arena, d);
        }
    }

    var out: std.ArrayList(u8) = .empty;
    try out.appendSlice(arena, html_head);
    try out.appendSlice(arena, "<div class=\"ts\">Generated: 2025-01-01T00:00:00Z</div>\n");
    try out.appendSlice(arena, "<table>\n<thead><tr><th>Track</th><th>Date</th><th>Status</th><th>Decision</th></tr></thead>\n<tbody>\n");

    for (decisions.items) |d| {
        try out.appendSlice(arena, "<tr><td>");
        try out.appendSlice(arena, try escapeHtml(arena, d.track));
        try out.appendSlice(arena, "</td><td class=\"date\">");
        try out.appendSlice(arena, try escapeHtml(arena, d.date));
        try out.appendSlice(arena, "</td><td>");
        if (d.ratified) {
            try out.appendSlice(arena, "<span class=\"ratified\">RATIFIED</span>");
        } else {
            try out.appendSlice(arena, "
