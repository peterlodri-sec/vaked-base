const std = @import("std");

const GENESIS_SEAL: u32 = 0x7c242080;

const Directive = struct {
    id: []const u8,
    description: []const u8,
    key: []const u8,
};

const DIRECTIVES = [_]Directive{
    .{ .id = "D1", .description = "Preserve provenance of all ledger entries", .key = "provenance" },
    .{ .id = "D2", .description = "Maintain immutability of sealed records", .key = "immutable" },
    .{ .id = "D3", .description = "Ensure transparency of governance actions", .key = "transparency" },
    .{ .id = "D4", .description = "Honor the Genesis Seal binding", .key = "genesis_seal" },
};

const AuditResult = struct {
    directive: Directive,
    pass: bool,
    note: []const u8,
};

fn checkDirective(
    directive: Directive,
    ledger: std.json.Value,
) AuditResult {
    if (ledger != .object) {
        return .{ .directive = directive, .pass = false, .note = "ledger is not an object" };
    }
    const obj = ledger.object;

    if (std.mem.eql(u8, directive.key, "genesis_seal")) {
        const seal = obj.get("genesis_seal") orelse {
            return .{ .directive = directive, .pass = false, .note = "missing genesis_seal" };
        };
        switch (seal) {
            .integer => |i| {
                if (@as(u64, @intCast(i)) == GENESIS_SEAL) {
                    return .{ .directive = directive, .pass = true, .note = "seal verified" };
                }
                return .{ .directive = directive, .pass = false, .note = "seal mismatch" };
            },
            .string => |s| {
                const parsed = std.fmt.parseInt(u32, std.mem.trimLeft(u8, s, "0x"), 16) catch {
                    return .{ .directive = directive, .pass = false, .note = "seal unparseable" };
                };
                if (parsed == GENESIS_SEAL) {
                    return .{ .directive = directive, .pass = true, .note = "seal verified" };
                }
                return .{ .directive = directive, .pass = false, .note = "seal mismatch" };
            },
            else => return .{ .directive = directive, .pass = false, .note = "seal wrong type" },
        }
    }

    const val = obj.get(directive.key) orelse {
        return .{ .directive = directive, .pass = false, .note = "key absent" };
    };
    switch (val) {
        .bool => |b| {
            if (b) return .{ .directive = directive, .pass = true, .note = "affirmed" };
            return .{ .directive = directive, .pass = false, .note = "negated" };
        },
        else => return .{ .directive = directive, .pass = true, .note = "present" },
    }
}

fn writeReflection(
    allocator: std.mem.Allocator,
    results: []const AuditResult,
    drift: usize,
) !void {
    const now = std.time.timestamp();
    const day = @divFloor(now, 86400);

    const filename = try std.fmt.allocPrint(allocator, "reflection-{d}.md", .{day});
    defer allocator.free(filename);

    var file = try std.fs.cwd().createFile(filename, .{});
    defer file.close();

    var buf: [4096]u8 = undefined;
    var fw = file.writer(&buf);
    const w = &fw.interface;

    try w.print("# Ralph Daily Reflection\n\n", .{});
    try w.print("Genesis Seal: 0x{x:0>8}\n", .{GENESIS_SEAL});
    try w.print("Timestamp: {d}\n\n", .{now});
    try w.print("## Directive Audit\n\n", .{});

    for (results) |r| {
        const mark = if (r.pass) "PASS" else "DRIFT";
        try w.print("- [{s}] {s}: {s} ({s})\n", .{ mark, r.directive.id, r.directive.description, r.note });
    }

    try w.print("\n## Summary\n\n", .{});
    try w.print("Drift count: {d}\n", .{drift});
    if (drift >= 2) {
        try w.print("Status: CRITICAL — governance integrity compromised\n", .{});
    } else if (drift == 1) {
        try w.print("Status: WARNING — minor drift detected\n", .{});
    } else {
        try w.print("Status: NOMINAL — all directives honored\n", .{});
    }

    try w.flush();
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const args = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, args);

    if (args.len < 2) {
        std.debug.print("usage: ralph-audit <ledger.json>\n", .{});
        std.process.exit(2);
    }

    const path = args[1];
    const data = std.fs.cwd().readFileAlloc(allocator, path, 16 * 1024 * 1024) catch |err| {
        std.debug.print("error reading {s}: {s}\n", .{ path, @errorName(err) });
        std.process.exit(2);
    };
    defer allocator.free(data);

    var parsed = std.json.parseFromSlice(std.json.Value, allocator, data, .{}) catch |err| {
        std.debug.print("error parsing ledger: {s}\n", .{@errorName(err)});
        std.process.exit(2);
    };
    defer parsed.deinit();

    var results: [DIRECTIVES.len]AuditResult = undefined;
    var drift: usize = 0;

    for (DIRECTIV
