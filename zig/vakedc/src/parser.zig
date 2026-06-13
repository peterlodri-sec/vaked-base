const std = @import("std");
const ast = @import("ast.zig");
const lexer = @import("lexer.zig");
const Token = lexer.Token;
const TokenKind = lexer.TokenKind;
const Span = ast.Span;

// ---- Kind set ---------------------------------------------------------------
// Must match KINDS in the Python parser exactly.
const KINDS = [_][]const u8{
    "runtime", "engine",  "host",
    "network", "filesystem", "mcp", "ebpf",
    "budget",  "observability", "runclass", "workflow",
    "index",   "catalog", "stream", "fiber",
    "surface", "mesh",    "device", "mediaPipeline",
    "parallel","schema",  "capability",
    "service", "secret",  "hostResource", "ingress", "container",
    "memory",
};

fn isKind(s: []const u8) bool {
    for (KINDS) |k| {
        if (std.mem.eql(u8, s, k)) return true;
    }
    return false;
}

// ---- Error ------------------------------------------------------------------
pub const ParseError = error{
    UnexpectedToken,
    UnexpectedEof,
    OutOfMemory,
};

// ---- Parser struct ----------------------------------------------------------
pub const Parser = struct {
    tokens: []const Token,
    pos: usize,
    filename: []const u8,
    alloc: std.mem.Allocator,

    pub fn init(
        alloc: std.mem.Allocator,
        tokens: []const Token,
        filename: []const u8,
    ) Parser {
        return .{
            .tokens = tokens,
            .pos = 0,
            .filename = filename,
            .alloc = alloc,
        };
    }

    // ---- Cursor helpers ----------------------------------------------------

    fn cur(self: *Parser) Token {
        return self.tokens[self.pos];
    }

    fn peek(self: *Parser, offset: usize) Token {
        const p = self.pos + offset;
        if (p >= self.tokens.len) return self.tokens[self.tokens.len - 1]; // EOF
        return self.tokens[p];
    }

    fn atEof(self: *Parser) bool {
        return self.cur().kind == .eof;
    }

    fn isOp(self: *Parser, val: []const u8) bool {
        const t = self.cur();
        return t.kind == .op and std.mem.eql(u8, t.value, val);
    }

    fn isOpAt(self: *Parser, offset: usize, val: []const u8) bool {
        const t = self.peek(offset);
        return t.kind == .op and std.mem.eql(u8, t.value, val);
    }

    fn isIdent(self: *Parser, val: ?[]const u8) bool {
        const t = self.cur();
        if (t.kind != .ident) return false;
        if (val) |v| return std.mem.eql(u8, t.value, v);
        return true;
    }

    fn isIdentAt(self: *Parser, offset: usize, val: ?[]const u8) bool {
        const t = self.peek(offset);
        if (t.kind != .ident) return false;
        if (val) |v| return std.mem.eql(u8, t.value, v);
        return true;
    }

    fn skipNl(self: *Parser) void {
        while (self.pos < self.tokens.len and self.tokens[self.pos].kind == .newline) {
            self.pos += 1;
        }
    }

    fn advance(self: *Parser) Token {
        const t = self.tokens[self.pos];
        if (self.pos + 1 < self.tokens.len) self.pos += 1;
        return t;
    }

    fn expectOp(self: *Parser, val: []const u8) ParseError!Token {
        self.skipNl();
        const t = self.cur();
        if (t.kind == .op and std.mem.eql(u8, t.value, val)) {
            self.pos += 1;
            return t;
        }
        return ParseError.UnexpectedToken;
    }

    fn expectIdent(self: *Parser) ParseError!Token {
        self.skipNl();
        const t = self.cur();
        if (t.kind == .ident) {
            self.pos += 1;
            return t;
        }
        return ParseError.UnexpectedToken;
    }

    // ---- Entry point -------------------------------------------------------

    pub fn parseFile(self: *Parser) ParseError!ast.File {
        var items = std.ArrayList(ast.Item).init(self.alloc);
        self.skipNl();
        while (!self.atEof()) {
            const item = try self.parseItem();
            try items.append(item);
            self.skipNl();
        }
        return ast.File{
            .items = try items.toOwnedSlice(),
            .source_file = self.filename,
        };
    }

    fn parseItem(self: *Parser) ParseError!ast.Item {
        self.skipNl();
        if (self.isIdent("use")) {
            const imp = try self.parseImport();
            return ast.Item{ .import_decl = imp };
        }
        const d = try self.parseDecl();
        return ast.Item{ .decl = d };
    }

    // import = "use" string ;
    fn parseImport(self: *Parser) ParseError!ast.Import {
        const kw = self.advance(); // "use"
        // no skipNl — string should be on the same line
        const t = self.cur();
        if (t.kind != .string) return ParseError.UnexpectedToken;
        self.pos += 1;
        const path = stripString(t.value);
        return ast.Import{
            .path = path,
            .span = Span{
                .byte_start = kw.span.byte_start,
                .byte_end = t.span.byte_end,
                .line = kw.span.line,
                .col = kw.span.col,
            },
        };
    }

    // decl = { annotation } kind name [ signature ] block ;
    fn parseDecl(self: *Parser) ParseError!ast.Decl {
        self.skipNl();
        var annotations = std.ArrayList(ast.Annotation).init(self.alloc);
        while (self.isOp("@")) {
            try annotations.append(try self.parseAnnotation());
            self.skipNl();
        }
        const kw = self.cur();
        if (kw.kind != .ident or !isKind(kw.value)) {
            return ParseError.UnexpectedToken;
        }
        self.pos += 1;
        const name = try self.parseName();
        var signature: ?ast.Signature = null;
        if (self.isOp("(")) {
            signature = try self.parseSignature();
        }
        const body_result = try self.parseBlock();
        return ast.Decl{
            .kind = kw.value,
            .name = name,
            .annotations = try annotations.toOwnedSlice(),
            .signature = signature,
            .body = body_result.stmts,
            .span = Span{
                .byte_start = kw.span.byte_start,
                .byte_end = body_result.close_byte_end,
                .line = kw.span.line,
                .col = kw.span.col,
            },
        };
    }

    // name = ident | string ;
    fn parseName(self: *Parser) ParseError![]const u8 {
        self.skipNl();
        const t = self.cur();
        if (t.kind == .ident) {
            self.pos += 1;
            return t.value;
        }
        if (t.kind == .string) {
            self.pos += 1;
            return stripString(t.value);
        }
        return ParseError.UnexpectedToken;
    }

    // annotation = "@" ident [ "(" [ arg { "," arg } ] ")" ] ;
    fn parseAnnotation(self: *Parser) ParseError!ast.Annotation {
        _ = try self.expectOp("@");
        const name = try self.expectIdent();
        var args: ?[]ast.Expr = null;
        if (self.isOp("(")) {
            args = try self.parseParenArgs();
        }
        return ast.Annotation{ .name = name.value, .args = args };
    }

    // signature = "(" [ param { "," param } ] ")" [ "->" type ] ;
    fn parseSignature(self: *Parser) ParseError!ast.Signature {
        _ = try self.expectOp("(");
        var params = std.ArrayList(ast.Param).init(self.alloc);
        if (!self.isOp(")")) {
            try params.append(try self.parseParam());
            while (self.isOp(",")) {
                self.pos += 1;
                try params.append(try self.parseParam());
            }
        }
        _ = try self.expectOp(")");
        var ret: ?ast.TypeRef = null;
        if (self.isOp("->")) {
            self.pos += 1;
            ret = try self.parseType();
        }
        return ast.Signature{ .params = try params.toOwnedSlice(), .ret = ret };
    }

    // param = ident ":" type [ "=" expr ] ;
    fn parseParam(self: *Parser) ParseError!ast.Param {
        const name = try self.expectIdent();
        _ = try self.expectOp(":");
        const ty = try self.parseType();
        var default: ?*ast.Expr = null;
        if (self.isOp("=")) {
            self.pos += 1;
            const expr = try self.alloc.create(ast.Expr);
            expr.* = try self.parseExpr();
            default = expr;
        }
        return ast.Param{ .name = name.value, .type_ref = ty, .default = default };
    }

    // ---- Block & statements ------------------------------------------------

    const BlockResult = struct {
        stmts: []ast.Stmt,
        close_byte_end: u32,
    };

    // block = "{" { stmt } "}" ;
    fn parseBlock(self: *Parser) ParseError!BlockResult {
        self.skipNl();
        _ = try self.expectOp("{");
        var stmts = std.ArrayList(ast.Stmt).init(self.alloc);
        self.skipNl();
        while (!self.isOp("}")) {
            if (self.atEof()) return ParseError.UnexpectedEof;
            try stmts.append(try self.parseStmt());
            self.skipNl();
        }
        const close = self.cur();
        self.pos += 1; // consume '}'
        return BlockResult{
            .stmts = try stmts.toOwnedSlice(),
            .close_byte_end = close.span.byte_end,
        };
    }

    // stmt = field_decl | grant_decl | order_decl | assignment | open_decl
    //      | inherit_stmt | edge | node_decl | decl | app  (ORDERED)
    fn parseStmt(self: *Parser) ParseError!ast.Stmt {
        self.skipNl();
        const t = self.cur();

        // field_decl: "field" ident ":"
        if (t.kind == .ident and std.mem.eql(u8, t.value, "field") and self.lookaheadField()) {
            return ast.Stmt{ .field_decl = try self.parseFieldDecl() };
        }

        // grant_decl: "grant" ident
        if (t.kind == .ident and std.mem.eql(u8, t.value, "grant") and self.lookaheadGrant()) {
            return ast.Stmt{ .grant_decl = try self.parseGrantDecl() };
        }

        // order_decl: "order" ident "<"
        if (t.kind == .ident and std.mem.eql(u8, t.value, "order") and self.lookaheadOrder()) {
            return ast.Stmt{ .order_decl = try self.parseOrderDecl() };
        }

        // assignment: ident assign_op expr  (bare ident, not dotted)
        if (t.kind == .ident and self.lookaheadAssign()) {
            return ast.Stmt{ .assignment = try self.parseAssignment() };
        }

        // open_decl: bare "open" (not followed by assign_op)
        if (t.kind == .ident and std.mem.eql(u8, t.value, "open")) {
            self.pos += 1;
            return ast.Stmt{ .open_decl = {} };
        }

        // inherit_stmt = "inherit" ident { ident }
        if (t.kind == .ident and std.mem.eql(u8, t.value, "inherit")) {
            return ast.Stmt{ .inherit = try self.parseInheritStmt() };
        }

        // edge: try ref "->" (backtrack if not)
        if (t.kind == .ident) {
            if (try self.tryEdge()) |edge| {
                return ast.Stmt{ .edge = edge };
            }
        }

        // node_decl: "node" name "{"
        if (t.kind == .ident and std.mem.eql(u8, t.value, "node") and self.lookaheadNode()) {
            return ast.Stmt{ .node_decl = try self.parseNodeDecl() };
        }

        // decl: { "@" } kind name ( "{" | "(" )
        if (self.isOp("@") or (t.kind == .ident and isKind(t.value) and self.lookaheadDecl())) {
            return ast.Stmt{ .decl = try self.parseDecl() };
        }

        // app: ref [ "(" args ")" ] [ record ]
        if (t.kind == .ident) {
            return ast.Stmt{ .app = try self.parseApp() };
        }

        return ParseError.UnexpectedToken;
    }

    // ---- Lookahead predicates ----------------------------------------------

    fn lookaheadField(self: *Parser) bool {
        // "field" ident ":"
        if (self.peek(1).kind != .ident) return false;
        return self.isOpAt(2, ":");
    }

    fn lookaheadGrant(self: *Parser) bool {
        // "grant" ident
        return self.peek(1).kind == .ident;
    }

    fn lookaheadOrder(self: *Parser) bool {
        // "order" ident "<"
        if (self.peek(1).kind != .ident) return false;
        return self.isOpAt(2, "<");
    }

    fn lookaheadAssign(self: *Parser) bool {
        // ident ("=" | "?=")
        const next = self.peek(1);
        if (next.kind != .op) return false;
        return std.mem.eql(u8, next.value, "=") or std.mem.eql(u8, next.value, "?=");
    }

    fn lookaheadNode(self: *Parser) bool {
        // "node" name "{"
        const nt = self.peek(1);
        if (nt.kind != .ident and nt.kind != .string) return false;
        return self.isOpAt(2, "{");
    }

    fn lookaheadDecl(self: *Parser) bool {
        // kind name ( "{" | "(" )
        const nt = self.peek(1);
        if (nt.kind != .ident and nt.kind != .string) return false;
        return self.isOpAt(2, "{") or self.isOpAt(2, "(");
    }

    // ---- Statement forms ---------------------------------------------------

    // field_decl = "field" ident ":" type [ "{" { refinement } "}" ] ;
    fn parseFieldDecl(self: *Parser) ParseError!ast.FieldDecl {
        self.pos += 1; // "field"
        const name = try self.expectIdent();
        _ = try self.expectOp(":");
        const ty = try self.parseType();
        var refinements = std.ArrayList(ast.Refinement).init(self.alloc);
        if (self.isOp("{")) {
            self.pos += 1;
            self.skipNl();
            while (!self.isOp("}")) {
                if (self.atEof()) return ParseError.UnexpectedEof;
                try refinements.append(try self.parseRefinement());
                self.skipNl();
            }
            self.pos += 1; // '}'
        }
        return ast.FieldDecl{
            .name = name.value,
            .type_ref = ty,
            .refinements = try refinements.toOwnedSlice(),
        };
    }

    fn parseRefinement(self: *Parser) ParseError!ast.Refinement {
        self.skipNl();
        const t = self.cur();
        if (t.kind == .ident) {
            if (std.mem.eql(u8, t.value, "required")) {
                self.pos += 1;
                return ast.Refinement{ .required = {} };
            }
            if (std.mem.eql(u8, t.value, "optional")) {
                self.pos += 1;
                return ast.Refinement{ .optional = {} };
            }
            if (std.mem.eql(u8, t.value, "nonempty")) {
                self.pos += 1;
                return ast.Refinement{ .nonempty = {} };
            }
            if (std.mem.eql(u8, t.value, "default")) {
                self.pos += 1;
                _ = try self.expectOp("=");
                const expr = try self.alloc.create(ast.Expr);
                expr.* = try self.parseExpr();
                return ast.Refinement{ .default = expr };
            }
            if (std.mem.eql(u8, t.value, "oneof")) {
                self.pos += 1;
                const items = try self.parseList();
                return ast.Refinement{ .oneof = items };
            }
            if (std.mem.eql(u8, t.value, "matches")) {
                self.pos += 1;
                self.skipNl();
                const r = self.cur();
                if (r.kind != .regex) return ParseError.UnexpectedToken;
                self.pos += 1;
                return ast.Refinement{ .matches = r.value };
            }
            if (std.mem.eql(u8, t.value, "in")) {
                self.pos += 1;
                const lo = try self.expectNumber();
                _ = try self.expectOp("..");
                const hi = try self.expectNumber();
                return ast.Refinement{ .range = .{ .lo = lo, .hi = hi } };
            }
        }
        // cmp: ( ">=" | "<=" | ">" | "<" ) number
        if (t.kind == .op) {
            const ops = [_][]const u8{ "<=", ">=", "<", ">" };
            for (ops) |op| {
                if (std.mem.eql(u8, t.value, op)) {
                    self.pos += 1;
                    const num = try self.expectNumber();
                    const cmp_op: ast.CmpOp = if (std.mem.eql(u8, op, "<=")) .lte
                        else if (std.mem.eql(u8, op, ">=")) .gte
                        else if (std.mem.eql(u8, op, "<")) .lt
                        else .gt;
                    return ast.Refinement{ .cmp = .{ .op = cmp_op, .number = num } };
                }
            }
        }
        return ParseError.UnexpectedToken;
    }

    fn expectNumber(self: *Parser) ParseError![]const u8 {
        self.skipNl();
        const t = self.cur();
        if (t.kind != .number) return ParseError.UnexpectedToken;
        self.pos += 1;
        return t.value;
    }

    // grant_decl = "grant" ident { ident } ; line-bounded
    fn parseGrantDecl(self: *Parser) ParseError!ast.GrantDecl {
        self.pos += 1; // "grant"
        var names = std.ArrayList([]const u8).init(self.alloc);
        // first ident required (ensured by lookahead)
        const first = try self.expectIdent();
        try names.append(first.value);
        // { ident } line-bounded: do NOT skip NEWLINE
        while (self.cur().kind == .ident) {
            try names.append(self.cur().value);
            self.pos += 1;
        }
        return ast.GrantDecl{ .names = try names.toOwnedSlice() };
    }

    // order_decl = "order" order_chain { ";" order_chain } ;
    fn parseOrderDecl(self: *Parser) ParseError!ast.OrderDecl {
        self.pos += 1; // "order"
        var chains = std.ArrayList(ast.OrderChain).init(self.alloc);
        try chains.append(try self.parseOrderChain());
        while (self.isOp(";")) {
            self.pos += 1; // ";"
            self.skipNl(); // ";" absorbs trailing newlines
            try chains.append(try self.parseOrderChain());
        }
        return ast.OrderDecl{ .chains = try chains.toOwnedSlice() };
    }

    // order_chain = ident "<" ident { "<" ident } ; line-bounded
    fn parseOrderChain(self: *Parser) ParseError!ast.OrderChain {
        var names = std.ArrayList([]const u8).init(self.alloc);
        const t = self.cur();
        if (t.kind != .ident) return ParseError.UnexpectedToken;
        try names.append(t.value);
        self.pos += 1;
        if (!self.isOp("<")) return ParseError.UnexpectedToken;
        while (self.isOp("<")) {
            self.pos += 1; // "<"
            const n = self.cur();
            if (n.kind != .ident) return ParseError.UnexpectedToken;
            try names.append(n.value);
            self.pos += 1;
        }
        return names.toOwnedSlice();
    }

    // inherit_stmt = "inherit" ident { ident } ; line-bounded
    fn parseInheritStmt(self: *Parser) ParseError!ast.InheritStmt {
        self.pos += 1; // "inherit"
        var names = std.ArrayList([]const u8).init(self.alloc);
        const first = try self.expectIdent();
        try names.append(first.value);
        // line-bounded: do NOT skip NEWLINE
        while (self.cur().kind == .ident) {
            try names.append(self.cur().value);
            self.pos += 1;
        }
        return ast.InheritStmt{ .names = try names.toOwnedSlice() };
    }

    // assignment = ident assign_op expr ;
    fn parseAssignment(self: *Parser) ParseError!ast.Assignment {
        const target = self.cur().value;
        self.pos += 1;
        const op = self.cur().value; // "=" or "?="
        self.pos += 1;
        const val = try self.alloc.create(ast.Expr);
        val.* = try self.parseExpr();
        return ast.Assignment{ .target = target, .op = op, .value = val };
    }

    // node_decl = "node" name block ;
    fn parseNodeDecl(self: *Parser) ParseError!ast.NodeDecl {
        const kw = self.cur();
        self.pos += 1; // "node"
        const name = try self.parseName();
        const body_result = try self.parseBlock();
        return ast.NodeDecl{
            .name = name,
            .body = body_result.stmts,
            .span = Span{
                .byte_start = kw.span.byte_start,
                .byte_end = body_result.close_byte_end,
                .line = kw.span.line,
                .col = kw.span.col,
            },
        };
    }

    // edge = ref "->" ref { "->" ref } [ ":" string ] ;  (try, backtrack)
    fn tryEdge(self: *Parser) ParseError!?ast.Edge {
        const save = self.pos;
        const first = self.parseRef() catch {
            self.pos = save;
            return null;
        };
        if (!self.isOp("->")) {
            self.pos = save;
            return null;
        }
        var refs = std.ArrayList(ast.Ref).init(self.alloc);
        try refs.append(first);
        while (self.isOp("->")) {
            self.pos += 1;
            try refs.append(try self.parseRef());
        }
        var label: ?[]const u8 = null;
        if (self.isOp(":")) {
            self.pos += 1;
            self.skipNl();
            const t = self.cur();
            if (t.kind != .string) return ParseError.UnexpectedToken;
            self.pos += 1;
            label = stripString(t.value);
        }
        return ast.Edge{ .refs = try refs.toOwnedSlice(), .label = label };
    }

    // ---- Expressions -------------------------------------------------------

    // expr = literal | list | record | app ;
    fn parseExpr(self: *Parser) ParseError!ast.Expr {
        self.skipNl();
        const t = self.cur();
        // Literal kinds: string, number, path, duration, bytes
        if (t.kind == .string) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{
                .kind = .string,
                .value = stripString(t.value),
                .span = t.span,
            }};
        }
        if (t.kind == .number) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{ .kind = .number, .value = t.value, .span = t.span }};
        }
        if (t.kind == .path) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{ .kind = .path, .value = t.value, .span = t.span }};
        }
        if (t.kind == .duration) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{ .kind = .duration, .value = t.value, .span = t.span }};
        }
        if (t.kind == .bytes) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{ .kind = .bytes, .value = t.value, .span = t.span }};
        }
        // bool / null
        if (t.kind == .ident and (std.mem.eql(u8, t.value, "true") or std.mem.eql(u8, t.value, "false"))) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{ .kind = .bool_lit, .value = t.value, .span = t.span }};
        }
        if (t.kind == .ident and std.mem.eql(u8, t.value, "null")) {
            self.pos += 1;
            return ast.Expr{ .literal = ast.Literal{ .kind = .null_lit, .value = "null", .span = t.span }};
        }
        // list
        if (self.isOp("[")) {
            const items = try self.parseList();
            return ast.Expr{ .list = items };
        }
        // record
        if (self.isOp("{")) {
            const rec = try self.parseRecord();
            return ast.Expr{ .record = rec };
        }
        // app (ref + optional args + optional record)
        if (t.kind == .ident) {
            return ast.Expr{ .app = try self.parseApp() };
        }
        return ParseError.UnexpectedToken;
    }

    // app = ref [ "(" [ arg { "," arg } ] ")" ] [ record ] ;
    fn parseApp(self: *Parser) ParseError!ast.App {
        const ref = try self.parseRef();
        var args: ?[]ast.Expr = null;
        if (self.isOp("(")) {
            args = try self.parseParenArgs();
        }
        var record: ?[]ast.RecordEntry = null;
        if (self.isOp("{")) {
            record = try self.parseRecord();
        }
        return ast.App{ .ref = ref, .args = args, .record = record };
    }

    fn parseParenArgs(self: *Parser) ParseError![]ast.Expr {
        _ = try self.expectOp("(");
        var args = std.ArrayList(ast.Expr).init(self.alloc);
        if (!self.isOp(")")) {
            try args.append(try self.parseExpr());
            while (self.isOp(",")) {
                self.pos += 1;
                try args.append(try self.parseExpr());
            }
        }
        _ = try self.expectOp(")");
        return args.toOwnedSlice();
    }

    // ref = ident { "." ident } ;
    fn parseRef(self: *Parser) ParseError!ast.Ref {
        self.skipNl();
        const t = self.cur();
        if (t.kind != .ident) return ParseError.UnexpectedToken;
        var parts = std.ArrayList([]const u8).init(self.alloc);
        try parts.append(t.value);
        const start = t;
        var end = t;
        self.pos += 1;
        while (self.isOp(".") and self.peek(1).kind == .ident) {
            self.pos += 1; // "."
            const nt = self.cur();
            try parts.append(nt.value);
            end = nt;
            self.pos += 1;
        }
        return ast.Ref{
            .parts = try parts.toOwnedSlice(),
            .span = Span{
                .byte_start = start.span.byte_start,
                .byte_end = end.span.byte_end,
                .line = start.span.line,
                .col = start.span.col,
            },
        };
    }

    // list = "[" [ expr { "," expr } ] "]" ;
    fn parseList(self: *Parser) ParseError![]ast.Expr {
        _ = try self.expectOp("[");
        var items = std.ArrayList(ast.Expr).init(self.alloc);
        if (!self.isOp("]")) {
            try items.append(try self.parseExpr());
            while (self.isOp(",")) {
                self.pos += 1;
                if (self.isOp("]")) break; // tolerate trailing comma
                try items.append(try self.parseExpr());
            }
        }
        _ = try self.expectOp("]");
        return items.toOwnedSlice();
    }

    // record = "{" { assignment | inherit_stmt } "}" ;
    fn parseRecord(self: *Parser) ParseError![]ast.RecordEntry {
        _ = try self.expectOp("{");
        var entries = std.ArrayList(ast.RecordEntry).init(self.alloc);
        self.skipNl();
        while (!self.isOp("}")) {
            if (self.atEof()) return ParseError.UnexpectedEof;
            const t = self.cur();
            if (t.kind == .ident and std.mem.eql(u8, t.value, "inherit")) {
                try entries.append(ast.RecordEntry{ .inherit = try self.parseInheritStmt() });
            } else if (t.kind == .ident and self.lookaheadAssign()) {
                try entries.append(ast.RecordEntry{ .assignment = try self.parseAssignment() });
            } else {
                return ParseError.UnexpectedToken;
            }
            self.skipNl();
        }
        self.pos += 1; // '}'
        return entries.toOwnedSlice();
    }

    // ---- Types -------------------------------------------------------------

    // type = type_atom { "|" type_atom } ; stored as flat text
    fn parseType(self: *Parser) ParseError!ast.TypeRef {
        var buf = std.ArrayList(u8).init(self.alloc);
        const first = try self.parseTypeAtom();
        try buf.appendSlice(first);
        while (self.isOp("|")) {
            self.pos += 1;
            try buf.appendSlice(" | ");
            const next = try self.parseTypeAtom();
            try buf.appendSlice(next);
        }
        return ast.TypeRef{ .text = try buf.toOwnedSlice() };
    }

    fn parseTypeAtom(self: *Parser) ParseError![]const u8 {
        self.skipNl();
        var buf = std.ArrayList(u8).init(self.alloc);
        if (self.isOp("(")) {
            // "(" [ type { "," type } ] ")" "->" type
            self.pos += 1;
            try buf.appendSlice("(");
            if (!self.isOp(")")) {
                const t = try self.parseType();
                try buf.appendSlice(t.text);
                while (self.isOp(",")) {
                    self.pos += 1;
                    try buf.appendSlice(", ");
                    const nt = try self.parseType();
                    try buf.appendSlice(nt.text);
                }
            }
            _ = try self.expectOp(")");
            try buf.appendSlice(")");
            _ = try self.expectOp("->");
            try buf.appendSlice(" -> ");
            const ret = try self.parseType();
            try buf.appendSlice(ret.text);
            return buf.toOwnedSlice();
        }
        // qualname [ "<" type { "," type } ">" ]
        const qn = try self.parseQualname();
        try buf.appendSlice(qn);
        if (self.isOp("<")) {
            self.pos += 1;
            try buf.appendSlice("<");
            const a = try self.parseType();
            try buf.appendSlice(a.text);
            while (self.isOp(",")) {
                self.pos += 1;
                try buf.appendSlice(", ");
                const b = try self.parseType();
                try buf.appendSlice(b.text);
            }
            _ = try self.expectOp(">");
            try buf.appendSlice(">");
        }
        return buf.toOwnedSlice();
    }

    fn parseQualname(self: *Parser) ParseError![]const u8 {
        const t = try self.expectIdent();
        var buf = std.ArrayList(u8).init(self.alloc);
        try buf.appendSlice(t.value);
        while (self.isOp(".") and self.peek(1).kind == .ident) {
            self.pos += 1;
            try buf.appendSlice(".");
            try buf.appendSlice(self.cur().value);
            self.pos += 1;
        }
        return buf.toOwnedSlice();
    }
};

// ---- Helpers ----------------------------------------------------------------

fn stripString(v: []const u8) []const u8 {
    if (v.len >= 2 and v[0] == '"' and v[v.len - 1] == '"') {
        return v[1 .. v.len - 1];
    }
    return v;
}

// ---- Entry point -----------------------------------------------------------

pub fn parse(
    alloc: std.mem.Allocator,
    tokens: []const Token,
    filename: []const u8,
) ParseError!ast.File {
    var p = Parser.init(alloc, tokens, filename);
    return p.parseFile();
}

test "parse empty file" {
    const alloc = std.testing.allocator;
    const toks = try @import("lexer.zig").tokenize(alloc, "", "<test>");
    defer alloc.free(toks);
    var arena = std.heap.ArenaAllocator.init(alloc);
    defer arena.deinit();
    const file = try parse(arena.allocator(), toks, "<test>");
    try std.testing.expectEqual(@as(usize, 0), file.items.len);
}
