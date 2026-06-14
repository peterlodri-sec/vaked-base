//! Canonical JSON serialization — the artifact contract. Hand-rolled (no
//! `std.json`) for exact byte control. Two modes, both matching the existing
//! Python output byte-for-byte:
//!
//!  * **graph mode** (`graphToCanonical`) — compact `(",",":")`, fixed key order
//!    per object (id,kind,name,labels,props,provenance / from,to,label,props /
//!    file,decl,span / byteStart,byteEnd,line,col), props object keys sorted
//!    recursively, nodes sorted by id, edges by (from,label,to,propsKey),
//!    trailing `\n`. Mirrors `vakedc/emit.py:to_canonical_json`.
//!  * **diagnostics mode** (`valueToPretty`) — `indent=2`, ALL object keys
//!    sorted, trailing `\n` added by the caller. Mirrors
//!    `vakedc/__main__.py:_diagnostics_json`.
//!
//! Strings use UTF-8 passthrough (`ensure_ascii=False`): only `"`, `\`, and
//! control chars (< 0x20) are escaped; bytes >= 0x80 pass through unchanged.

const std = @import("std");
const Value = @import("value.zig").Value;
const graph_mod = @import("graph.zig");
const Graph = graph_mod.Graph;
const GraphNode = graph_mod.GraphNode;
const GraphEdge = graph_mod.GraphEdge;
const Provenance = @import("provenance.zig").Provenance;

const Buf = std.ArrayList(u8);

// --------------------------------------------------------------------------- //
// strings + numbers
// --------------------------------------------------------------------------- //

fn writeString(buf: *Buf, alloc: std.mem.Allocator, s: []const u8) !void {
    try buf.append(alloc, '"');
    for (s) |c| {
        switch (c) {
            '"' => try buf.appendSlice(alloc, "\\\""),
            '\\' => try buf.appendSlice(alloc, "\\\\"),
            '\n' => try buf.appendSlice(alloc, "\\n"),
            '\r' => try buf.appendSlice(alloc, "\\r"),
            '\t' => try buf.appendSlice(alloc, "\\t"),
            0x08 => try buf.appendSlice(alloc, "\\b"),
            0x0c => try buf.appendSlice(alloc, "\\f"),
            else => {
                if (c < 0x20) {
                    var tmp: [6]u8 = undefined;
                    const esc = try std.fmt.bufPrint(&tmp, "\\u{x:0>4}", .{c});
                    try buf.appendSlice(alloc, esc);
                } else {
                    try buf.append(alloc, c); // ASCII >= 0x20 and UTF-8 continuation/lead bytes
                }
            },
        }
    }
    try buf.append(alloc, '"');
}

fn writeInt(buf: *Buf, alloc: std.mem.Allocator, n: i64) !void {
    var tmp: [24]u8 = undefined;
    try buf.appendSlice(alloc, try std.fmt.bufPrint(&tmp, "{d}", .{n}));
}

/// Float repr targeting Python's `json.dumps` (shortest round-trip; integer
/// values keep a `.0`). Validated against the corpus in Task 0.5.
fn writeFloat(buf: *Buf, alloc: std.mem.Allocator, f: f64) !void {
    var tmp: [64]u8 = undefined;
    const s = try std.fmt.bufPrint(&tmp, "{d}", .{f});
    try buf.appendSlice(alloc, s);
    // Python renders integer-valued floats with a trailing ".0"; Zig's {d} omits it.
    if (std.mem.indexOfAny(u8, s, ".eEnN") == null) try buf.appendSlice(alloc, ".0");
}

// --------------------------------------------------------------------------- //
// Value — compact (sorted object keys)
// --------------------------------------------------------------------------- //

fn lessField(_: void, a: Value.Field, b: Value.Field) bool {
    return std.mem.lessThan(u8, a.key, b.key);
}

fn sortedFields(alloc: std.mem.Allocator, fields: []const Value.Field) ![]Value.Field {
    const out = try alloc.dupe(Value.Field, fields);
    std.mem.sort(Value.Field, out, {}, lessField);
    return out;
}

fn writeValueCompact(buf: *Buf, alloc: std.mem.Allocator, v: Value) !void {
    switch (v) {
        .null => try buf.appendSlice(alloc, "null"),
        .bool => |b| try buf.appendSlice(alloc, if (b) "true" else "false"),
        .int => |n| try writeInt(buf, alloc, n),
        .float => |f| try writeFloat(buf, alloc, f),
        .string => |s| try writeString(buf, alloc, s),
        .array => |items| {
            try buf.append(alloc, '[');
            for (items, 0..) |item, i| {
                if (i != 0) try buf.append(alloc, ',');
                try writeValueCompact(buf, alloc, item);
            }
            try buf.append(alloc, ']');
        },
        .object => |fields| {
            const fs = try sortedFields(alloc, fields);
            defer alloc.free(fs);
            try buf.append(alloc, '{');
            for (fs, 0..) |f, i| {
                if (i != 0) try buf.append(alloc, ',');
                try writeString(buf, alloc, f.key);
                try buf.append(alloc, ':');
                try writeValueCompact(buf, alloc, f.value);
            }
            try buf.append(alloc, '}');
        },
    }
}

