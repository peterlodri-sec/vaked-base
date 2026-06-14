//! vakedc.parser (Zig port) — hand-written recursive-descent parser, PEG-ordered
//! per the v0.3 grammar. A faithful 1:1 port of `vakedc/parser.py`: same cursor
//! discipline (which methods `_skip_nl` and which peek), same ordered-choice
//! lookahead predicates, same backtracking for `edge`. Accept/reject verdict
//! matches Python token-for-token.
//!
//! On a syntax error it returns `error.ParseFailed` and fills `ErrInfo` (the CLI
//! formats `file:line:col — expected …, got …`). stdout+exit code are what the
//! oracle gates; the message is for human parity.

const std = @import("std");
const ast = @import("ast.zig");
const lex = @import("vaked-lex");
const Token = lex.Token;
const Kind = lex.Kind;

const Item = ast.Item;
const Stmt = ast.Stmt;
const Expr = ast.Expr;
const Entry = ast.Entry;
const Ref = ast.Ref;
const Decl = ast.Decl;
const NodeDecl = ast.NodeDecl;
const Annotation = ast.Annotation;
const Param = ast.Param;
const Signature = ast.Signature;
const Refinement = ast.Refinement;

pub const ParseError = error{
    ParseFailed,
    OutOfMemory,
};

/// Source-mapped syntax-error detail, mirroring `VakedSyntaxError`.
pub const ErrInfo = struct {
    file: []const u8,
    line: usize,
    col: usize,
    expected: []const u8,
    got: []const u8,
};

/// The 23 declaration kinds (grammar `kind`) — order matches `parser.py:KINDS`.
pub const KINDS = [_][]const u8{
    "runtime",       "input",   "engine",     "host",
    "network",       "filesystem", "mcp",     "ebpf",
    "budget",        "observability", "runclass", "workflow",
    "index",         "catalog", "stream",     "fiber",
    "surface",       "mesh",    "device",     "mediaPipeline",
    "parallel",      "schema",  "capability",
};

pub fn isKind(s: []const u8) bool {
    for (KINDS) |k| {
        if (std.mem.eql(u8, k, s)) return true;
    }
    return false;
}

const REFINEMENT_WORDS = [_][]const u8{
    "required", "optional", "nonempty", "default", "oneof", "in", "matches",
};
const CMP_OPS = [_][]const u8{ "<=", ">=", "<", ">" };

