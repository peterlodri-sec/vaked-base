const std = @import("std");
const linux = std.os.linux;

const NotesDir = "notes";

const Note = struct {
    name: []u8,
    content: []u8,
};

const AlignmentPoint = struct {
    name: []const u8,
    description: []const u8,
    present: bool,
    detail: []const u8,
};

fn write_all(fd: i32, bytes: []const u8) void {
    var off: usize = 0;
    while (off < bytes.len) {
        const n = linux.write(fd, bytes.ptr + off, bytes.len - off);
        const r: isize = @bitCast(n);
        if (r <= 0) break;
        off += @intCast(r);
    }
}

fn read_file(alloc: std.mem.Allocator, path: []const u8) ![]u8 {
    var pathz_buf: [4096]u8 = undefined;
    if (path.len >= pathz_buf.len) return error.PathTooLong;
    @memcpy(pathz_buf[0..path.len], path);
    pathz_buf[path.len] = 0;
    const pathz: [*:0]const u8 = @ptrCast(&pathz_buf);

    const fd_us = linux.open(pathz, .{ .ACCMODE = .RDONLY }, 0);
    const fd_s: isize = @bitCast(fd_us);
    if (fd_s < 0) return error.OpenFailed;
    const fd: i32 = @intCast(fd_s);
    defer _ = linux.close(fd);

    var buf: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    var tmp: [8192]u8 = undefined;
    while (true) {
        const n = linux.read(fd, &tmp, tmp.len);
        const r: isize = @bitCast(n);
        if (r < 0) return error.ReadFailed;
        if (r == 0) break;
        try buf.appendSlice(alloc, tmp[0..@intCast(r)]);
    }
    return buf.items;
}

fn list_notes(alloc: std.mem.Allocator) !std.ArrayListUnmanaged(Note) {
    var notes: std.ArrayListUnmanaged(Note) = .{ .items = &.{}, .capacity = 0 };

    const dirz: [*:0]const u8 = NotesDir;
    const fd_us = linux.open(dirz, .{ .ACCMODE = .RDONLY, .DIRECTORY = true }, 0);
    const fd_s: isize = @bitCast(fd_us);
    if (fd_s < 0) return notes;
    const fd: i32 = @intCast(fd_s);
    defer _ = linux.close(fd);

    var dbuf: [8192]u8 = undefined;
    while (true) {
        const n = linux.getdents64(fd, &dbuf, dbuf.len);
        const r: isize = @bitCast(n);
        if (r < 0) return error.ReadDirFailed;
        if (r == 0) break;
        var off: usize = 0;
        while (off < @as(usize, @intCast(r))) {
            const dent: *align(1) linux.dirent64 = @ptrCast(&dbuf[off]);
            const name_ptr: [*:0]u8 = @ptrCast(&dent.name);
            const name = std.mem.span(name_ptr);
            off += dent.reclen;

            if (!is_daily_note(name)) continue;

            var path_buf: [4096]u8 = undefined;
            const path = try std.fmt.bufPrint(&path_buf, "{s}/{s}", .{ NotesDir, name });
            const content = read_file(alloc, path) catch continue;
            const name_copy = try alloc.dupe(u8, name);
            try notes.append(alloc, .{ .name = name_copy, .content = content });
        }
    }
    return notes;
}

fn is_daily_note(name: []const u8) bool {
    // YYYY-MM-DD.md
    if (name.len != 13) return false;
    if (!std.mem.endsWith(u8, name, ".md")) return false;
    const stem = name[0..10];
    if (stem[4] != '-' or stem[7] != '-') return false;
    for ([_]usize{ 0, 1, 2, 3, 5, 6, 8, 9 }) |i| {
        if (stem[i] < '0' or stem[i] > '9') return false;
    }
    return true;
}

fn contains_ci(haystack: []const u8, needle: []const u8) bool {
    if (needle.len == 0) return true;
    if (needle.len > haystack.len) return false;
    var i: usize = 0;
    while (i + needle.len <= haystack.len) : (i += 1) {
        var match = true;
        var j: usize = 0;
        while (j < needle.len) : (j += 1) {
            if (lower(haystack[i + j]) != lower(needle[j])) {
                match = false;
                break;
            }
        }
        if (match) return true;
    }
    return false;
}

fn lower(c: u8) u8 {
    if (c >= 'A' and c <= 'Z') return c + 32;
    return c;
}

fn check_alignment(alloc: std.mem.Allocator, notes: []const Note) ![]AlignmentPoint {
    var points = try alloc.alloc(AlignmentPoint, 4);

    points[0] = checkPoint(notes, "Graveyard Permanence", "Deleted concepts must remain recorded, never erased.", &.{ "graveyard", "never erase", "permanent" });
    points[1] = checkPoint(notes, "Trust Priority", "Trust is prioritized in decision-making.", &.{ "trust", "priority", "prioritize" });
    points[2] = checkPoint(notes, "Genesis Seal Presence", "The genesis seal anchors the origin.", &.{ "genesis", "seal" });
    points[3] = checkPoint(notes, "Intent Documentation", "Architectural intent must be documented.", &.{ "intent", "document", "rationale" });

    return points;
}

fn checkPoint(notes: []const Note, name: []const u8, desc: []const u8, keywords: []const []const u8) AlignmentPoint {
    for (notes) |note| {
        var all = true;
        for (keywords) |kw| {
            if (!contains_ci(note.content, kw)) {
                all = false;
                break;
            }
        }
        if (all) {
            return .{ .name = name, .description = desc, .present = true, .detail = note.name };
        }
    }
    // partial: any keyword
    for (notes) |note| {
        for (keywords) |kw| {
            if (contains_ci(note.content, kw)) {
                return .{ .name = name, .description = desc, .present = false, .detail = note.name };
            }
        }
    }
    return .{ .name = name, .description = desc, .present = false, .detail = "" };
}

fn generate_report(alloc: std.mem.Allocator, notes: []const Note, points: []const AlignmentPoint) ![]u8 {
    var buf: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    const w = buf.writer(alloc);

    try w.writeAll("# Architectural Alignment Report\n\n");
    try w.print("Daily notes scanned: {d}\n\n", .{notes.len});

    var aligned: usize = 0;
    for (points) |p| {
        if (p.present) aligned += 1;
    }
    try w.print("Alignment score: {d}/{d}\n\n", .{ aligned, points.len });

    try w.writeAll("## Alignment Points\n\n");
    for (points) |p| {
        const mark = if (p.present) "[x]" else "[ ]";
        try w.print("- {s} **{s}**\n", .{ mark, p.name });
        try w.print("  - {s}\n", .{p.description});
        if (p.present) {
            try w.print("  - Status: ALIGNED (found in `{s}`)\n", .{p.detail});
        } else if (p.detail.len > 0) {
            try w.print("  - Status: PARTIAL (referenced in `{s}` but incomplete)\n", .{p.detail});
        } else {
            try w.writeAll("  - Status: MISSING (no reference found)\n");
        }
        try w.writeAll("\n");
    }

    try w.writeAll("## Summary\n\n");
    if (aligned == points.len) {
        try w.writeAll("All alignment points are satisfied. Architecture is in full alignment.\n");
    } else {
        try w.print("{d} alignment point(s) require attention.\n", .{points.len - aligned});
    }

    return buf.items;
}

pub fn main(init: std.process.Init) !void {
    const alloc = init.arena;

    var notes = try list_notes(alloc);
    const points = try check_alignment(alloc, notes.items);
    const report = try generate_report(alloc, notes.items, points);

    write_all(1, report);
}