/// Compact canonical JSON of a single Value (sorted object keys). Used as the
/// edge props tiebreak key. Caller owns the returned bytes.
pub fn stablePropsKey(alloc: std.mem.Allocator, v: Value) ![]u8 {
    var buf: Buf = .empty;
    errdefer buf.deinit(alloc);
    try writeValueCompact(&buf, alloc, v);
    return buf.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// Value — pretty (indent=2, ALL keys sorted) — diagnostics mode
// --------------------------------------------------------------------------- //

fn indent(buf: *Buf, alloc: std.mem.Allocator, level: usize) !void {
    var i: usize = 0;
    while (i < level * 2) : (i += 1) try buf.append(alloc, ' ');
}

pub fn writeValuePretty(buf: *Buf, alloc: std.mem.Allocator, v: Value, level: usize) !void {
    switch (v) {
        .null, .bool, .int, .float, .string => try writeValueCompact(buf, alloc, v),
        .array => |items| {
            if (items.len == 0) {
                try buf.appendSlice(alloc, "[]");
                return;
            }
            try buf.appendSlice(alloc, "[\n");
            for (items, 0..) |item, i| {
                try indent(buf, alloc, level + 1);
                try writeValuePretty(buf, alloc, item, level + 1);
                if (i != items.len - 1) try buf.append(alloc, ',');
                try buf.append(alloc, '\n');
            }
            try indent(buf, alloc, level);
            try buf.append(alloc, ']');
        },
        .object => |fields| {
            if (fields.len == 0) {
                try buf.appendSlice(alloc, "{}");
                return;
            }
            const fs = try sortedFields(alloc, fields);
            defer alloc.free(fs);
            try buf.appendSlice(alloc, "{\n");
            for (fs, 0..) |f, i| {
                try indent(buf, alloc, level + 1);
                try writeString(buf, alloc, f.key);
                try buf.appendSlice(alloc, ": ");
                try writeValuePretty(buf, alloc, f.value, level + 1);
                if (i != fs.len - 1) try buf.append(alloc, ',');
                try buf.append(alloc, '\n');
            }
            try indent(buf, alloc, level);
            try buf.append(alloc, '}');
        },
    }
}

/// Pretty doc + trailing newline (the diagnostics.json shape). Caller owns bytes.
pub fn valueDocToPretty(alloc: std.mem.Allocator, doc: Value) ![]u8 {
    var buf: Buf = .empty;
    errdefer buf.deinit(alloc);
    try writeValuePretty(&buf, alloc, doc, 0);
    try buf.append(alloc, '\n');
    return buf.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// graph mode (compact, fixed key order)
// --------------------------------------------------------------------------- //

fn writeStringArray(buf: *Buf, alloc: std.mem.Allocator, items: []const []const u8) !void {
    try buf.append(alloc, '[');
    for (items, 0..) |s, i| {
        if (i != 0) try buf.append(alloc, ',');
        try writeString(buf, alloc, s);
    }
    try buf.append(alloc, ']');
}

fn writeProvenance(buf: *Buf, alloc: std.mem.Allocator, prov: ?Provenance) !void {
    if (prov == null) {
        try buf.appendSlice(alloc, "null");
        return;
    }
    const p = prov.?;
    try buf.appendSlice(alloc, "{\"file\":");
    try writeString(buf, alloc, p.file);
    try buf.appendSlice(alloc, ",\"decl\":");
    try writeString(buf, alloc, p.decl);
    try buf.appendSlice(alloc, ",\"span\":{\"byteStart\":");
    try writeInt(buf, alloc, @intCast(p.span.byteStart));
    try buf.appendSlice(alloc, ",\"byteEnd\":");
    try writeInt(buf, alloc, @intCast(p.span.byteEnd));
    try buf.appendSlice(alloc, ",\"line\":");
    try writeInt(buf, alloc, @intCast(p.span.line));
    try buf.appendSlice(alloc, ",\"col\":");
    try writeInt(buf, alloc, @intCast(p.span.col));
    try buf.appendSlice(alloc, "}}");
}

fn writeNode(buf: *Buf, alloc: std.mem.Allocator, n: GraphNode) !void {
    try buf.appendSlice(alloc, "{\"id\":");
    try writeString(buf, alloc, n.id);
    try buf.appendSlice(alloc, ",\"kind\":");
    try writeString(buf, alloc, n.kind);
    try buf.appendSlice(alloc, ",\"name\":");
    try writeString(buf, alloc, n.name);
    try buf.appendSlice(alloc, ",\"labels\":");
    try writeStringArray(buf, alloc, n.labels);
    try buf.appendSlice(alloc, ",\"props\":");
    try writeValueCompact(buf, alloc, n.props);
    try buf.appendSlice(alloc, ",\"provenance\":");
    try writeProvenance(buf, alloc, n.provenance);
    try buf.append(alloc, '}');
}

/// An edge paired with its precomputed canonical props key, so the canonical
/// sort (from, label, to, propsKey) matches Python's `edges_sorted` tiebreak.
const KeyedEdge = struct { e: GraphEdge, key: []const u8 };

fn lessKeyedEdge(_: void, a: KeyedEdge, b: KeyedEdge) bool {
    if (!std.mem.eql(u8, a.e.from, b.e.from)) return std.mem.lessThan(u8, a.e.from, b.e.from);
    if (!std.mem.eql(u8, a.e.label, b.e.label)) return std.mem.lessThan(u8, a.e.label, b.e.label);
    if (!std.mem.eql(u8, a.e.to, b.e.to)) return std.mem.lessThan(u8, a.e.to, b.e.to);
    return std.mem.lessThan(u8, a.key, b.key);
}

fn canonicalEdges(alloc: std.mem.Allocator, g: *Graph) ![]KeyedEdge {
    const out = try alloc.alloc(KeyedEdge, g.edges.items.len);
    for (g.edges.items, 0..) |e, i| {
        out[i] = .{ .e = e, .key = try stablePropsKey(alloc, e.props) };
    }
    std.mem.sort(KeyedEdge, out, {}, lessKeyedEdge);
    return out;
}

fn writeEdge(buf: *Buf, alloc: std.mem.Allocator, e: GraphEdge) !void {
    try buf.appendSlice(alloc, "{\"from\":");
    try writeString(buf, alloc, e.from);
    try buf.appendSlice(alloc, ",\"to\":");
    try writeString(buf, alloc, e.to);
    try buf.appendSlice(alloc, ",\"label\":");
    try writeString(buf, alloc, e.label);
    try buf.appendSlice(alloc, ",\"props\":");
    try writeValueCompact(buf, alloc, e.props);
    try buf.append(alloc, '}');
}

/// Canonical `graph.json` bytes (compact, trailing `\n`). Caller owns the bytes.
pub fn graphToCanonical(alloc: std.mem.Allocator, g: *Graph) ![]u8 {
    var buf: Buf = .empty;
    errdefer buf.deinit(alloc);

    try buf.appendSlice(alloc, "{\"version\":1,\"source\":");
    try writeString(&buf, alloc, g.source_file);

    try buf.appendSlice(alloc, ",\"nodes\":[");
    const nodes = try g.nodesSorted();
    defer alloc.free(nodes);
    for (nodes, 0..) |n, i| {
        if (i != 0) try buf.append(alloc, ',');
        try writeNode(&buf, alloc, n);
    }

    try buf.appendSlice(alloc, "],\"edges\":[");
    const edges = try canonicalEdges(alloc, g);
    defer alloc.free(edges);
    for (edges, 0..) |ke, i| {
        if (i != 0) try buf.append(alloc, ',');
        try writeEdge(&buf, alloc, ke.e);
    }

    try buf.appendSlice(alloc, "]}\n");
    return buf.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// tests
// --------------------------------------------------------------------------- //

test "graph mode is compact with fixed key order and trailing newline" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var g = Graph.init(a, "f.vaked");
    defer g.deinit();
    _ = try g.ensureExternal("x");

    const out = try graphToCanonical(a, &g);
    const expected =
        "{\"version\":1,\"source\":\"f.vaked\"," ++
        "\"nodes\":[{\"id\":\"external:x\",\"kind\":\"external\",\"name\":\"x\"," ++
        "\"labels\":[\"external\"],\"props\":{\"external\":true},\"provenance\":null}]," ++
        "\"edges\":[]}\n";
    try std.testing.expectEqualStrings(expected, out);
}

test "string escaping: utf-8 passthrough, escape quote/backslash/control only" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    var buf: Buf = .empty;
    // input:  a"b\c <newline> é(0xC3 0xA9) <unit-separator 0x1f>
    try writeString(&buf, a, "a\"b\\c\n\u{e9}\u{1f}");
    try std.testing.expectEqualStrings("\"a\\\"b\\\\c\\n\u{e9}\\u001f\"", buf.items);
}

test "diagnostics mode is indent-2 with all keys sorted" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();

    // {"diagnostics":[{"severity":"error","code":"E1"}]} — keys deliberately
    // out of order to prove sort_keys.
    const diag = Value{ .object = &.{
        .{ .key = "severity", .value = .{ .string = "error" } },
        .{ .key = "code", .value = .{ .string = "E1" } },
    } };
    const doc = Value{ .object = &.{
        .{ .key = "diagnostics", .value = .{ .array = &.{diag} } },
    } };
    const out = try valueDocToPretty(a, doc);
    const expected =
        "{\n" ++
        "  \"diagnostics\": [\n" ++
        "    {\n" ++
        "      \"code\": \"E1\",\n" ++
        "      \"severity\": \"error\"\n" ++
        "    }\n" ++
        "  ]\n" ++
        "}\n";
    try std.testing.expectEqualStrings(expected, out);
}

test "stablePropsKey is compact sorted-key json" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const v = Value{ .object = &.{
        .{ .key = "b", .value = .{ .int = 2 } },
        .{ .key = "a", .value = .{ .int = 1 } },
    } };
    const k = try stablePropsKey(a, v);
    try std.testing.expectEqualStrings("{\"a\":1,\"b\":2}", k);
}
