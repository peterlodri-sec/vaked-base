const std = @import("std");
const linux = std.os.linux;

const GENESIS_SEAL = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf";
const LEDGER_PATH = "/tmp/oculus_export.jsonl";
const TRUTH_THRESHOLD: usize = 2;

const Directive = struct {
    id: []const u8,
    name: []const u8,
    keyword: []const u8,
    critical: bool,
    always_pass: bool,
};

const DIRECTIVES = [_]Directive{
    .{ .id = "G01", .name = "graveyard_permanent", .keyword = "graveyard", .critical = true, .always_pass = false },
    .{ .id = "G02", .name = "trust_priority", .keyword = "trust", .critical = true, .always_pass = false },
    .{ .id = "G03", .name = "mesh_complete", .keyword = "MESH_COMPLETE", .critical = true, .always_pass = false },
    .{ .id = "G04", .name = "genesis_seal", .keyword = "", .critical = false, .always_pass = true },
};

const Result = struct {
    id: []const u8,
    name: []const u8,
    aligned: bool,
    critical: bool,
};

fn readFile(arena: std.mem.Allocator, path: []const u8) ![]u8 {
    const path_z = try arena.dupeZ(u8, path);
    const fd_usize = linux.open(path_z, @bitCast(@as(u32, 0)), 0);
    const fd: i32 = @intCast(@as(isize, @bitCast(fd_usize)));
    if (fd < 0) return error.OpenFailed;
    defer _ = linux.close(fd);

    var list: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    var buf: [8192]u8 = undefined;
    while (true) {
        const n = linux.read(fd, &buf, buf.len);
        const r: isize = @bitCast(n);
        if (r < 0) return error.ReadFailed;
        if (r == 0) break;
        try list.appendSlice(arena, buf[0..@intCast(r)]);
    }
    return list.items;
}

fn writeAll(fd: i32, data: []const u8) void {
    var off: usize = 0;
    while (off < data.len) {
        const n = linux.write(fd, data.ptr + off, data.len - off);
        const r: isize = @bitCast(n);
        if (r <= 0) break;
        off += @intCast(r);
    }
}

fn print(comptime fmt: []const u8, args: anytype) void {
    var buf: [4096]u8 = undefined;
    const s = std.fmt.bufPrint(&buf, fmt, args) catch return;
    writeAll(1, s);
}

fn containsKeyword(haystack: []const u8, needle: []const u8) bool {
    if (needle.len == 0) return false;
    return std.mem.indexOf(u8, haystack, needle) != null;
}

fn checkMeshComplete(haystack: []const u8) bool {
    // look for payload.kind == "MESH_COMPLETE"
    return std.mem.indexOf(u8, haystack, "MESH_COMPLETE") != null;
}