pub const Parser = struct {
    toks: []const Token,
    file: []const u8,
    i: usize = 0,
    alloc: std.mem.Allocator,
    err: ?ErrInfo = null,

    // --- cursor helpers -------------------------------------------------- //

    fn cur(self: *Parser) Token {
        return self.toks[self.i];
    }

    fn skipNl(self: *Parser) void {
        while (self.toks[self.i].kind == .NEWLINE) self.i += 1;
    }

    fn atEof(self: *Parser) bool {
        return self.toks[self.i].kind == .EOF;
    }

    fn isOpTok(t: Token, val: []const u8) bool {
        return t.kind == .OP and std.mem.eql(u8, t.value, val);
    }

    fn isOp(self: *Parser, val: []const u8) bool {
        return isOpTok(self.toks[self.i], val);
    }

    fn isIdentTok(t: Token, val: ?[]const u8) bool {
        if (t.kind != .IDENT) return false;
        if (val) |v| return std.mem.eql(u8, t.value, v);
        return true;
    }

    fn isIdent(self: *Parser, val: ?[]const u8) bool {
        return isIdentTok(self.toks[self.i], val);
    }

    fn fail(self: *Parser, expected: []const u8) ParseError {
        const t = self.toks[self.i];
        const got: []const u8 = if (t.kind != .EOF)
            std.fmt.allocPrint(self.alloc, "{s} {s}", .{ t.kind.name(), pyRepr(self.alloc, t.value) catch "?" }) catch "?"
        else
            "end of input";
        self.err = .{
            .file = self.file,
            .line = t.line,
            .col = t.col,
            .expected = expected,
            .got = got,
        };
        return error.ParseFailed;
    }

    fn expectOp(self: *Parser, val: []const u8) ParseError!Token {
        self.skipNl();
        const t = self.toks[self.i];
        if (isOpTok(t, val)) {
            self.i += 1;
            return t;
        }
        return self.fail(try std.fmt.allocPrint(self.alloc, "{s}", .{pyRepr(self.alloc, val) catch val}));
    }

    fn expectIdent(self: *Parser) ParseError!Token {
        self.skipNl();
        const t = self.toks[self.i];
        if (t.kind == .IDENT) {
            self.i += 1;
            return t;
        }
        return self.fail("an identifier");
    }

    // --- entry point ----------------------------------------------------- //

    pub fn parseFile(self: *Parser) ParseError![]const Item {
        var items: std.ArrayList(Item) = .empty;
        self.skipNl();
        while (!self.atEof()) {
            try items.append(self.alloc, try self.item());
            self.skipNl();
        }
        return items.toOwnedSlice(self.alloc);
    }

    fn item(self: *Parser) ParseError!Item {
        self.skipNl();
        const t = self.toks[self.i];
        if (isIdentTok(t, "use")) return .{ .import = try self.import_() };
        return .{ .decl = try self.decl() };
    }

    fn import_(self: *Parser) ParseError!ast.Import {
        const kw = self.toks[self.i]; // 'use'
        self.i += 1;
        // _skip_nl_inline is a no-op in Python; keep strict.
        const t = self.toks[self.i];
        if (t.kind != .STRING) return self.fail("a string after `use`");
        self.i += 1;
        const path = stripString(t.value);
        return .{ .path = path, .byteStart = kw.byteStart, .byteEnd = t.byteEnd, .line = kw.line, .col = kw.col };
    }

    // --- declarations ---------------------------------------------------- //

    fn decl(self: *Parser) ParseError!Decl {
        self.skipNl();
        var annotations: std.ArrayList(Annotation) = .empty;
        while (self.isOp("@")) {
            try annotations.append(self.alloc, try self.annotation());
            self.skipNl();
        }
        const t = self.toks[self.i];
        if (!(t.kind == .IDENT and isKind(t.value))) return self.fail("a declaration kind keyword");
        const kind = t.value;
        const kw = t;
        self.i += 1;
        const nm = try self.name();
        var sig: ?Signature = null;
        if (self.isOp("(")) sig = try self.signature();
        const body = try self.block();
        return .{
            .kind = kind,
            .name = nm,
            .annotations = try annotations.toOwnedSlice(self.alloc),
            .signature = sig,
            .body = body.stmts,
            .byteStart = kw.byteStart,
            .byteEnd = body.close.byteEnd,
            .line = kw.line,
            .col = kw.col,
        };
    }

    fn name(self: *Parser) ParseError![]const u8 {
        self.skipNl();
        const t = self.toks[self.i];
        if (t.kind == .IDENT) {
            self.i += 1;
            return t.value;
        }
        if (t.kind == .STRING) {
            self.i += 1;
            return stripString(t.value);
        }
        return self.fail("a declaration name (identifier or string)");
    }

    fn annotation(self: *Parser) ParseError!Annotation {
        _ = try self.expectOp("@");
        const nm = (try self.expectIdent()).value;
        var args: ?[]const Expr = null;
        if (self.isOp("(")) args = try self.parenArgs();
        return .{ .name = nm, .args = args };
    }

    fn signature(self: *Parser) ParseError!Signature {
        _ = try self.expectOp("(");
        var params: std.ArrayList(Param) = .empty;
        if (!self.isOp(")")) {
            try params.append(self.alloc, try self.param());
            while (self.isOp(",")) {
                self.i += 1;
                try params.append(self.alloc, try self.param());
            }
        }
        _ = try self.expectOp(")");
        var ret: ?ast.TypeRef = null;
        if (self.isOp("->")) {
            self.i += 1;
            ret = try self.type_();
        }
        return .{ .params = try params.toOwnedSlice(self.alloc), .ret = ret };
    }

    fn param(self: *Parser) ParseError!Param {
        const nm = (try self.expectIdent()).value;
        _ = try self.expectOp(":");
        const ty = try self.type_();
        var default: ?Expr = null;
        if (self.isOp("=")) {
            self.i += 1;
            default = try self.expr();
        }
        return .{ .name = nm, .type = ty, .default = default };
    }

    // --- blocks & statements --------------------------------------------- //

    const Block = struct { stmts: []const Stmt, close: Token };

    fn block(self: *Parser) ParseError!Block {
        self.skipNl();
        _ = try self.expectOp("{");
        var stmts: std.ArrayList(Stmt) = .empty;
        self.skipNl();
        while (!self.isOp("}")) {
            if (self.atEof()) return self.fail("'}' to close block");
            try stmts.append(self.alloc, try self.stmt());
            self.skipNl();
        }
        const close = self.toks[self.i];
        self.i += 1; // consume '}'
        return .{ .stmts = try stmts.toOwnedSlice(self.alloc), .close = close };
    }

    fn stmt(self: *Parser) ParseError!Stmt {
        self.skipNl();
        const t = self.toks[self.i];

        // field_decl / grant_decl / order_decl — BEFORE assignment.
        if (isIdentTok(t, "field") and self.lookaheadField()) return .{ .field_decl = try self.fieldDecl() };
        if (isIdentTok(t, "grant") and self.lookaheadGrant()) return .{ .grant_decl = try self.grantDecl() };
        if (isIdentTok(t, "order") and self.lookaheadOrder()) return .{ .order_decl = try self.orderDecl() };

        // assignment = ident assign_op expr
        if (t.kind == .IDENT and self.lookaheadAssign()) return .{ .assignment = try self.assignment() };

        // open_decl — AFTER assignment (bare `open`, not `open =`).
        if (isIdentTok(t, "open")) {
            self.i += 1;
            return .open_decl;
        }

        // inherit_stmt = "inherit" ident { ident }
        if (isIdentTok(t, "inherit")) return .{ .inherit_stmt = try self.inheritStmt() };

        // edge = ref "->" ref { "->" ref } [ ":" string ]  (try before node/decl)
        if (try self.tryEdge()) |e| return .{ .edge = e };

        // node_decl = "node" name block
        if (isIdentTok(t, "node") and self.lookaheadNode()) return .{ .node_decl = try self.nodeDecl() };

        // decl = { annotation } kind name [ signature ] block
        if (self.isOp("@") or (t.kind == .IDENT and isKind(t.value) and self.lookaheadDecl())) {
            return .{ .decl = try self.decl() };
        }

        // app = ref [ "(" ... ")" ] [ record ]
        if (t.kind == .IDENT) return .{ .app = try self.app() };

        return self.fail("a statement");
    }

    // --- lookahead predicates (mirror PEG ordered-choice disambiguation) -- //

    fn lookaheadField(self: *Parser) bool {
        // `field` ident ":"
        const j = self.i + 1;
        if (self.toks[j].kind != .IDENT) return false;
        return isOpTok(self.toks[j + 1], ":");
    }

    fn lookaheadGrant(self: *Parser) bool {
        // `grant` ident
        return self.toks[self.i + 1].kind == .IDENT;
    }

    fn lookaheadOrder(self: *Parser) bool {
        // `order` ident "<"
        const j = self.i + 1;
        if (self.toks[j].kind != .IDENT) return false;
        return isOpTok(self.toks[j + 1], "<");
    }

    fn lookaheadAssign(self: *Parser) bool {
        // ident assign_op
        const t1 = self.toks[self.i + 1];
        return t1.kind == .OP and (std.mem.eql(u8, t1.value, "=") or std.mem.eql(u8, t1.value, "?="));
    }

    fn lookaheadNode(self: *Parser) bool {
        // `node` name "{"
        const j = self.i + 1;
        const nt = self.toks[j];
        if (nt.kind == .IDENT or nt.kind == .STRING) {
            return isOpTok(self.toks[j + 1], "{");
        }
        return false;
    }

    fn lookaheadDecl(self: *Parser) bool {
        // kind name [signature] "{"  — name is ident|string, then '(' or '{'.
        const j = self.i + 1;
        const nt = self.toks[j];
        if (!(nt.kind == .IDENT or nt.kind == .STRING)) return false;
        const k = j + 1;
        return isOpTok(self.toks[k], "{") or isOpTok(self.toks[k], "(");
    }

    // --- statement forms ------------------------------------------------- //

    fn fieldDecl(self: *Parser) ParseError!ast.FieldDecl {
        self.i += 1; // 'field'
        const nm = (try self.expectIdent()).value;
        _ = try self.expectOp(":");
        const ty = try self.type_();
        var refinements: std.ArrayList(Refinement) = .empty;
        if (self.isOp("{")) {
            self.i += 1;
            self.skipNl();
            while (!self.isOp("}")) {
                if (self.atEof()) return self.fail("'}' to close refinement list");
                try refinements.append(self.alloc, try self.refinement());
                self.skipNl();
            }
            self.i += 1; // '}'
        }
        return .{ .name = nm, .type = ty, .refinements = try refinements.toOwnedSlice(self.alloc) };
    }

    fn refinement(self: *Parser) ParseError!Refinement {
        self.skipNl();
        const t = self.toks[self.i];
        if (isIdentTok(t, "required") or isIdentTok(t, "optional") or isIdentTok(t, "nonempty")) {
            self.i += 1;
            return .{ .word = t.value };
        }
        if (isIdentTok(t, "default")) {
            self.i += 1;
            _ = try self.expectOp("=");
            return .{ .default = try self.expr() };
        }
        if (isIdentTok(t, "oneof")) {
            self.i += 1;
            return .{ .oneof = try self.list() };
        }
        if (isIdentTok(t, "matches")) {
            self.i += 1;
            self.skipNl();
            const r = self.toks[self.i];
            if (r.kind != .REGEX) return self.fail("a /regex/ literal after `matches`");
            self.i += 1;
            return .{ .matches = r.value };
        }
        // cmp_ref = ( ">=" | "<=" | ">" | "<" ) number
        for (CMP_OPS) |op| {
            if (isOpTok(t, op)) {
                self.i += 1;
                const num = try self.expectNumber();
                return .{ .cmp = .{ .op = op, .num = num } };
            }
        }
        // range_ref = "in" number ".." number
        if (isIdentTok(t, "in")) {
            self.i += 1;
            const lo = try self.expectNumber();
            _ = try self.expectOp("..");
            const hi = try self.expectNumber();
            return .{ .range = .{ .lo = lo, .hi = hi } };
        }
        return self.fail("a refinement (required/optional/nonempty/default/oneof/comparison/in/matches)");
    }

    fn expectNumber(self: *Parser) ParseError![]const u8 {
        self.skipNl();
        const t = self.toks[self.i];
        if (t.kind != .NUMBER) return self.fail("a number");
        self.i += 1;
        return t.value;
    }

    fn grantDecl(self: *Parser) ParseError!ast.GrantDecl {
        self.i += 1; // 'grant'
        var names: std.ArrayList([]const u8) = .empty;
        try names.append(self.alloc, (try self.expectIdent()).value);
        // { ident } line-bounded: NEWLINE ends it (do NOT skip NEWLINE).
        while (self.toks[self.i].kind == .IDENT) {
            try names.append(self.alloc, self.toks[self.i].value);
            self.i += 1;
        }
        return .{ .names = try names.toOwnedSlice(self.alloc) };
    }

    fn orderDecl(self: *Parser) ParseError!ast.OrderDecl {
        self.i += 1; // 'order'
        var chains: std.ArrayList([]const []const u8) = .empty;
        try chains.append(self.alloc, try self.orderChain());
        while (true) {
            const save = self.i;
            if (isOpTok(self.toks[self.i], ";")) {
                self.i += 1;
                self.skipNl(); // ';' absorbs trailing newlines
                try chains.append(self.alloc, try self.orderChain());
                continue;
            }
            self.i = save;
            break;
        }
        return .{ .chains = try chains.toOwnedSlice(self.alloc) };
    }

    fn orderChain(self: *Parser) ParseError![]const []const u8 {
        // NEWLINE significant here; do not skip it within the chain.
        const t = self.toks[self.i];
        if (t.kind != .IDENT) return self.fail("an identifier to start an order chain");
        var names: std.ArrayList([]const u8) = .empty;
        try names.append(self.alloc, t.value);
        self.i += 1;
        if (!isOpTok(self.toks[self.i], "<")) return self.fail("'<' in an order chain");
        while (isOpTok(self.toks[self.i], "<")) {
            self.i += 1;
            const nx = self.toks[self.i];
            if (nx.kind != .IDENT) return self.fail("an identifier after '<' in an order chain");
            try names.append(self.alloc, nx.value);
            self.i += 1;
        }
        return names.toOwnedSlice(self.alloc);
    }

    fn inheritStmt(self: *Parser) ParseError!ast.InheritStmt {
        self.i += 1; // 'inherit'
        var names: std.ArrayList([]const u8) = .empty;
        try names.append(self.alloc, (try self.expectIdent()).value);
        while (self.toks[self.i].kind == .IDENT) {
            try names.append(self.alloc, self.toks[self.i].value);
            self.i += 1;
        }
        return .{ .names = try names.toOwnedSlice(self.alloc) };
    }

    fn assignment(self: *Parser) ParseError!ast.Assignment {
        const target = self.toks[self.i].value;
        self.i += 1;
        const op = self.toks[self.i].value; // '=' or '?='
        self.i += 1;
        const value = try self.expr();
        return .{ .target = target, .op = op, .value = value };
    }

    fn nodeDecl(self: *Parser) ParseError!NodeDecl {
        const kw = self.toks[self.i]; // 'node'
        self.i += 1;
        const nm = try self.name();
        const body = try self.block();
        return .{
            .name = nm,
            .body = body.stmts,
            .byteStart = kw.byteStart,
            .byteEnd = body.close.byteEnd,
            .line = kw.line,
            .col = kw.col,
        };
    }

    fn tryEdge(self: *Parser) ParseError!?ast.Edge {
        const save = self.i;
        if (self.toks[self.i].kind != .IDENT) return null;
        const first = try self.ref();
        if (!self.isOp("->")) {
            self.i = save;
            return null;
        }
        var refs: std.ArrayList(Ref) = .empty;
        try refs.append(self.alloc, first);
        while (self.isOp("->")) {
            self.i += 1;
            try refs.append(self.alloc, try self.ref());
        }
        var label: ?[]const u8 = null;
        if (self.isOp(":")) {
            self.i += 1;
            self.skipNl();
            const t = self.toks[self.i];
            if (t.kind != .STRING) return self.fail("a string label after ':' in an edge");
            self.i += 1;
            label = stripString(t.value);
        }
        return ast.Edge{ .refs = try refs.toOwnedSlice(self.alloc), .label = label };
    }

    // --- expressions ----------------------------------------------------- //

    fn expr(self: *Parser) ParseError!Expr {
        self.skipNl();
        const t = self.toks[self.i];
        switch (t.kind) {
            .STRING, .NUMBER, .PATH, .DURATION, .BYTES => {
                self.i += 1;
                return .{ .literal = makeLiteral(t) };
            },
            else => {},
        }
        if (isIdentTok(t, "true") or isIdentTok(t, "false")) {
            self.i += 1;
            return .{ .literal = .{ .kind = .BOOL, .value = t.value } };
        }
        if (isIdentTok(t, "null")) {
            self.i += 1;
            return .{ .literal = .{ .kind = .NULL, .value = "null" } };
        }
        if (self.isOp("[")) return .{ .list = try self.list() };
        if (self.isOp("{")) return .{ .record = try self.record() };
        if (t.kind == .IDENT) return .{ .app = try self.app() };
        return self.fail("an expression");
    }

    fn app(self: *Parser) ParseError!ast.App {
        const r = try self.ref();
        var args: ?[]const Expr = null;
        if (self.isOp("(")) args = try self.parenArgs();
        var rec: ?[]const Entry = null;
        if (self.isOp("{")) rec = (try self.record()).entries;
        return .{ .ref = r, .args = args, .record = rec };
    }

    fn parenArgs(self: *Parser) ParseError![]const Expr {
        _ = try self.expectOp("(");
        var args: std.ArrayList(Expr) = .empty;
        if (!self.isOp(")")) {
            try args.append(self.alloc, try self.expr());
            while (self.isOp(",")) {
                self.i += 1;
                try args.append(self.alloc, try self.expr());
            }
        }
        _ = try self.expectOp(")");
        return args.toOwnedSlice(self.alloc);
    }

    fn ref(self: *Parser) ParseError!Ref {
        self.skipNl();
        const t = self.toks[self.i];
        if (t.kind != .IDENT) return self.fail("a reference (identifier)");
        var parts: std.ArrayList([]const u8) = .empty;
        try parts.append(self.alloc, t.value);
        const start = t;
        var end = t;
        self.i += 1;
        while (self.isOp(".") and self.toks[self.i + 1].kind == .IDENT) {
            self.i += 1; // '.'
            const nt = self.toks[self.i];
            try parts.append(self.alloc, nt.value);
            end = nt;
            self.i += 1;
        }
        return .{
            .parts = try parts.toOwnedSlice(self.alloc),
            .byteStart = start.byteStart,
            .byteEnd = end.byteEnd,
            .line = start.line,
            .col = start.col,
        };
    }

    fn list(self: *Parser) ParseError!ast.ListLit {
        _ = try self.expectOp("[");
        var items: std.ArrayList(Expr) = .empty;
        if (!self.isOp("]")) {
            try items.append(self.alloc, try self.expr());
            while (self.isOp(",")) {
                self.i += 1;
                try items.append(self.alloc, try self.expr());
            }
        }
        _ = try self.expectOp("]");
        return .{ .items = try items.toOwnedSlice(self.alloc) };
    }

    fn record(self: *Parser) ParseError!ast.RecordLit {
        _ = try self.expectOp("{");
        var entries: std.ArrayList(Entry) = .empty;
        self.skipNl();
        while (!self.isOp("}")) {
            if (self.atEof()) return self.fail("'}' to close record");
            const t = self.toks[self.i];
            if (isIdentTok(t, "inherit")) {
                entries.append(self.alloc, .{ .inherit = try self.inheritStmt() }) catch return error.OutOfMemory;
            } else if (t.kind == .IDENT and self.lookaheadAssign()) {
                entries.append(self.alloc, .{ .assignment = try self.assignment() }) catch return error.OutOfMemory;
            } else {
                return self.fail("an assignment or `inherit` in a record");
            }
            self.skipNl();
        }
        self.i += 1; // '}'
        return .{ .entries = try entries.toOwnedSlice(self.alloc) };
    }

    // --- types ----------------------------------------------------------- //

    fn type_(self: *Parser) ParseError!ast.TypeRef {
        var parts: std.ArrayList([]const u8) = .empty;
        try parts.append(self.alloc, try self.typeAtom());
        while (self.isOp("|")) {
            self.i += 1;
            try parts.append(self.alloc, try self.typeAtom());
        }
        const text = try std.mem.join(self.alloc, " | ", parts.items);
        return .{ .text = text };
    }

    fn typeAtom(self: *Parser) ParseError![]const u8 {
        self.skipNl();
        if (self.isOp("(")) {
            self.i += 1;
            var inner: std.ArrayList([]const u8) = .empty;
            if (!self.isOp(")")) {
                try inner.append(self.alloc, (try self.type_()).text);
                while (self.isOp(",")) {
                    self.i += 1;
                    try inner.append(self.alloc, (try self.type_()).text);
                }
            }
            _ = try self.expectOp(")");
            _ = try self.expectOp("->");
            const r = (try self.type_()).text;
            const joined = try std.mem.join(self.alloc, ", ", inner.items);
            return std.fmt.allocPrint(self.alloc, "({s}) -> {s}", .{ joined, r });
        }
        // qualname
        const nm = try self.qualname();
        if (self.isOp("<")) {
            self.i += 1;
            var args: std.ArrayList([]const u8) = .empty;
            try args.append(self.alloc, (try self.type_()).text);
            while (self.isOp(",")) {
                self.i += 1;
                try args.append(self.alloc, (try self.type_()).text);
            }
            _ = try self.expectOp(">");
            const joined = try std.mem.join(self.alloc, ", ", args.items);
            return std.fmt.allocPrint(self.alloc, "{s}<{s}>", .{ nm, joined });
        }
        return nm;
    }

    fn qualname(self: *Parser) ParseError![]const u8 {
        const t = try self.expectIdent();
        var parts: std.ArrayList([]const u8) = .empty;
        try parts.append(self.alloc, t.value);
        while (self.isOp(".") and self.toks[self.i + 1].kind == .IDENT) {
            self.i += 1;
            try parts.append(self.alloc, self.toks[self.i].value);
            self.i += 1;
        }
        return std.mem.join(self.alloc, ".", parts.items);
    }
};

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //

