//! Vaked lexer (v0.x subset) — turns UTF-8 source into a flat token list.
//!
//! Scope: the tokens needed by the v0.x parser subset (see parser.zig and
//! docs/compiler/ZIG_FRONTEND.md). Comments (`#` … end-of-line) and whitespace
//! are discarded. Newlines are NOT emitted as tokens: the v0.x parser is
//! structure-driven (brace/lookahead), which is a deliberate simplification of
//! the newline-terminated reference grammar — documented in the design note.
//!
//! Strings are lexed as a single STRING token spanning the quotes; the slice
//! includes the surrounding quotes and is left un-unescaped (the subset does
//! not interpret `\` escapes or `${}` interpolation).

const std = @import("std");

pub const TokenKind = enum {
    ident, // a-zA-Z then [a-zA-Z0-9_-]*  (also covers keywords; the parser
    //        decides whether an ident is a kind keyword)
    string, // "..."  (slice includes the quotes)
    number, // [-]digits[.digits]
    lbrace, // {
    rbrace, // }
    lbracket, // [
    rbracket, // ]
    lparen, // (
    rparen, // )
    eq, // =
    qeq, // ?=
    arrow, // ->
    dot, // .
    comma, // ,
    colon, // :
    at, // @
    lt, // <
    gt, // >
    pipe, // |
    semicolon, // ;
    eof,
};

pub const Token = struct {
    kind: TokenKind,
    /// Slice into the original source (no copy).
    text: []const u8,
    /// 1-based line and column of the first byte, for diagnostics.
    line: usize,
    col: usize,
};

pub const LexError = error{UnterminatedString} || std.mem.Allocator.Error;

const Lexer = struct {
    src: []const u8,
    i: usize = 0,
    line: usize = 1,
    col: usize = 1,

    fn peek(self: *Lexer) u8 {
        return if (self.i < self.src.len) self.src[self.i] else 0;
    }

    fn peekNext(self: *Lexer) u8 {
        return if (self.i + 1 < self.src.len) self.src[self.i + 1] else 0;
    }

    fn advance(self: *Lexer) u8 {
        const c = self.src[self.i];
        self.i += 1;
        if (c == '\n') {
            self.line += 1;
            self.col = 1;
        } else {
            self.col += 1;
        }
        return c;
    }

    fn isIdentStart(c: u8) bool {
        return std.ascii.isAlphabetic(c);
    }

    fn isIdentCont(c: u8) bool {
        return std.ascii.isAlphanumeric(c) or c == '_' or c == '-';
    }
};

