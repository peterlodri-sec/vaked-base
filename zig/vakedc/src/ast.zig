const std = @import("std");

// ---- Span ------------------------------------------------------------------

pub const Span = struct {
    byte_start: u32,
    byte_end: u32,
    line: u32,
    col: u32,
};

// ---- Literal ---------------------------------------------------------------

pub const LiteralKind = enum {
    string,
    number,
    bool_lit,
    path,
    duration,
    bytes,
    null_lit,
};

pub const Literal = struct {
    kind: LiteralKind,
    value: []const u8,
    span: Span,
};

// ---- Ref -------------------------------------------------------------------

pub const Ref = struct {
    parts: []const []const u8,
    span: Span,
};

// ---- Expr ------------------------------------------------------------------

pub const ExprTag = enum {
    literal,
    list,
    record,
    app,
};

pub const RecordEntry = union(enum) {
    assignment: Assignment,
    inherit: InheritStmt,
};

pub const App = struct {
    ref: Ref,
    args: ?[]Expr,     // null = no parens
    record: ?[]RecordEntry, // null = no record
};

pub const Expr = union(ExprTag) {
    literal: Literal,
    list: []Expr,
    record: []RecordEntry,
    app: App,
};

// ---- Refinements -----------------------------------------------------------

pub const CmpOp = enum { lte, gte, lt, gt };

pub const RefinementTag = enum {
    required,
    optional,
    nonempty,
    default,
    oneof,
    cmp,
    range,
    matches,
};

pub const Refinement = union(RefinementTag) {
    required: void,
    optional: void,
    nonempty: void,
    default: *Expr,
    oneof: []Expr,
    cmp: struct { op: CmpOp, number: []const u8 },
    range: struct { lo: []const u8, hi: []const u8 },
    matches: []const u8, // regex value including slashes
};

// ---- TypeRef ---------------------------------------------------------------

pub const TypeRef = struct {
    text: []const u8,
};

// ---- Annotation ------------------------------------------------------------

pub const Annotation = struct {
    name: []const u8,
    args: ?[]Expr,
};

// ---- Statements ------------------------------------------------------------

pub const Assignment = struct {
    target: []const u8,
    op: []const u8, // "=" or "?="
    value: *Expr,
};

pub const FieldDecl = struct {
    name: []const u8,
    type_ref: TypeRef,
    refinements: []Refinement,
};

pub const GrantDecl = struct {
    names: []const []const u8,
};

pub const OrderChain = []const []const u8;

pub const OrderDecl = struct {
    chains: []OrderChain,
};

pub const InheritStmt = struct {
    names: []const []const u8,
};

pub const NodeDecl = struct {
    name: []const u8,
    body: []Stmt,
    span: Span,
};

pub const Edge = struct {
    refs: []Ref,
    label: ?[]const u8,
};

pub const Param = struct {
    name: []const u8,
    type_ref: TypeRef,
    default: ?*Expr,
};

pub const Signature = struct {
    params: []Param,
    ret: ?TypeRef,
};

pub const Decl = struct {
    kind: []const u8,
    name: []const u8,
    annotations: []Annotation,
    signature: ?Signature,
    body: []Stmt,
    span: Span,
};

pub const StmtTag = enum {
    assignment,
    field_decl,
    open_decl,
    grant_decl,
    order_decl,
    inherit,
    edge,
    node_decl,
    decl,
    app,
};

pub const Stmt = union(StmtTag) {
    assignment: Assignment,
    field_decl: FieldDecl,
    open_decl: void,
    grant_decl: GrantDecl,
    order_decl: OrderDecl,
    inherit: InheritStmt,
    edge: Edge,
    node_decl: NodeDecl,
    decl: Decl,
    app: App,
};

// ---- Import ----------------------------------------------------------------

pub const Import = struct {
    path: []const u8,
    span: Span,
};

// ---- Item / File -----------------------------------------------------------

pub const ItemTag = enum {
    decl,
    import_decl,
};

pub const Item = union(ItemTag) {
    decl: Decl,
    import_decl: Import,
};

pub const File = struct {
    items: []Item,
    source_file: []const u8,
};

// ---- JSON serialization ----------------------------------------------------