/// Strip the surrounding double quotes from a STRING token value.
pub fn stripString(tokval: []const u8) []const u8 {
    if (tokval.len >= 2 and tokval[0] == '"' and tokval[tokval.len - 1] == '"') {
        return tokval[1 .. tokval.len - 1];
    }
    return tokval;
}

fn makeLiteral(t: Token) ast.Literal {
    if (t.kind == .STRING) return .{ .kind = .STRING, .value = stripString(t.value) };
    const lk: ast.LitKind = switch (t.kind) {
        .NUMBER => .NUMBER,
        .DURATION => .DURATION,
        .BYTES => .BYTES,
        .PATH => .PATH,
        else => .STRING, // unreachable for the literal-token set
    };
    return .{ .kind = lk, .value = t.value };
}

/// Python `repr()` of a short token value for the error message (human parity
/// only; stdout/exit code are gated, not stderr). Single-quoted, with basic
/// escaping. Best-effort.
fn pyRepr(alloc: std.mem.Allocator, s: []const u8) ![]const u8 {
    var buf: std.ArrayList(u8) = .empty;
    try buf.append(alloc, '\'');
    for (s) |c| {
        switch (c) {
            '\\' => try buf.appendSlice(alloc, "\\\\"),
            '\'' => try buf.appendSlice(alloc, "\\'"),
            '\n' => try buf.appendSlice(alloc, "\\n"),
            '\r' => try buf.appendSlice(alloc, "\\r"),
            '\t' => try buf.appendSlice(alloc, "\\t"),
            else => try buf.append(alloc, c),
        }
    }
    try buf.append(alloc, '\'');
    return buf.toOwnedSlice(alloc);
}

/// Parse a token list into a slice of top-level items. On a syntax error,
/// `err_out` (if non-null) is filled and `error.ParseFailed` is returned.
pub fn parse(alloc: std.mem.Allocator, toks: []const Token, filename: []const u8, err_out: ?*ErrInfo) ParseError![]const Item {
    var p = Parser{ .toks = toks, .file = filename, .alloc = alloc };
    return p.parseFile() catch |e| {
        if (err_out) |ptr| {
            if (p.err) |info| ptr.* = info;
        }
        return e;
    };
}