/// Tokenize `src` into `out`. The caller owns `out` and must `deinit` it.
/// Returned token `text` slices point into `src`, so `src` must outlive them.
pub fn tokenize(allocator: std.mem.Allocator, src: []const u8, out: *std.ArrayList(Token)) LexError!void {
    var lx = Lexer{ .src = src };

    while (lx.i < lx.src.len) {
        const c = lx.peek();

        // Whitespace.
        if (c == ' ' or c == '\t' or c == '\r' or c == '\n') {
            _ = lx.advance();
            continue;
        }

        // Comment: `#` to end of line.
        if (c == '#') {
            while (lx.i < lx.src.len and lx.peek() != '\n') _ = lx.advance();
            continue;
        }

        const start = lx.i;
        const line = lx.line;
        const col = lx.col;

        // Identifier / keyword.
        if (Lexer.isIdentStart(c)) {
            _ = lx.advance();
            while (lx.i < lx.src.len and Lexer.isIdentCont(lx.peek())) _ = lx.advance();
            try out.append(.{ .kind = .ident, .text = src[start..lx.i], .line = line, .col = col });
            continue;
        }

        // Number ([-]?digits[.digits]). A bare '-' not followed by a digit is
        // handled by the '->' arrow case below, so we only enter here when a
        // digit follows.
        if (std.ascii.isDigit(c) or (c == '-' and std.ascii.isDigit(lx.peekNext()))) {
            _ = lx.advance(); // sign or first digit
            while (lx.i < lx.src.len and std.ascii.isDigit(lx.peek())) _ = lx.advance();
            if (lx.peek() == '.' and std.ascii.isDigit(lx.peekNext())) {
                _ = lx.advance(); // '.'
                while (lx.i < lx.src.len and std.ascii.isDigit(lx.peek())) _ = lx.advance();
            }
            try out.append(.{ .kind = .number, .text = src[start..lx.i], .line = line, .col = col });
            continue;
        }

        // String: "..." (no escape interpretation in the subset, but a '\'
        // escapes the next byte so an escaped quote does not end the string).
        if (c == '"') {
            _ = lx.advance(); // opening quote
            while (lx.i < lx.src.len and lx.peek() != '"') {
                if (lx.peek() == '\\' and lx.i + 1 < lx.src.len) {
                    _ = lx.advance(); // backslash
                }
                _ = lx.advance();
            }
            if (lx.i >= lx.src.len) return error.UnterminatedString;
            _ = lx.advance(); // closing quote
            try out.append(.{ .kind = .string, .text = src[start..lx.i], .line = line, .col = col });
            continue;
        }

        // Multi-char and single-char operators.
        const two: TokenKind = switch (c) {
            '-' => if (lx.peekNext() == '>') .arrow else .eof,
            '?' => if (lx.peekNext() == '=') .qeq else .eof,
            else => .eof,
        };
        if (two != .eof) {
            _ = lx.advance();
            _ = lx.advance();
            try out.append(.{ .kind = two, .text = src[start..lx.i], .line = line, .col = col });
            continue;
        }

        const one: ?TokenKind = switch (c) {
            '{' => .lbrace,
            '}' => .rbrace,
            '[' => .lbracket,
            ']' => .rbracket,
            '(' => .lparen,
            ')' => .rparen,
            '=' => .eq,
            '.' => .dot,
            ',' => .comma,
            ':' => .colon,
            '@' => .at,
            '<' => .lt,
            '>' => .gt,
            '|' => .pipe,
            ';' => .semicolon,
            else => null,
        };
        if (one) |k| {
            _ = lx.advance();
            try out.append(.{ .kind = k, .text = src[start..lx.i], .line = line, .col = col });
            continue;
        }

        // Unknown byte: skip it (the parser will surface structural errors).
        _ = lx.advance();
    }

    try out.append(.{ .kind = .eof, .text = "", .line = lx.line, .col = lx.col });
}

// ---- tests -----------------------------------------------------------------

test "tokenize a small declaration" {
    const src =
        \\use "./engines/zig.vaked"
        \\runtime "swe" {
        \\  systems = ["x86_64-linux"]
        \\  fiber coordinator { engine = zigDaemon }
        \\  mesh coordinator -> aggregator
        \\}
    ;
    var toks = std.ArrayList(Token).init(std.testing.allocator);
    defer toks.deinit();
    try tokenize(std.testing.allocator, src, &toks);

    // First token is the `use` keyword (an ident), last is eof.
    try std.testing.expectEqual(TokenKind.ident, toks.items[0].kind);
    try std.testing.expectEqualStrings("use", toks.items[0].text);
    try std.testing.expectEqual(TokenKind.eof, toks.items[toks.items.len - 1].kind);

    // The arrow must be lexed as a single token, not minus + gt.
    var saw_arrow = false;
    for (toks.items) |t| {
        if (t.kind == .arrow) saw_arrow = true;
    }
    try std.testing.expect(saw_arrow);
}

test "comments and strings are handled" {
    const src =
        \\# a comment
        \\name = "a string with -> arrow and # hash inside"
    ;
    var toks = std.ArrayList(Token).init(std.testing.allocator);
    defer toks.deinit();
    try tokenize(std.testing.allocator, src, &toks);
    // ident(name) eq string eof
    try std.testing.expectEqual(@as(usize, 4), toks.items.len);
    try std.testing.expectEqual(TokenKind.ident, toks.items[0].kind);
    try std.testing.expectEqual(TokenKind.eq, toks.items[1].kind);
    try std.testing.expectEqual(TokenKind.string, toks.items[2].kind);
}

test "unterminated string errors" {
    const src = "x = \"oops";
    var toks = std.ArrayList(Token).init(std.testing.allocator);
    defer toks.deinit();
    try std.testing.expectError(error.UnterminatedString, tokenize(std.testing.allocator, src, &toks));
}
