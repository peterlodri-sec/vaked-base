const std = @import("std");
const linux = std.os.linux;

const O_RDONLY: u32 = 0x0;
const O_WRONLY: u32 = 0x1;
const O_CREAT: u32 = 0o100;
const O_TRUNC: u32 = 0o1000;

const TIMESTAMP = "2025-01-15 12:00:00 UTC";

const Decision = struct {
    track: []const u8,
    date: []const u8,
    body: []const u8,
    ratified: bool,
};

fn openRead(path: []const u8) !i32 {
    const flags: u32 = O_RDONLY;
    const rc = linux.open(@ptrCast(path.ptr), @bitCast(@as(u32, flags)), 0);
    const ret: isize = @bitCast(rc);
    if (ret < 0) return error.OpenFailed;
    return @intCast(rc);
}

fn openWrite(path: []const u8) !i32 {
    const flags: u32 = O_WRONLY | O_CREAT | O_TRUNC;
    const rc = linux.open(@ptrCast(path.ptr), @bitCast(@as(u32, flags)), 0o644);
    const ret: isize = @bitCast(rc);
    if (ret < 0) return error.OpenFailed;
    return @intCast(rc);
}

fn readAll(alloc: std.mem.Allocator, fd: i32) ![]u8 {
    var list: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    var buf: [4096]u8 = undefined;
    while (true) {
        const rc = linux.read(fd, &buf, buf.len);
        const ret: isize = @bitCast(rc);
        if (ret < 0) return error.ReadFailed;
        if (ret == 0) break;
        try list.appendSlice(alloc, buf[0..@intCast(rc)]);
    }
    return list.items;
}

fn writeAll(fd: i32, data: []const u8) !void {
    var off: usize = 0;
    while (off < data.len) {
        const rc = linux.write(fd, data[off..].ptr, data.len - off);
        const ret: isize = @bitCast(rc);
        if (ret < 0) return error.WriteFailed;
        off += @intCast(rc);
    }
}

fn trim(s: []const u8) []const u8 {
    return std.mem.trim(u8, s, " \t\r\n");
}

fn extractTrack(alloc: std.mem.Allocator, path: []const u8) []const u8 {
    // basename without extension, strip ".ralph-log.md"
    var name = path;
    if (std.mem.lastIndexOfScalar(u8, name, '/')) |i| {
        name = name[i + 1 ..];
    }
    const suffix = ".ralph-log.md";
    if (std.mem.endsWith(u8, name, suffix)) {
        name = name[0 .. name.len - suffix.len];
    }
    return alloc.dupe(u8, name) catch name;
}

fn parseFile(alloc: std.mem.Allocator, content: []const u8, track: []const u8, out: *std.ArrayList(Decision)) !void {
    // find latest decision (last "## YYYY-MM-DD" header)
    var it = std.mem.splitSequence(u8, content, "\n## ");
    var latest_date: []const u8 = "";
    var latest_body: []const u8 = "";
    var found = false;

    while (it.next()) |seg| {
        // seg may start with date header (except first piece which is preamble)
        var s = seg;
        // for the very first segment, it might have leading "## "
        if (std.mem.startsWith(u8, s, "## ")) {
            s = s[3..];
        }
        // a date header looks like YYYY-MM-DD
        if (s.len < 10) continue;
        if (!isDate(s[0..10])) continue;
        const date = s[0..10];
        var body_start: usize = 10;
        if (std.mem.indexOfScalar(u8, s, '\n')) |nl| {
            body_start = nl + 1;
        } else {
            body_start = s.len;
        }
        const body = trim(s[body_start..]);
        latest_date = date;
        latest_body = body;
        found = true;
    }

    if (!found) return;

    const ratified = std.mem.indexOf(u8, latest_body, "RATIFIED") != null or
        std.mem.indexOf(u8, latest_body, "Ratified") != null or
        std.mem.indexOf(u8, latest_body, "ratified") != null;

    try out.append(alloc, .{
        .track = track,
        .date = alloc.dupe(u8, latest_date) catch latest_date,
        .body = alloc.dupe(u8, latest_body) catch latest_body,
        .ratified = ratified,
    });
}