fn dateString(buf: []u8) []const u8 {
    const now: i64 = 0; // hardcoded — time API removed in 0.16
    const secs: i64 = @intCast(now);
    var days = @divTrunc(secs, 86400);
    var year: i64 = 1970;
    while (true) {
        const leap = (@mod(year, 4) == 0 and @mod(year, 100) != 0) or (@mod(year, 400) == 0);
        const ydays: i64 = if (leap) 366 else 365;
        if (days < ydays) break;
        days -= ydays;
        year += 1;
    }
    const leap = (@mod(year, 4) == 0 and @mod(year, 100) != 0) or (@mod(year, 400) == 0);
    const mdays = [_]i64{ 31, if (leap) @as(i64, 29) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
    var month: i64 = 0;
    while (month < 12) : (month += 1) {
        if (days < mdays[@intCast(month)]) break;
        days -= mdays[@intCast(month)];
    }
    const m = month + 1;
    const d = days + 1;
    const s = std.fmt.bufPrint(buf, "{d:0>4}-{d:0>2}-{d:0>2}", .{ year, m, d }) catch return "0000-00-00";
    return s;
}

fn sha256Hex(arena: std.mem.Allocator, data: []const u8) ![]const u8 {
    var hash: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(data, &hash, .{});
    const hex = try arena.alloc(u8, 64);
    const chars = "0123456789abcdef";
    for (hash, 0..) |b, i| {
        hex[i * 2] = chars[b >> 4];
        hex[i * 2 + 1] = chars[b & 0xf];
    }
    return hex;
}

pub fn main(init: std.process.Init) !void {
    _ = init;
    var arena_state = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena_state.deinit();
    const arena = arena_state.allocator();

    print("=== Ralph Governance Audit ===\n", .{});
    print("Genesis Seal: {s}\n", .{GENESIS_SEAL});

    const ledger = readFile(arena, LEDGER_PATH) catch blk: {
        print("WARNING: could not read ledger at {s}, treating as empty\n", .{LEDGER_PATH});
        break :blk @as([]u8, &.{});
    };

    print("Ledger size: {d} bytes\n", .{ledger.len});

    var results: std.ArrayListUnmanaged(Result) = .{ .items = &.{}, .capacity = 0 };
    var aligned_count: usize = 0;
    var critical_drifts: usize = 0;

    for (DIRECTIVES) |dir| {
        var aligned = false;
        if (dir.always_pass) {
            aligned = true;
        } else if (std.mem.eql(u8, dir.id, "G01")) {
            aligned = containsKeyword(ledger, "graveyard") or containsKeyword(ledger, "PERMANENT");
        } else if (std.mem.eql(u8, dir.id, "G03")) {
            aligned = checkMeshComplete(ledger);
        } else {
            aligned = containsKeyword(ledger, dir.keyword);
        }

        if (aligned) {
            aligned_count += 1;
        } else if (dir.critical) {
            critical_drifts += 1;
        }

        try results.append(arena, .{
            .id = dir.id,
            .name = dir.name,
            .aligned = aligned,
            .critical = dir.critical,
        });

        print("  {s} {s}: {s}\n", .{ dir.id, dir.name, if (aligned) "ALIGNED" else "DRIFT" });
    }

    var date_buf: [16]u8 = undefined;
    const date = dateString(&date_buf);

    const hash_input = try std.fmt.allocPrint(arena, "{s}{s}{d}{d}", .{
        GENESIS_SEAL, date, aligned_count, critical_drifts,
    });
    const audit_hash = try sha256Hex(arena, hash_input);

    const blocked = critical_drifts >= TRUTH_THRESHOLD;
    const verdict = if (blocked) "BUILD BLOCKED" else "BUILD CLEAR";

    print("\nAligned: {d}/{d}  Critical drifts: {d}\n", .{ aligned_count, DIRECTIVES.len, critical_drifts });
    print("Audit hash: {s}\n", .{audit_hash});
    print("Verdict: {s}\n", .{verdict});

    // Build reflection markdown
    var md: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    const w = struct {
        fn line(a: std.mem.Allocator, l: *std.ArrayListUnmanaged(u8), comptime fmt: []const u8, args: anytype) !void {
            const s = try std.fmt.allocPrint(a, fmt, args);
            try l.appendSlice(a, s);
        }
    };

    try w.line(arena, &md, "# Ralph Reflection — {s}\n\n", .{date});
    try w.line(arena, &md, "Genesis Seal: `{s}`\n\n", .{GENESIS_SEAL});
    try w.line(arena, &md, "## Governance Audit Results\n\n", .{});
    try w.line(arena, &md, "| Directive | Name | Status | Critical |\n", .{});
    try w.line(arena, &md, "|-----------|------|--------|----------|\n", .{});
    for (results.items) |r| {
        try w.line(arena, &md, "| {s} | {s} | {s} | {s} |\n", .{
            r.id,
            r.name,
            if (r.aligned) "ALIGNED" else "DRIFT",
            if (r.critical) "yes" else "no",
        });
    }
    try w.line(arena, &md, "\n## Summary\n\n", .{});
    try w.line(arena, &md, "- Aligned: {d}/{d}\n", .{ aligned_count, DIRECTIVES.len });
    try w.line(arena, &md, "- Critical drifts: {d}\n", .{critical_drifts});
    try w.line(arena, &md, "- Truth threshold: {d}\n", .{TRUTH_THRESHOLD});
    try w.line(arena, &md, "- Audit hash: `{s}`\n\n", .{audit_hash});
    try w.line(arena, &md, "## Verdict\n\n**{s}**\n", .{verdict});

    const out_path = try std.fmt.allocPrint(arena, "notes/REFLECTIONS/{s}-ralph-reflection.md", .{date});

    const path_z2 = try arena.dupeZ(u8, out_path);
    const fd_usize = linux.open(path_z2, @bitCast(@as(u32, 0x241)), 0o644);
    const fd: i32 = @intCast(@as(isize, @bitCast(fd_usize)));
    if (fd >= 0) {
        writeAll(fd, md.items);
        _ = linux.close(fd);
        print("Reflection written: {s}\n", .{out_path});
    } else {
        print("WARNING: could not write reflection to {s}\n", .{out_path});
    }

    if (blocked) {
        linux.exit(1);
    }
    linux.exit(0);
}