pub fn writeJson(file: File, writer: anytype, alloc: std.mem.Allocator) !void {
    _ = alloc;
    try writer.writeAll("{\"source_file\":");
    try writeJsonString(writer, file.source_file);
    try writer.writeAll(",\"items\":[");
    for (file.items, 0..) |item, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonItem(writer, item);
    }
    try writer.writeAll("]}");
}

fn writeJsonItem(writer: anytype, item: Item) !void {
    switch (item) {
        .import_decl => |imp| try writeJsonImport(writer, imp),
        .decl => |d| try writeJsonDecl(writer, d),
    }
}

fn writeJsonImport(writer: anytype, imp: Import) !void {
    try writer.writeAll("{\"_type\":\"import\",\"path\":");
    try writeJsonString(writer, imp.path);
    try writer.writeAll(",\"span\":");
    try writeJsonSpan(writer, imp.span);
    try writer.writeByte('}');
}

fn writeJsonDecl(writer: anytype, d: Decl) !void {
    try writer.writeAll("{\"_type\":\"decl\",\"kind\":");
    try writeJsonString(writer, d.kind);
    try writer.writeAll(",\"name\":");
    try writeJsonString(writer, d.name);
    try writer.writeAll(",\"annotations\":[");
    for (d.annotations, 0..) |ann, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonAnnotation(writer, ann);
    }
    try writer.writeAll("],\"signature\":");
    if (d.signature) |sig| {
        try writeJsonSignature(writer, sig);
    } else {
        try writer.writeAll("null");
    }
    try writer.writeAll(",\"body\":[");
    for (d.body, 0..) |stmt, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonStmt(writer, stmt);
    }
    try writer.writeAll("],\"span\":");
    try writeJsonSpan(writer, d.span);
    try writer.writeByte('}');
}

fn writeJsonAnnotation(writer: anytype, ann: Annotation) !void {
    try writer.writeAll("{\"_type\":\"annotation\",\"name\":");
    try writeJsonString(writer, ann.name);
    try writer.writeAll(",\"args\":");
    if (ann.args) |args| {
        try writer.writeByte('[');
        for (args, 0..) |arg, i| {
            if (i > 0) try writer.writeByte(',');
            try writeJsonExpr(writer, arg);
        }
        try writer.writeByte(']');
    } else {
        try writer.writeAll("null");
    }
    try writer.writeByte('}');
}

fn writeJsonSignature(writer: anytype, sig: Signature) !void {
    try writer.writeAll("{\"params\":[");
    for (sig.params, 0..) |p, i| {
        if (i > 0) try writer.writeByte(',');
        try writer.writeAll("{\"name\":");
        try writeJsonString(writer, p.name);
        try writer.writeAll(",\"type\":");
        try writeJsonString(writer, p.type_ref.text);
        try writer.writeAll(",\"default\":");
        if (p.default) |d| {
            try writeJsonExpr(writer, d.*);
        } else {
            try writer.writeAll("null");
        }
        try writer.writeByte('}');
    }
    try writer.writeAll("],\"ret\":");
    if (sig.ret) |r| {
        try writeJsonString(writer, r.text);
    } else {
        try writer.writeAll("null");
    }
    try writer.writeByte('}');
}

fn writeJsonStmt(writer: anytype, stmt: Stmt) !void {
    switch (stmt) {
        .assignment => |a| try writeJsonAssignment(writer, a),
        .field_decl => |f| try writeJsonFieldDecl(writer, f),
        .open_decl => try writer.writeAll("{\"_type\":\"open_decl\"}"),
        .grant_decl => |g| try writeJsonGrantDecl(writer, g),
        .order_decl => |o| try writeJsonOrderDecl(writer, o),
        .inherit => |inh| try writeJsonInherit(writer, inh),
        .edge => |e| try writeJsonEdge(writer, e),
        .node_decl => |nd| try writeJsonNodeDecl(writer, nd),
        .decl => |d| try writeJsonDecl(writer, d),
        .app => |a| try writeJsonApp(writer, a),
    }
}

fn writeJsonAssignment(writer: anytype, a: Assignment) !void {
    try writer.writeAll("{\"_type\":\"assignment\",\"target\":");
    try writeJsonString(writer, a.target);
    try writer.writeAll(",\"op\":");
    try writeJsonString(writer, a.op);
    try writer.writeAll(",\"value\":");
    try writeJsonExpr(writer, a.value.*);
    try writer.writeByte('}');
}

