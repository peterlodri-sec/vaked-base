//! `Diagnostic` — a source-mapped 0011 type-system finding. Port of the Python
//! `vakedc.check.Diagnostic` dataclass (fields + `as_dict` shape).
//!
//! The checker (`vaked-check`) produces a list of these, sorted by
//! `(file, byteStart, byteEnd, code)` — exactly the Python order. The CLI emits
//! them as the `{"diagnostics": [...]}` canonical-JSON doc via
//! `diagnosticsDocToCanonical`, which serializes through the existing pretty
//! writer (`indent=2`, ALL keys sorted, trailing `\n`) so the bytes match
//! Python's `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True) + "\n"`.

const std = @import("std");
const Value = @import("value.zig").Value;
const json_canon = @import("json_canon.zig");

/// Mirrors `vakedc.check.Diagnostic`. `related` is a list of strings (the
/// corpus only ever produces `[]`, but we model the full shape for parity).
pub const Diagnostic = struct {
    code: []const u8,
    message: []const u8,
    file: []const u8,
    line: usize,
    col: usize,
    byteStart: usize,
    byteEnd: usize,
    decl: []const u8, // "<kind> <name>" of the enclosing declaration
    severity: []const u8 = "error",
    related: []const []const u8 = &.{},

    /// `as_dict` equivalent — build the `Value.object` for one diagnostic.
    /// Field order here is irrelevant: the pretty writer sorts ALL keys.
    pub fn toValue(self: Diagnostic, alloc: std.mem.Allocator) !Value {
        var related_vals: std.ArrayList(Value) = .empty;
        for (self.related) |r| try related_vals.append(alloc, .{ .string = r });

        const span_fields = try alloc.dupe(Value.Field, &.{
            .{ .key = "byteStart", .value = .{ .int = @intCast(self.byteStart) } },
            .{ .key = "byteEnd", .value = .{ .int = @intCast(self.byteEnd) } },
            .{ .key = "line", .value = .{ .int = @intCast(self.line) } },
            .{ .key = "col", .value = .{ .int = @intCast(self.col) } },
        });

        const fields = try alloc.dupe(Value.Field, &.{
            .{ .key = "code", .value = .{ .string = self.code } },
            .{ .key = "severity", .value = .{ .string = self.severity } },
            .{ .key = "message", .value = .{ .string = self.message } },
            .{ .key = "file", .value = .{ .string = self.file } },
            .{ .key = "decl", .value = .{ .string = self.decl } },
            .{ .key = "span", .value = .{ .object = span_fields } },
            .{ .key = "related", .value = .{ .array = try related_vals.toOwnedSlice(alloc) } },
        });
        return .{ .object = fields };
    }
};

/// Build the `{"diagnostics": [...]}` doc and serialize it canonically
/// (indent=2, sorted keys, trailing newline). Mirrors
/// `vakedc.__main__._diagnostics_json`. Caller owns the returned bytes.
pub fn diagnosticsDocToCanonical(alloc: std.mem.Allocator, diags: []const Diagnostic) ![]u8 {
    var arr: std.ArrayList(Value) = .empty;
    for (diags) |d| try arr.append(alloc, try d.toValue(alloc));
    const doc = Value{ .object = &.{
        .{ .key = "diagnostics", .value = .{ .array = try arr.toOwnedSlice(alloc) } },
    } };
    return json_canon.valueDocToPretty(alloc, doc);
}

// --------------------------------------------------------------------------- //
// tests
// --------------------------------------------------------------------------- //

test "empty diagnostics list matches Python's empty-array shape" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();

    const out = try diagnosticsDocToCanonical(a, &.{});
    // Python: json.dumps({"diagnostics": []}, indent=2, sort_keys=True) + "\n"
    const expected =
        "{\n" ++
        "  \"diagnostics\": []\n" ++
        "}\n";
    try std.testing.expectEqualStrings(expected, out);
}

test "single diagnostic — keys sorted, span nested, related empty" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();

    const diags = [_]Diagnostic{.{
        .code = "E-CONSTRAINT-RANGE",
        .message = "field `fps`: value 0 violates `> 0`",
        .file = "x.vaked",
        .line = 39,
        .col = 9,
        .byteStart = 1314,
        .byteEnd = 1315,
        .decl = "stream telemetry",
    }};
    const out = try diagnosticsDocToCanonical(a, &diags);
    const expected =
        "{\n" ++
        "  \"diagnostics\": [\n" ++
        "    {\n" ++
        "      \"code\": \"E-CONSTRAINT-RANGE\",\n" ++
        "      \"decl\": \"stream telemetry\",\n" ++
        "      \"file\": \"x.vaked\",\n" ++
        "      \"message\": \"field `fps`: value 0 violates `> 0`\",\n" ++
        "      \"related\": [],\n" ++
        "      \"severity\": \"error\",\n" ++
        "      \"span\": {\n" ++
        "        \"byteEnd\": 1315,\n" ++
        "        \"byteStart\": 1314,\n" ++
        "        \"col\": 9,\n" ++
        "        \"line\": 39\n" ++
        "      }\n" ++
        "    }\n" ++
        "  ]\n" ++
        "}\n";
    try std.testing.expectEqualStrings(expected, out);
}
