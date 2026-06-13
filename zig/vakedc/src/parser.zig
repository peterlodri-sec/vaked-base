//! Vaked parser (v0.x subset) — recursive-descent over the lexer's token list.
//!
//! This is a DELIBERATE SUBSET of `vaked/grammar/vaked-v0-plus.ebnf`, chosen to
//! parse real hand-written examples (notably vaked/examples/swe-swarm-loadtest.vaked)
//! end to end while staying small enough to review. The subset, and where it
//! diverges from the reference grammar, is documented in
//! docs/compiler/ZIG_FRONTEND.md. Out-of-subset input produces a clear error
//! (we never silently accept).
//!
//! Subset grammar:
//!   file   = { item }
//!   item   = import | decl
//!   import = "use" string
//!   decl   = kind name block
//!   block  = "{" { stmt } "}"
//!   stmt   = decl | edge | assignment | app
//!   edge   = [ kindkw ] ref "->" ref { "->" ref }     // e.g. `mesh a -> b`
//!   assignment = ident ("="|"?=") expr
//!   app    = ref [ record ]                            // e.g. `policy { ... }`
//!   expr   = string | number | bool | null | list | app
//!   list   = "[" [ expr { "," expr } ] "]"
//!   record = "{" { assignment | app } "}"
//!   ref    = ident { "." ident }

const std = @import("std");
const lex = @import("lexer.zig");
const Token = lex.Token;
const TokenKind = lex.TokenKind;

/// The canonical declaration kinds (vaked-v0-plus.ebnf, `kind` production),
/// plus "ralphloop" from the docs/language design proposal so the Zig front-end
/// can parse the proposed example. Used only to disambiguate decl vs app/edge.
pub const kinds = [_][]const u8{
    "runtime",       "engine",   "host",       "network",
    "filesystem",    "mcp",      "ebpf",       "budget",
    "observability", "runclass", "workflow",   "index",
    "catalog",       "stream",   "fiber",      "surface",
    "mesh",          "device",   "mediaPipeline", "parallel",
    "schema",        "capability", "service",  "secret",
    "hostResource",  "ingress",  "container",  "memory",
    "ralphloop",
};

pub fn isKind(name: []const u8) bool {
    for (kinds) |k| {
        if (std.mem.eql(u8, k, name)) return true;
    }
    return false;
}

// ---- AST -------------------------------------------------------------------

pub const NodeKind = enum { import, decl, assignment, edge, app, list, literal, ref };

pub const Node = struct {
    kind: NodeKind,
    /// Primary text: the import path, decl kind, assignment target, etc.
    text: []const u8 = "",
    /// Secondary text: decl/app name, ref dotted path, literal kind tag.
    name: []const u8 = "",
    /// Child nodes: block stmts, list/record entries, edge endpoints, expr.
    children: std.ArrayList(*Node),

    fn create(a: std.mem.Allocator, kind: NodeKind) std.mem.Allocator.Error!*Node {
        const n = try a.create(Node);
        n.* = .{ .kind = kind, .children = std.ArrayList(*Node).init(a) };
        return n;
    }
};

pub const ParseError = error{UnexpectedToken} || std.mem.Allocator.Error;

