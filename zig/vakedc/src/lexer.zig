const std = @import("std");
const ast = @import("ast.zig");
const Span = ast.Span;

// ---- Token kinds ------------------------------------------------------------

pub const TokenKind = enum {
    ident,
    string,
    number,
    duration,
    bytes,
    path,
    regex,
    op,
    newline,
    eof,
};

// EnumArray gives exhaustiveness: every new TokenKind must get a name here.
pub const TOKEN_KIND_NAMES = std.enums.EnumArray(TokenKind, []const u8).init(.{
    .ident    = "IDENT",
    .string   = "STRING",
    .number   = "NUMBER",
    .duration = "DURATION",
    .bytes    = "BYTES",
    .path     = "PATH",
    .regex    = "REGEX",
    .op       = "OP",
    .newline  = "NEWLINE",
    .eof      = "EOF",
});

// ---- Token ------------------------------------------------------------------

pub const Token = struct {
    kind: TokenKind,
    value: []const u8,
    span: Span,
};

// ---- Errors -----------------------------------------------------------------

pub const LexError = error{
    UnexpectedCharacter,
    UnterminatedString,
    UnterminatedRegex,
    UnterminatedEscape,
    InvalidRegexPosition,
    OutOfMemory,
};

// ---- Helper predicates ------------------------------------------------------

