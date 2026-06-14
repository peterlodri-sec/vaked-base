//! AST node shapes — port of `vakedc/parser.py`'s node dataclasses.
//!
//! The parser produces a `[]Item` (top-level decls/imports). Bodies hold
//! `[]Stmt`. Expression values are `Expr`. Everything is allocated in the
//! per-compile arena the CLI hands the parser, so there are no per-node frees;
//! string slices reference the source bytes (or arena-owned strings produced by
//! `stripString`). Mirrors the Python AST 1:1 so the resolver port is direct.

const std = @import("std");

/// A dotted reference (`ident { "." ident }`). `parts[0]` is the head; `dotted`
/// is the `"."`-join. Carries the source span of the whole ref.
pub const Ref = struct {
    parts: []const []const u8,
    byteStart: usize,
    byteEnd: usize,
    line: usize,
    col: usize,

    pub fn head(self: Ref) []const u8 {
        return self.parts[0];
    }

    /// `"."`-join of the parts. Caller-arena allocated.
    pub fn dotted(self: Ref, alloc: std.mem.Allocator) ![]const u8 {
        return std.mem.join(alloc, ".", self.parts);
    }
};

/// A parsed type, stored as flat text (not checked). Mirrors `TypeRef`.
pub const TypeRef = struct {
    text: []const u8,
};

/// Literal kinds, named to match Python's `Literal.kind` strings.
pub const LitKind = enum {
    STRING,
    NUMBER,
    DURATION,
    BYTES,
    PATH,
    BOOL,
    NULL,

    /// Lowercased name — what `_value_to_props` emits as the `"lit"` value.
    pub fn lower(self: LitKind) []const u8 {
        return switch (self) {
            .STRING => "string",
            .NUMBER => "number",
            .DURATION => "duration",
            .BYTES => "bytes",
            .PATH => "path",
            .BOOL => "bool",
            .NULL => "null",
        };
    }
};

pub const Literal = struct {
    kind: LitKind,
    value: []const u8, // always a string (quote-stripped for STRING)
};

/// An application / reference value: `ref [ "(" args ")" ] [ record ]`.
/// A *bare* ref-app (args == null and record == null) is a dependency ref.
pub const App = struct {
    ref: Ref,
    args: ?[]const Expr, // null = no parens
    record: ?[]const Entry, // null = no record block
};

pub const ListLit = struct {
    items: []const Expr,
};

pub const RecordLit = struct {
    entries: []const Entry,
};

/// expr = literal | list | record | app.
pub const Expr = union(enum) {
    literal: Literal,
    list: ListLit,
    record: RecordLit,
    app: App,
};

/// A record / assignment-target entry: an assignment or an `inherit`.
pub const Entry = union(enum) {
    assignment: Assignment,
    inherit: InheritStmt,
};

pub const Assignment = struct {
    target: []const u8,
    op: []const u8, // "=" or "?="
    value: Expr,
};

/// A single refinement on a field. Mirrors the Python tuples:
///   ("required",) / ("optional",) / ("nonempty",)
///   ("default", expr)
///   ("oneof", listlit)
///   ("matches", regex_text)
///   ("cmp", op, number_text)
///   ("range", lo_text, hi_text)
pub const Refinement = union(enum) {
    word: []const u8, // required / optional / nonempty
    default: Expr,
    oneof: ListLit,
    matches: []const u8, // raw regex token text (with slashes)
    cmp: struct { op: []const u8, num: []const u8 },
    range: struct { lo: []const u8, hi: []const u8 },
};

pub const FieldDecl = struct {
    name: []const u8,
    type: TypeRef,
    refinements: []const Refinement,
};

pub const GrantDecl = struct {
    names: []const []const u8,
};

pub const OrderDecl = struct {
    chains: []const []const []const u8, // list of chains, each a list of idents
};

pub const InheritStmt = struct {
    names: []const []const u8,
};

pub const Edge = struct {
    refs: []const Ref, // >= 2
    label: ?[]const u8, // quote-stripped string label or null
};

/// An annotation: `@ name [ "(" args ")" ]`. `args == null` if no parens.
pub const Annotation = struct {
    name: []const u8,
    args: ?[]const Expr,
};

/// signature = "(" [ param { "," param } ] ")" [ "->" type ].
pub const Param = struct {
    name: []const u8,
    type: TypeRef,
    default: ?Expr,
};

pub const Signature = struct {
    params: []const Param,
    ret: ?TypeRef,
};

pub const Decl = struct {
    kind: []const u8,
    name: []const u8,
    annotations: []const Annotation,
    signature: ?Signature,
    body: []const Stmt,
    byteStart: usize,
    byteEnd: usize,
    line: usize,
    col: usize,
};

pub const NodeDecl = struct {
    name: []const u8,
    body: []const Stmt,
    byteStart: usize,
    byteEnd: usize,
    line: usize,
    col: usize,
};

/// A statement inside a block. The resolver dispatches on the tag exactly as
/// `_build_stmt` dispatches on the Python class.
pub const Stmt = union(enum) {
    decl: Decl,
    node_decl: NodeDecl,
    edge: Edge,
    assignment: Assignment,
    app: App, // bare app statement: no edge
    field_decl: FieldDecl,
    grant_decl: GrantDecl,
    order_decl: OrderDecl,
    open_decl, // bare `open`
    inherit_stmt: InheritStmt,
};

/// A top-level item: a declaration or an import.
pub const Item = union(enum) {
    decl: Decl,
    import: Import,
};

pub const Import = struct {
    path: []const u8, // quote-stripped string value
    byteStart: usize,
    byteEnd: usize,
    line: usize,
    col: usize,
};