pub const Parser = struct {
    a: std.mem.Allocator,
    toks: []const Token,
    i: usize = 0,
    /// Last error message (valid until the next parse call). Borrowed, static.
    err_msg: []const u8 = "",
    err_line: usize = 0,
    err_col: usize = 0,

    pub fn init(a: std.mem.Allocator, toks: []const Token) Parser {
        return .{ .a = a, .toks = toks };
    }

    fn cur(self: *Parser) Token {
        return self.toks[self.i];
    }

    fn at(self: *Parser, k: TokenKind) bool {
        return self.cur().kind == k;
    }

    fn atEof(self: *Parser) bool {
        return self.cur().kind == .eof;
    }

    fn isIdentText(self: *Parser, text: []const u8) bool {
        return self.at(.ident) and std.mem.eql(u8, self.cur().text, text);
    }

    fn fail(self: *Parser, msg: []const u8) ParseError {
        self.err_msg = msg;
        self.err_line = self.cur().line;
        self.err_col = self.cur().col;
        return error.UnexpectedToken;
    }

    fn expect(self: *Parser, k: TokenKind, msg: []const u8) ParseError!Token {
        if (!self.at(k)) return self.fail(msg);
        const t = self.cur();
        self.i += 1;
        return t;
    }

    // file = { item }
    pub fn parseFile(self: *Parser) ParseError!*Node {
        const file = try Node.create(self.a, .decl);
        file.text = "file";
        while (!self.atEof()) {
            const item = try self.parseItem();
            try file.children.append(item);
        }
        return file;
    }

    fn parseItem(self: *Parser) ParseError!*Node {
        if (self.isIdentText("use")) return self.parseImport();
        if (self.at(.ident) and isKind(self.cur().text)) return self.parseDecl();
        return self.fail("an item: `use <string>` or a `<kind> <name> { … }` declaration");
    }

    // import = "use" string
    fn parseImport(self: *Parser) ParseError!*Node {
        self.i += 1; // 'use'
        const s = try self.expect(.string, "a quoted import path after `use`");
        const n = try Node.create(self.a, .import);
        n.text = s.text;
        return n;
    }

    // decl = kind name block
    fn parseDecl(self: *Parser) ParseError!*Node {
        const kind_tok = self.cur();
        self.i += 1; // kind
        // name = ident | string
        if (!(self.at(.ident) or self.at(.string))) return self.fail("a name after the declaration kind");
        const name_tok = self.cur();
        self.i += 1;
        const n = try Node.create(self.a, .decl);
        n.text = kind_tok.text;
        n.name = name_tok.text;
        try self.parseBlock(n);
        return n;
    }

    // block = "{" { stmt } "}"  — appends stmts to `parent.children`.
    fn parseBlock(self: *Parser, parent: *Node) ParseError!void {
        _ = try self.expect(.lbrace, "`{` to open a block");
        while (!self.at(.rbrace)) {
            if (self.atEof()) return self.fail("`}` to close a block");
            const s = try self.parseStmt();
            try parent.children.append(s);
        }
        self.i += 1; // '}'
    }

    // stmt = decl | edge | assignment | app
    fn parseStmt(self: *Parser) ParseError!*Node {
        // decl: kind name "{"
        if (self.at(.ident) and isKind(self.cur().text) and self.declAhead()) {
            return self.parseDecl();
        }
        // edge (possibly tagged by a leading bare kind keyword, e.g. `mesh a -> b`)
        if (self.edgeAhead()) return self.parseEdge();
        // assignment: ident ("="|"?=")
        if (self.at(.ident) and self.assignAhead()) return self.parseAssignment();
        // app: ref [ record ]
        if (self.at(.ident)) return self.parseApp();
        return self.fail("a statement (declaration, edge, assignment, or call)");
    }

    /// Lookahead: kind name "{" / "(".
    fn declAhead(self: *Parser) bool {
        const j = self.i + 1;
        if (j >= self.toks.len) return false;
        const nt = self.toks[j];
        if (!(nt.kind == .ident or nt.kind == .string)) return false;
        const k = j + 1;
        if (k >= self.toks.len) return false;
        return self.toks[k].kind == .lbrace or self.toks[k].kind == .lparen;
    }

    /// Lookahead: ident ("="|"?=").
    fn assignAhead(self: *Parser) bool {
        const j = self.i + 1;
        if (j >= self.toks.len) return false;
        return self.toks[j].kind == .eq or self.toks[j].kind == .qeq;
    }

    /// Lookahead: a `->` appears after a leading ref, optionally after one bare
    /// kind keyword. Matches `a -> b`, `mesh a -> b`, `a.b -> c`.
    fn edgeAhead(self: *Parser) bool {
        var j = self.i;
        // optional leading bare kind keyword used as an edge tag (`mesh a -> b`)
        if (j < self.toks.len and self.toks[j].kind == .ident and isKind(self.toks[j].text)) {
            // only treat as a tag if it is NOT itself the ref target of an arrow
            const after = j + 1;
            if (after < self.toks.len and self.toks[after].kind == .ident) j += 1;
        }
        // skip a dotted ref
        if (j >= self.toks.len or self.toks[j].kind != .ident) return false;
        j += 1;
        while (j + 1 < self.toks.len and self.toks[j].kind == .dot and self.toks[j + 1].kind == .ident) j += 2;
        return j < self.toks.len and self.toks[j].kind == .arrow;
    }

    // edge = [ kindkw ] ref "->" ref { "->" ref }
    fn parseEdge(self: *Parser) ParseError!*Node {
        const n = try Node.create(self.a, .edge);
        // optional leading kind tag
        if (self.at(.ident) and isKind(self.cur().text)) {
            const after = self.i + 1;
            if (after < self.toks.len and self.toks[after].kind == .ident) {
                n.text = self.cur().text; // tag (e.g. "mesh")
                self.i += 1;
            }
        }
        const first = try self.parseRef();
        try n.children.append(first);
        while (self.at(.arrow)) {
            self.i += 1;
            const r = try self.parseRef();
            try n.children.append(r);
        }
        return n;
    }

    // assignment = ident ("="|"?=") expr
    fn parseAssignment(self: *Parser) ParseError!*Node {
        const target = self.cur();
        self.i += 1; // ident
        self.i += 1; // '=' or '?='
        const n = try Node.create(self.a, .assignment);
        n.text = target.text;
        const value = try self.parseExpr();
        try n.children.append(value);
        return n;
    }

    // app = ref [ record ]
    fn parseApp(self: *Parser) ParseError!*Node {
        const r = try self.parseRef();
        if (self.at(.lbrace)) {
            const app = try Node.create(self.a, .app);
            app.name = r.name;
            const rec = try self.parseRecord();
            try app.children.append(rec);
            return app;
        }
        return r;
    }

    // record = "{" { assignment | app } "}"  (returned as an .app node body)
    fn parseRecord(self: *Parser) ParseError!*Node {
        const rec = try Node.create(self.a, .app);
        rec.text = "record";
        _ = try self.expect(.lbrace, "`{` to open a record");
        while (!self.at(.rbrace)) {
            if (self.atEof()) return self.fail("`}` to close a record");
            if (self.at(.ident) and self.assignAhead()) {
                try rec.children.append(try self.parseAssignment());
            } else if (self.at(.ident)) {
                try rec.children.append(try self.parseApp());
            } else {
                return self.fail("an assignment or call inside a record");
            }
        }
        self.i += 1; // '}'
        return rec;
    }

    // expr = string | number | bool | null | list | app
    fn parseExpr(self: *Parser) ParseError!*Node {
        switch (self.cur().kind) {
            .string => {
                const t = self.cur();
                self.i += 1;
                const n = try Node.create(self.a, .literal);
                n.text = "string";
                n.name = t.text;
                return n;
            },
            .number => {
                const t = self.cur();
                self.i += 1;
                const n = try Node.create(self.a, .literal);
                n.text = "number";
                n.name = t.text;
                return n;
            },
            .lbracket => return self.parseList(),
            .ident => {
                // bool / null literals, else a ref/app
                if (std.mem.eql(u8, self.cur().text, "true") or std.mem.eql(u8, self.cur().text, "false")) {
                    const t = self.cur();
                    self.i += 1;
                    const n = try Node.create(self.a, .literal);
                    n.text = "bool";
                    n.name = t.text;
                    return n;
                }
                if (std.mem.eql(u8, self.cur().text, "null")) {
                    self.i += 1;
                    const n = try Node.create(self.a, .literal);
                    n.text = "null";
                    n.name = "null";
                    return n;
                }
                return self.parseApp();
            },
            else => return self.fail("an expression (string, number, bool, list, or reference)"),
        }
    }

    // list = "[" [ expr { "," expr } ] "]"
    fn parseList(self: *Parser) ParseError!*Node {
        const n = try Node.create(self.a, .list);
        self.i += 1; // '['
        if (!self.at(.rbracket)) {
            try n.children.append(try self.parseExpr());
            while (self.at(.comma)) {
                self.i += 1;
                if (self.at(.rbracket)) break; // tolerate a trailing comma
                try n.children.append(try self.parseExpr());
            }
        }
        _ = try self.expect(.rbracket, "`]` to close a list");
        return n;
    }

    // ref = ident { "." ident }
    fn parseRef(self: *Parser) ParseError!*Node {
        const first = try self.expect(.ident, "a reference (identifier)");
        const n = try Node.create(self.a, .ref);
        // Record the dotted path as a slice of the source spanning first..last.
        var end = first.text.ptr + first.text.len;
        while (self.at(.dot)) {
            self.i += 1; // '.'
            const part = try self.expect(.ident, "an identifier after `.`");
            end = part.text.ptr + part.text.len;
        }
        const len = @intFromPtr(end) - @intFromPtr(first.text.ptr);
        n.name = first.text.ptr[0..len];
        return n;
    }
};