fn writeJsonFieldDecl(writer: anytype, f: FieldDecl) !void {
    try writer.writeAll("{\"_type\":\"field_decl\",\"name\":");
    try writeJsonString(writer, f.name);
    try writer.writeAll(",\"type\":");
    try writeJsonString(writer, f.type_ref.text);
    try writer.writeAll(",\"refinements\":[");
    for (f.refinements, 0..) |ref, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonRefinement(writer, ref);
    }
    try writer.writeAll("]}");
}

fn writeJsonRefinement(writer: anytype, r: Refinement) !void {
    switch (r) {
        .required => try writer.writeAll("{\"_type\":\"required\"}"),
        .optional => try writer.writeAll("{\"_type\":\"optional\"}"),
        .nonempty => try writer.writeAll("{\"_type\":\"nonempty\"}"),
        .default => |expr| {
            try writer.writeAll("{\"_type\":\"default\",\"value\":");
            try writeJsonExpr(writer, expr.*);
            try writer.writeByte('}');
        },
        .oneof => |items| {
            try writer.writeAll("{\"_type\":\"oneof\",\"values\":[");
            for (items, 0..) |item, i| {
                if (i > 0) try writer.writeByte(',');
                try writeJsonExpr(writer, item);
            }
            try writer.writeAll("]}");
        },
        .cmp => |c| {
            const op_str: []const u8 = switch (c.op) {
                .lte => "<=",
                .gte => ">=",
                .lt => "<",
                .gt => ">",
            };
            try writer.writeAll("{\"_type\":\"cmp\",\"op\":");
            try writeJsonString(writer, op_str);
            try writer.writeAll(",\"number\":");
            try writeJsonString(writer, c.number);
            try writer.writeByte('}');
        },
        .range => |rng| {
            try writer.writeAll("{\"_type\":\"range\",\"lo\":");
            try writeJsonString(writer, rng.lo);
            try writer.writeAll(",\"hi\":");
            try writeJsonString(writer, rng.hi);
            try writer.writeByte('}');
        },
        .matches => |rx| {
            try writer.writeAll("{\"_type\":\"matches\",\"regex\":");
            try writeJsonString(writer, rx);
            try writer.writeByte('}');
        },
    }
}

fn writeJsonGrantDecl(writer: anytype, g: GrantDecl) !void {
    try writer.writeAll("{\"_type\":\"grant_decl\",\"names\":[");
    for (g.names, 0..) |name, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonString(writer, name);
    }
    try writer.writeAll("]}");
}

fn writeJsonOrderDecl(writer: anytype, o: OrderDecl) !void {
    try writer.writeAll("{\"_type\":\"order_decl\",\"chains\":[");
    for (o.chains, 0..) |chain, i| {
        if (i > 0) try writer.writeByte(',');
        try writer.writeByte('[');
        for (chain, 0..) |name, j| {
            if (j > 0) try writer.writeByte(',');
            try writeJsonString(writer, name);
        }
        try writer.writeByte(']');
    }
    try writer.writeAll("]}");
}

fn writeJsonInherit(writer: anytype, inh: InheritStmt) !void {
    try writer.writeAll("{\"_type\":\"inherit\",\"names\":[");
    for (inh.names, 0..) |name, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonString(writer, name);
    }
    try writer.writeAll("]}");
}

fn writeJsonEdge(writer: anytype, e: Edge) !void {
    try writer.writeAll("{\"_type\":\"edge\",\"refs\":[");
    for (e.refs, 0..) |ref, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonRef(writer, ref);
    }
    try writer.writeAll("],\"label\":");
    if (e.label) |lbl| {
        try writeJsonString(writer, lbl);
    } else {
        try writer.writeAll("null");
    }
    try writer.writeByte('}');
}

fn writeJsonNodeDecl(writer: anytype, nd: NodeDecl) !void {
    try writer.writeAll("{\"_type\":\"node_decl\",\"name\":");
    try writeJsonString(writer, nd.name);
    try writer.writeAll(",\"body\":[");
    for (nd.body, 0..) |stmt, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonStmt(writer, stmt);
    }
    try writer.writeAll("],\"span\":");
    try writeJsonSpan(writer, nd.span);
    try writer.writeByte('}');
}