fn isDate(s: []const u8) bool {
    if (s.len < 10) return false;
    for (0..10) |i| {
        const c = s[i];
        if (i == 4 or i == 7) {
            if (c != '-') return false;
        } else {
            if (c < '0' or c > '9') return false;
        }
    }
    return true;
}

fn escapeHtml(alloc: std.mem.Allocator, s: []const u8) []const u8 {
    var list: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    for (s) |c| {
        switch (c) {
            '&' => list.appendSlice(alloc, "&amp;") catch {},
            '<' => list.appendSlice(alloc, "&lt;") catch {},
            '>' => list.appendSlice(alloc, "&gt;") catch {},
            '"' => list.appendSlice(alloc, "&quot;") catch {},
            else => list.append(alloc, c) catch {},
        }
    }
    return list.items;
}

const HEAD =
    \\<!DOCTYPE html>
    \\<html lang="en">
    \\<head>
    \\<meta charset="utf-8">
    \\<title>Dogfeed — Decision Log</title>
    \\<style>
    \\  body { background:#0d1117; color:#c9d1d9; font-family:system-ui,sans-serif; margin:2rem; }
    \\  h1 { color:#58a6ff; }
    \\  table { border-collapse:collapse; width:100%; }
    \\  th, td { border:1px solid #30363d; padding:0.5rem 0.75rem; text-align:left; vertical-align:top; }
    \\  th { background:#161b22; color:#58a6ff; }
    \\  tr:nth-child(even) { background:#161b22; }
    \\  .ratified { color:#3fb950; font-weight:bold; }
    \\  .pending { color:#d29922; font-weight:bold; }
    \\  .ts { color:#8b949e; font-size:0.85rem; }
    \\  pre { white-space:pre-wrap; margin:0; font-family:inherit; }
    \\</style>
    \\</head>
    \\<body>
    \\<h1>Dogfeed — Decision Log</h1>
    \\<p class="ts">Generated: 
;

const HEAD2 =
    \\</p>
    \\<table>
    \\<thead><tr><th>Track</th><th>Latest Date</th><th>Status</th><th>Decision</th></tr></thead>
    \\<tbody>
    \\
;

const FOOT =
    \\</tbody>
    \\</table>
    \\</body>
    \\</html>
    \\
;

pub fn main(init: std.process.Init) !void {
    const alloc = init.arena.allocator();

    const paths = [_][]const u8{
        "docs/decisions/architecture.ralph-log.md\x00",
        "docs/decisions/process.ralph-log.md\x00",
        "docs/decisions/tooling.ralph-log.md\x00",
        "docs/decisions/api.ralph-log.md\x00",
    };

    var decisions: std.ArrayListUnmanaged(Decision) = .{ .items = &.{}, .capacity = 0 };

    for (paths) |p| {
        const fd = openRead(p) catch continue;
        defer _ = linux.close(fd);
        const content = readAll(alloc, fd) catch continue;
        const track = extractTrack(alloc, p[0 .. p.len - 1]);
        parseFile(alloc, content, track, &decisions) catch continue;
    }

    var out: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    try out.appendSlice(alloc, HEAD);
    try out.appendSlice(alloc, TIMESTAMP);
    try out.appendSlice(alloc, HEAD2);

    for (decisions.items) |d| {
        try out.appendSlice(alloc, "<tr><td>");
        try out.appendSlice(alloc, escapeHtml(alloc, d.track));
        try out.appendSlice(alloc, "</td><td>");
        try out.appendSlice(alloc, escapeHtml(alloc, d.date));
        try out.appendSlice(alloc, "</td><td>");
        if (d.ratified) {
            try out.appendSlice(alloc, "<span class=\"ratified\">RATIFIED</span>");
        } else {
            try out.appendSlice(alloc, "<span class=\"pending\">PENDING</span>");
        }
        try out.appendSlice(alloc, "</td><td><pre>");
        try out.appendSlice(alloc, escapeHtml(alloc, d.body));
        try out.appendSlice(alloc, "</pre></td></tr>\n");
    }

    try out.appendSlice(alloc, FOOT);

    const outfd = try openWrite("dogfeed.html\x00");
    defer _ = linux.close(outfd);
    try writeAll(outfd, out.items);
}