/// Count the declarations and edges in a parsed file (used by `main` and tests).
pub const Summary = struct { decls: usize = 0, edges: usize = 0, imports: usize = 0 };

pub fn summarize(file: *const Node) Summary {
    var s = Summary{};
    for (file.children.items) |item| {
        switch (item.kind) {
            .import => s.imports += 1,
            .decl => {
                s.decls += 1;
                s.edges += countEdges(item);
            },
            else => {},
        }
    }
    return s;
}

fn countEdges(decl: *const Node) usize {
    var n: usize = 0;
    for (decl.children.items) |c| {
        if (c.kind == .edge) n += 1;
        if (c.kind == .decl) n += countEdges(c);
    }
    return n;
}

// ---- tests -----------------------------------------------------------------

const testing = std.testing;

fn parseSrc(a: std.mem.Allocator, src: []const u8) !*Node {
    var toks = std.ArrayList(Token).init(a);
    defer toks.deinit();
    try lex.tokenize(a, src, &toks);
    var p = Parser.init(a, toks.items);
    return p.parseFile();
}

test "parses a runtime with fibers and edges" {
    var arena = std.heap.ArenaAllocator.init(testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const src =
        \\use "./engines/zig.vaked"
        \\runtime "swe" {
        \\  systems = ["x86_64-linux"]
        \\  fiber coordinator {
        \\    engine = zigDaemon
        \\    policy { role = "coordinator" }
        \\  }
        \\  fiber worker_001 { engine = zigDaemon }
        \\  mesh coordinator -> worker_001
        \\  mesh worker_001 -> aggregator
        \\}
    ;
    const file = try parseSrc(a, src);
    const s = summarize(file);
    try testing.expectEqual(@as(usize, 1), s.imports);
    try testing.expectEqual(@as(usize, 1), s.decls); // the runtime
    try testing.expectEqual(@as(usize, 2), s.edges); // two mesh edges
}

test "dotted refs and lists parse" {
    var arena = std.heap.ArenaAllocator.init(testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const src =
        \\parallel "pool" {
        \\  fibers = [worker_001, worker_002, worker_003]
        \\  input = stream.workQueue
        \\  strategy = "concurrent"
        \\}
    ;
    const file = try parseSrc(a, src);
    try testing.expectEqual(@as(usize, 1), file.children.items.len);
}

test "out-of-subset input is rejected, not silently accepted" {
    var arena = std.heap.ArenaAllocator.init(testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    // A top-level bare expression is not a valid item.
    var toks = std.ArrayList(Token).init(a);
    try lex.tokenize(a, "42", &toks);
    var p = Parser.init(a, toks.items);
    try testing.expectError(error.UnexpectedToken, p.parseFile());
}
