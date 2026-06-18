
const std = @import("std");
const linux = std.os.linux;

const GENESIS_SEAL: u32 = 0x7c242080;

const Directive = struct {
    name: []const u8,
    fulfilled: bool,
};

fn readFile(a: std.mem.Allocator, path: []const u8) ![]u8 {
    const zpath = try a.dupeZ(u8, path);
    const open_rc = linux.open(zpath.ptr, @bitCast(@as(u32, 0)), 0);
    const fd: i32 = @intCast(@as(isize, @bitCast(open_rc)));
    if (fd < 0) return error.OpenFailed;
    defer _ = linux.close(fd);

    var list: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    var buf: [4096]u8 = undefined;
    while (true) {
        const n = linux.read(fd, &buf, buf.len);
        const got: isize = @bitCast(n);
        if (got <= 0) break;
        try list.appendSlice(a, buf[0..@intCast(got)]);
    }
    return list.items;
}

fn writeFile(a: std.mem.Allocator, path: []const u8, data: []const u8) !void {
    const zpath = try a.dupeZ(u8, path);
    const open_rc = linux.open(zpath.ptr, @bitCast(@as(u32, 0x241)), 0o644);
    const fd: i32 = @intCast(@as(isize, @bitCast(open_rc)));
    if (fd < 0) return error.OpenFailed;
    defer _ = linux.close(fd);

    var off: usize = 0;
    while (off < data.len) {
        const w = linux.write(fd, data.ptr + off, data.len - off);
        const wn: isize = @bitCast(w);
        if (wn <= 0) break;
        off += @intCast(wn);
    }
}

fn ledgerContains(ledger: []const u8, name: []const u8) bool {
    // crude JSON scan: find the directive name, then check for "fulfilled":true after it
    var idx: usize = 0;
    while (std.mem.indexOfPos(u8, ledger, idx, name)) |pos| {
        const tail = ledger[pos..];
        if (std.mem.indexOf(u8, tail, "\"fulfilled\"")) |fpos| {
            const seg = tail[fpos..];
            if (std.mem.indexOf(u8, seg, "true")) |tp| {
                if (std.mem.indexOf(u8, seg, "false")) |fp| {
                    return tp < fp;
                }
                return true;
            }
            return false;
        }
        idx = pos + name.len;
    }
    return false;
}

pub fn main(init: std.process.Init) !void {
    const a = init.arena.allocator();
    const argv = try init.minimal.args.toSlice(a);

    const date = if (argv.len > 1) argv[1] else "2024-01-01";

    const notes_path = try std.fmt.allocPrint(a, "notes/{s}.md", .{date});
    const notes = readFile(a, notes_path) catch |e| {
        std.log.err("failed to read notes {s}: {s}", .{ notes_path, @errorName(e) });
        return e;
    };
    std.log.info("read {d} bytes from {s}", .{ notes.len, notes_path });

    const ledger = readFile(a, "ledger.json") catch |e| {
        std.log.err("failed to read ledger.json: {s}", .{@errorName(e)});
        return e;
    };

    const directive_names = [_][]const u8{
        "observe",
        "compare",
        "reflect",
        "seal",
    };

    var directives: std.ArrayListUnmanaged(Directive) = .{ .items = &.{}, .capacity = 0 };
    for (directive_names) |name| {
        try directives.append(a, .{
            .name = name,
            .fulfilled = ledgerContains(ledger, name),
        });
    }

    var out: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    try out.appendSlice(a, "# Reflection\n\n");
    try out.appendSlice(a, try std.fmt.allocPrint(a, "Date: {s}\n\n", .{date}));
    try out.appendSlice(a, try std.fmt.allocPrint(a, "Genesis Seal: 0x{x:0>8}\n\n", .{GENESIS_SEAL}));
    try out.appendSlice(a, "## Directives\n\n");

    var fulfilled_count: usize = 0;
    for (directives.items) |d| {
        const mark = if (d.fulfilled) "[x]" else "[ ]";
        if (d.fulfilled) fulfilled_count += 1;
        try out.appendSlice(a, try std.fmt.allocPrint(a, "- {s} {s}\n", .{ mark, d.name }));
    }

    try out.appendSlice(a, try std.fmt.allocPrint(
        a,
        "\n## Summary\n\n{d}/{d} directives fulfilled.\n",
        .{ fulfilled_count, directives.items.len },
    ));

    if (fulfilled_count == directives.items.len) {
        try out.appendSlice(a, try std.fmt.allocPrint(
            a,
            "\nSeal verified: 0x{x:0>8}\n",
            .{GENESIS_SEAL},
        ));
    } else {
    }

    const refl_path = try std.fmt.allocPrint(a, "notes/{s}-reflection.md", .{date});
    writeFile(a, refl_path, out.items) catch |e| {
        std.log.err("failed to write reflection: {s}", .{@errorName(e)});
        return e;
    };

    std.log.info("wrote reflection to {s} ({d}/{d})", .{ refl_path, fulfilled_count, directives.items.len });
}