fn writeJsonApp(writer: anytype, a: App) !void {
    try writer.writeAll("{\"_type\":\"app\",\"ref\":");
    try writeJsonRef(writer, a.ref);
    try writer.writeAll(",\"args\":");
    if (a.args) |args| {
        try writer.writeByte('[');
        for (args, 0..) |arg, i| {
            if (i > 0) try writer.writeByte(',');
            try writeJsonExpr(writer, arg);
        }
        try writer.writeByte(']');
    } else {
        try writer.writeAll("null");
    }
    try writer.writeAll(",\"record\":");
    if (a.record) |entries| {
        try writer.writeByte('[');
        for (entries, 0..) |entry, i| {
            if (i > 0) try writer.writeByte(',');
            try writeJsonRecordEntry(writer, entry);
        }
        try writer.writeByte(']');
    } else {
        try writer.writeAll("null");
    }
    try writer.writeByte('}');
}

fn writeJsonExpr(writer: anytype, expr: Expr) !void {
    switch (expr) {
        .literal => |lit| try writeJsonLiteral(writer, lit),
        .list => |items| {
            try writer.writeAll("{\"_type\":\"list\",\"items\":[");
            for (items, 0..) |item, i| {
                if (i > 0) try writer.writeByte(',');
                try writeJsonExpr(writer, item);
            }
            try writer.writeAll("]}");
        },
        .record => |entries| {
            try writer.writeAll("{\"_type\":\"record\",\"entries\":[");
            for (entries, 0..) |entry, i| {
                if (i > 0) try writer.writeByte(',');
                try writeJsonRecordEntry(writer, entry);
            }
            try writer.writeAll("]}");
        },
        .app => |a| try writeJsonApp(writer, a),
    }
}

fn writeJsonLiteral(writer: anytype, lit: Literal) !void {
    const kind_str: []const u8 = switch (lit.kind) {
        .string => "string",
        .number => "number",
        .bool_lit => "bool",
        .path => "path",
        .duration => "duration",
        .bytes => "bytes",
        .null_lit => "null",
    };
    try writer.writeAll("{\"_type\":\"literal\",\"kind\":");
    try writeJsonString(writer, kind_str);
    try writer.writeAll(",\"value\":");
    try writeJsonString(writer, lit.value);
    try writer.writeAll(",\"span\":");
    try writeJsonSpan(writer, lit.span);
    try writer.writeByte('}');
}

fn writeJsonRef(writer: anytype, ref: Ref) !void {
    try writer.writeAll("{\"_type\":\"ref\",\"parts\":[");
    for (ref.parts, 0..) |part, i| {
        if (i > 0) try writer.writeByte(',');
        try writeJsonString(writer, part);
    }
    try writer.writeAll("],\"span\":");
    try writeJsonSpan(writer, ref.span);
    try writer.writeByte('}');
}

fn writeJsonRecordEntry(writer: anytype, entry: RecordEntry) !void {
    switch (entry) {
        .assignment => |a| try writeJsonAssignment(writer, a),
        .inherit => |inh| try writeJsonInherit(writer, inh),
    }
}

fn writeJsonSpan(writer: anytype, span: Span) !void {
    try writer.print("{{\"byte_start\":{d},\"byte_end\":{d},\"line\":{d},\"col\":{d}}}", .{
        span.byte_start,
        span.byte_end,
        span.line,
        span.col,
    });
}

// Write a JSON-escaped string with surrounding quotes.
fn writeJsonString(writer: anytype, s: []const u8) !void {
    try writer.writeByte('"');
    for (s) |c| {
        switch (c) {
            '"' => try writer.writeAll("\\\""),
            '\\' => try writer.writeAll("\\\\"),
            '\n' => try writer.writeAll("\\n"),
            '\r' => try writer.writeAll("\\r"),
            '\t' => try writer.writeAll("\\t"),
            0x08 => try writer.writeAll("\\b"),
            0x0C => try writer.writeAll("\\f"),
            0x00...0x07, 0x0B, 0x0E...0x1F => {
                try writer.print("\\u{x:0>4}", .{c});
            },
            else => try writer.writeByte(c),
        }
    }
    try writer.writeByte('"');
}