fn isLetter(c: u8) bool {
    return (c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z');
}

fn isDigit(c: u8) bool {
    return c >= '0' and c <= '9';
}

fn isIdentPart(c: u8) bool {
    return isLetter(c) or isDigit(c) or c == '_' or c == '-';
}

fn isPathChar(c: u8) bool {
    return isLetter(c) or isDigit(c) or c == '/' or c == '_' or c == '-' or c == '.';
}

// ---- Multi-char ops (longest-first order, matches Python lexer) -------------
// "->", "<=", ">=", "..", "?="
const MULTI_OPS = [_][]const u8{ "->", "<=", ">=", "..", "?=" };

// Duration units (longest first for correct longest-match)
const DURATION_UNITS = [_][]const u8{ "ns", "us", "ms", "s", "m", "h", "d" };

// Byte units (longest first for correct longest-match)
const BYTE_UNITS = [_][]const u8{ "TB", "GB", "MB", "KB", "B" };

fn matchUnit(src: []const u8, pos: usize, units: []const []const u8) ?[]const u8 {
    var best: ?[]const u8 = null;
    for (units) |u| {
        if (pos + u.len <= src.len and std.mem.eql(u8, src[pos .. pos + u.len], u)) {
            if (best == null or u.len > best.?.len) {
                best = u;
            }
        }
    }
    return best;
}

// ---- Tokenizer state --------------------------------------------------------

const Tokenizer = struct {
    src: []const u8,
    filename: []const u8,
    pos: usize,
    line: u32,
    col: u32,
    group_depth: u32,
    // last significant (non-NEWLINE) token index in output, or null
    last_sig_idx: ?usize,

    fn init(src: []const u8, filename: []const u8) Tokenizer {
        return .{
            .src = src,
            .filename = filename,
            .pos = 0,
            .line = 1,
            .col = 1,
            .group_depth = 0,
            .last_sig_idx = null,
        };
    }

    fn cur(self: *Tokenizer) u8 {
        return self.src[self.pos];
    }

    fn peek(self: *Tokenizer, offset: usize) ?u8 {
        const p = self.pos + offset;
        if (p >= self.src.len) return null;
        return self.src[p];
    }

    fn advance(self: *Tokenizer) void {
        if (self.pos < self.src.len) {
            if (self.src[self.pos] == '\n') {
                self.line += 1;
                self.col = 1;
            } else {
                self.col += 1;
            }
            self.pos += 1;
        }
    }

    fn advanceN(self: *Tokenizer, n: usize) void {
        var i: usize = 0;
        while (i < n) : (i += 1) self.advance();
    }
};

// ---- Main tokenize function -------------------------------------------------

pub fn tokenize(
    alloc: std.mem.Allocator,
    src: []const u8,
    filename: []const u8,
) LexError![]Token {
    var tz = Tokenizer.init(src, filename);
    var toks = std.ArrayList(Token).init(alloc);

    // pending_newline: a NEWLINE is queued but not yet emitted.
    var pending_newline = false;
    var pending_nl_line: u32 = 0;
    var pending_nl_col: u32 = 0;
    var pending_nl_byte: u32 = 0;

    // Helper to flush a pending newline into the list (if the last emitted
    // token is not already a NEWLINE).
    const flushNewline = struct {
        fn call(
            list: *std.ArrayList(Token),
            pnl: *bool,
            nl_byte: u32,
            nl_line: u32,
            nl_col: u32,
        ) !void {
            if (!pnl.*) return;
            // Only emit if last token isn't already a NEWLINE.
            if (list.items.len > 0 and list.items[list.items.len - 1].kind == .newline) {
                pnl.* = false;
                return;
            }
            const span = Span{
                .byte_start = nl_byte,
                .byte_end = nl_byte,
                .line = nl_line,
                .col = nl_col,
            };
            try list.append(.{ .kind = .newline, .value = "\\n", .span = span });
            pnl.* = false;
        }
    }.call;

    while (tz.pos < src.len) {
        const c = tz.cur();
        const tline = tz.line;
        const tcol = tz.col;
        const tbyte: u32 = @intCast(tz.pos);

        // Whitespace (space, tab, CR)
        if (c == ' ' or c == '\t' or c == '\r') {
            tz.advance();
            continue;
        }

        // Newline
        if (c == '\n') {
            if (tz.group_depth == 0 and !pending_newline) {
                pending_newline = true;
                pending_nl_byte = tbyte;
                pending_nl_line = tline;
                pending_nl_col = tcol;
            }
            tz.advance();
            continue;
        }

        // Comment: '#' to end of line (discard)
        if (c == '#') {
            while (tz.pos < src.len and tz.cur() != '\n') {
                tz.advance();
            }
            continue;
        }

        // At this point we are about to emit a real token — flush pending NEWLINE
        try flushNewline(&toks, &pending_newline, pending_nl_byte, pending_nl_line, pending_nl_col);

        // Track last significant token index
        const sig_idx = toks.items.len;

        // ---- String "..." (raw scan; no interpolation in v0.1.0) ------------
        if (c == '"') {
            var j = tz.pos + 1;
            var closed = false;
            while (j < src.len) {
                const ch = src[j];
                if (ch == '\\') {
                    if (j + 1 >= src.len) {
                        return LexError.UnterminatedEscape;
                    }
                    j += 2;
                    continue;
                }
                if (ch == '"') {
                    j += 1;
                    closed = true;
                    break;
                }
                if (ch == '\n') {
                    return LexError.UnterminatedString;
                }
                j += 1;
            }
            if (!closed) return LexError.UnterminatedString;
            const val = src[tz.pos..j];
            const span = Span{ .byte_start = tbyte, .byte_end = @intCast(j), .line = tline, .col = tcol };
            try toks.append(.{ .kind = .string, .value = val, .span = span });
            tz.last_sig_idx = sig_idx;
            tz.advanceN(j - tz.pos);
            continue;
        }

        // ---- Regex literal: /.../ — only valid after a `matches` IDENT -------
        if (c == '/') {
            // Check if last significant token is IDENT "matches"
            const is_after_matches = blk: {
                if (tz.last_sig_idx) |li| {
                    const lt = toks.items[li];
                    if (lt.kind == .ident and std.mem.eql(u8, lt.value, "matches")) {
                        break :blk true;
                    }
                }
                break :blk false;
            };
            if (!is_after_matches) {
                return LexError.InvalidRegexPosition;
            }
            var j = tz.pos + 1;
            var closed = false;
            while (j < src.len) {
                const ch = src[j];
                if (ch == '\\') {
                    if (j + 1 >= src.len) return LexError.UnterminatedEscape;
                    j += 2;
                    continue;
                }
                if (ch == '\n') return LexError.UnterminatedRegex;
                if (ch == '/') {
                    j += 1;
                    closed = true;
                    break;
                }
                j += 1;
            }
            if (!closed) return LexError.UnterminatedRegex;
            const val = src[tz.pos..j];
            const span = Span{ .byte_start = tbyte, .byte_end = @intCast(j), .line = tline, .col = tcol };
            try toks.append(.{ .kind = .regex, .value = val, .span = span });
            tz.last_sig_idx = sig_idx;
            tz.advanceN(j - tz.pos);
            continue;
        }

        // ---- Path: '.' in leading position (not glued to prior value token) ----
        if (c == '.') {
            // Check if glued to preceding value token
            const glued = blk: {
                if (tz.last_sig_idx) |li| {
                    const lt = toks.items[li];
                    const value_kinds = [_]TokenKind{ .ident, .number, .string, .duration, .bytes, .regex };
                    var is_val = false;
                    for (value_kinds) |k| {
                        if (lt.kind == k) { is_val = true; break; }
                    }
                    if (is_val and lt.span.byte_end == tbyte) {
                        break :blk true;
                    }
                }
                break :blk false;
            };

            // Check for ".." — but only when not glued
            if (!glued and tz.pos + 1 < src.len and src[tz.pos + 1] == '.') {
                const span = Span{ .byte_start = tbyte, .byte_end = tbyte + 2, .line = tline, .col = tcol };
                try toks.append(.{ .kind = .op, .value = "..", .span = span });
                tz.last_sig_idx = sig_idx;
                tz.advanceN(2);
                continue;
            }

            // PATH: '.' followed by '/' or letter, not glued
            if (!glued and tz.pos + 1 < src.len and
                (src[tz.pos + 1] == '/' or isLetter(src[tz.pos + 1])))
            {
                var j = tz.pos + 1;
                while (j < src.len and isPathChar(src[j])) {
                    j += 1;
                }
                const val = src[tz.pos..j];
                const span = Span{ .byte_start = tbyte, .byte_end = @intCast(j), .line = tline, .col = tcol };
                try toks.append(.{ .kind = .path, .value = val, .span = span });
                tz.last_sig_idx = sig_idx;
                tz.advanceN(j - tz.pos);
                continue;
            }

            // Fall through to OP handling ('.' as DOT)
        }

        // ---- Multi-char operators -------------------------------------------
        {
            var matched: ?[]const u8 = null;
            for (MULTI_OPS) |op| {
                if (tz.pos + op.len <= src.len and
                    std.mem.eql(u8, src[tz.pos .. tz.pos + op.len], op))
                {
                    matched = op;
                    break;
                }
            }
            if (matched) |op| {
                const span = Span{
                    .byte_start = tbyte,
                    .byte_end = @intCast(tz.pos + op.len),
                    .line = tline,
                    .col = tcol,
                };
                try toks.append(.{ .kind = .op, .value = op, .span = span });
                tz.last_sig_idx = sig_idx;
                tz.advanceN(op.len);
                continue;
            }
        }

        // ---- Single-char operators ------------------------------------------
        {
            const single_ops = "=<>.;:,@()[]{}|-";
            var is_single = false;
            for (single_ops) |sc| {
                if (c == sc) { is_single = true; break; }
            }
            if (is_single) {
                if (c == '(' or c == '[') tz.group_depth += 1;
                if (c == ')' or c == ']') {
                    if (tz.group_depth > 0) tz.group_depth -= 1;
                }
                const end: u32 = @intCast(tz.pos + 1);
                const span = Span{ .byte_start = tbyte, .byte_end = end, .line = tline, .col = tcol };
                // Single-char op value: we need a stable string.
                // Use a slice into src for single chars.
                try toks.append(.{ .kind = .op, .value = src[tz.pos .. tz.pos + 1], .span = span });
                tz.last_sig_idx = sig_idx;
                tz.advance();
                continue;
            }
        }

        // ---- Numbers / durations / bytes ------------------------------------
        if (isDigit(c)) {
            var j = tz.pos;
            while (j < src.len and isDigit(src[j])) j += 1;
            var is_float = false;
            if (j < src.len and src[j] == '.' and j + 1 < src.len and isDigit(src[j + 1])) {
                is_float = true;
                j += 1;
                while (j < src.len and isDigit(src[j])) j += 1;
            }
            if (!is_float) {
                // Try byte units first (longest-match, not followed by ident-char)
                if (matchUnit(src, j, &BYTE_UNITS)) |unit| {
                    const after = j + unit.len;
                    if (after >= src.len or !isIdentPart(src[after])) {
                        const end: u32 = @intCast(after);
                        const span = Span{ .byte_start = tbyte, .byte_end = end, .line = tline, .col = tcol };
                        try toks.append(.{ .kind = .bytes, .value = src[tz.pos..after], .span = span });
                        tz.last_sig_idx = sig_idx;
                        tz.advanceN(after - tz.pos);
                        continue;
                    }
                }
                // Try duration units
                if (matchUnit(src, j, &DURATION_UNITS)) |unit| {
                    const after = j + unit.len;
                    if (after >= src.len or !isIdentPart(src[after])) {
                        const end: u32 = @intCast(after);
                        const span = Span{ .byte_start = tbyte, .byte_end = end, .line = tline, .col = tcol };
                        try toks.append(.{ .kind = .duration, .value = src[tz.pos..after], .span = span });
                        tz.last_sig_idx = sig_idx;
                        tz.advanceN(after - tz.pos);
                        continue;
                    }
                }
            }
            // Plain number
            const end: u32 = @intCast(j);
            const span = Span{ .byte_start = tbyte, .byte_end = end, .line = tline, .col = tcol };
            try toks.append(.{ .kind = .number, .value = src[tz.pos..j], .span = span });
            tz.last_sig_idx = sig_idx;
            tz.advanceN(j - tz.pos);
            continue;
        }

        // ---- Identifiers ---------------------------------------------------
        if (isLetter(c)) {
            var j = tz.pos;
            while (j < src.len and isIdentPart(src[j])) j += 1;
            const val = src[tz.pos..j];
            const end: u32 = @intCast(j);
            const span = Span{ .byte_start = tbyte, .byte_end = end, .line = tline, .col = tcol };
            try toks.append(.{ .kind = .ident, .value = val, .span = span });
            tz.last_sig_idx = sig_idx;
            tz.advanceN(j - tz.pos);
            continue;
        }

        // Unexpected character
        return LexError.UnexpectedCharacter;
    }

    // Trim trailing NEWLINE
    if (toks.items.len > 0 and toks.items[toks.items.len - 1].kind == .newline) {
        _ = toks.pop();
    }

    // EOF sentinel
    const eof_byte: u32 = @intCast(src.len);
    try toks.append(.{
        .kind = .eof,
        .value = "<eof>",
        .span = Span{
            .byte_start = eof_byte,
            .byte_end = eof_byte,
            .line = tz.line,
            .col = tz.col,
        },
    });

    return toks.toOwnedSlice();
}

test "lex simple ident" {
    const alloc = std.testing.allocator;
    const toks = try tokenize(alloc, "hello world", "<test>");
    defer alloc.free(toks);
    try std.testing.expectEqual(@as(usize, 3), toks.len); // hello, world, EOF
    try std.testing.expectEqual(TokenKind.ident, toks[0].kind);
    try std.testing.expectEqualStrings("hello", toks[0].value);
}

test "TOKEN_KIND_NAMES covers all kinds" {
    try std.testing.expectEqualStrings("IDENT", TOKEN_KIND_NAMES.get(.ident));
    try std.testing.expectEqualStrings("EOF", TOKEN_KIND_NAMES.get(.eof));
    try std.testing.expectEqualStrings("NEWLINE", TOKEN_KIND_NAMES.get(.newline));
    // EnumArray.len is comptime; assert it equals the number of enum fields.
    comptime std.debug.assert(TOKEN_KIND_NAMES.len == std.meta.fields(TokenKind).len);
}

test "lex number and duration" {
    const alloc = std.testing.allocator;
    const toks = try tokenize(alloc, "42 100ms 1s", "<test>");
    defer alloc.free(toks);
    try std.testing.expectEqual(TokenKind.number, toks[0].kind);
    try std.testing.expectEqual(TokenKind.duration, toks[1].kind);
    try std.testing.expectEqualStrings("100ms", toks[1].value);
    try std.testing.expectEqual(TokenKind.duration, toks[2].kind);
    try std.testing.expectEqualStrings("1s", toks[2].value);
}
