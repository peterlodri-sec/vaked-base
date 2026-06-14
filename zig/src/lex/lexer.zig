//! vakedc.lexer (Zig port) — mode-switching tokenizer for Vaked (.vaked).
//!
//! Byte-for-byte token-stream parity with `vakedc/lexer.py`. The Python lexer
//! iterates over Unicode *codepoints*, tracking 1-based line/col per codepoint
//! and a precomputed char-index→byte-offset table for exact byte spans. We do
//! the same: scan codepoint by codepoint, advance `col` once per codepoint, and
//! record byte offsets directly (no off[] table needed — `i` IS the byte
//! offset). Token `value` slices reference the source bytes verbatim.
//!
//! NFC gate: the Python lexer rejects non-NFC source. The corpus is verified
//! 100% NFC-stable, so we do **UTF-8 passthrough** — validate that each byte
//! sequence is well-formed UTF-8 and emit the bytes unchanged (no `zg`
//! dependency). Invalid UTF-8 is a lex error (Python would never see it because
//! it decodes on read; an undecodable file errors before tokenize). The pinned-
//! Unicode-version warning is reproduced to stderr for parity.

const std = @import("std");
const tok = @import("token.zig");
const Token = tok.Token;
const Kind = tok.Kind;

/// Pinned Unicode version (mirrors `lexer.py:PINNED_UNICODE`).
pub const PINNED_UNICODE = "15.1.0";
/// The runtime Unicode version Python's CPython 3.x reports here is 16.0.0
/// (verified on this host). Python emits the mismatch warning because
/// 16.0.0 != 15.1.0; we hardcode the same runtime string so the warning bytes
/// match exactly. stderr is NOT gated (only stdout+exit code), so this is for
/// human parity only.
pub const RUNTIME_UNICODE = "16.0.0";

pub const LexError = error{
    /// A lexical error. The message + source position are stashed on the
    /// `Lexer` (see `errInfo`) so the CLI can format `file:line:col — msg`.
    LexFailed,
    OutOfMemory,
};

/// Source-mapped error detail, mirroring `VakedLexError` (`file:line:col — msg`).
pub const ErrInfo = struct {
    msg: []const u8,
    file: []const u8,
    line: usize,
    col: usize,
};

/// The exact warning bytes Python emits when the runtime Unicode version
/// differs from the pin. stderr is NOT gated (only stdout+exit code), so this
/// is for human parity only.
pub const UNICODE_MISMATCH_WARNING = "vakedc: warning: Unicode data version mismatch " ++
    "(pinned " ++ PINNED_UNICODE ++ ", runtime " ++ RUNTIME_UNICODE ++ "); " ++
    "NFC normalization may differ for edge-case codepoints.\n";

/// Emit the pinned-Unicode-version-mismatch warning to stderr once, matching
/// Python's exact bytes. The CLI calls this (it owns the `Io`); `tokenize`
/// stays I/O-free. Best-effort: parity is for humans (stderr is ungated).
var warned_unicode_mismatch = false;
pub fn maybeWarnUnicodeVersion(io: std.Io) void {
    if (warned_unicode_mismatch) return;
    warned_unicode_mismatch = true;
    if (std.mem.eql(u8, RUNTIME_UNICODE, PINNED_UNICODE)) return;
    std.Io.File.stderr().writeStreamingAll(io, UNICODE_MISMATCH_WARNING) catch {};
}

// --- character-class predicates (ASCII; bytes >= 0x80 are never these) ------

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

const MULTI_OPS = [_][]const u8{ "->", "<=", ">=", "..", "?=" };
const DURATION_UNITS = [_][]const u8{ "ns", "us", "ms", "s", "m", "h", "d" };
const BYTE_UNITS = [_][]const u8{ "B", "KB", "MB", "GB", "TB" };

fn isSingleOp(c: u8) bool {
    return std.mem.indexOfScalar(u8, "=<>.;:,@()[]{}|", c) != null;
}

/// Longest unit in `units` that is a prefix of `rest`, or null. Mirrors
/// `_match_unit` (which iterates and keeps the longest match).
fn matchUnit(rest: []const u8, units: []const []const u8) ?[]const u8 {
    var best: ?[]const u8 = null;
    for (units) |u| {
        if (std.mem.startsWith(u8, rest, u)) {
            if (best == null or u.len > best.?.len) best = u;
        }
    }
    return best;
}

/// Decode one UTF-8 codepoint starting at `src[i]`; return its byte length.
/// Errors on malformed UTF-8 (Python decodes on file read, so it never sees
/// invalid UTF-8 in tokenize; we treat it as a lex error for safety).
fn utf8Len(src: []const u8, i: usize) LexError!usize {
    const b = src[i];
    const len = std.unicode.utf8ByteSequenceLength(b) catch return error.LexFailed;
    if (i + len > src.len) return error.LexFailed;
    // Validate the continuation bytes form a legal sequence.
    _ = std.unicode.utf8Decode(src[i .. i + len]) catch return error.LexFailed;
    return len;
}

pub const Lexer = struct {
    src: []const u8,
    file: []const u8,
    alloc: std.mem.Allocator,
    toks: std.ArrayList(Token) = .empty,
    err: ?ErrInfo = null,

    // scan state
    i: usize = 0, // byte offset (== Python off[char_index])
    line: usize = 1,
    col: usize = 1,
    group_depth: usize = 0,
    pending_newline: bool = false,
    pending_nl_byte: usize = 0,
    pending_nl_line: usize = 1,
    pending_nl_col: usize = 1,

    fn fail(self: *Lexer, msg: []const u8, line: usize, col: usize) LexError {
        self.err = .{ .msg = msg, .file = self.file, .line = line, .col = col };
        return error.LexFailed;
    }

    fn lastSignificant(self: *Lexer) ?Token {
        if (self.toks.items.len == 0) return null;
        return self.toks.items[self.toks.items.len - 1];
    }

    /// Advance line/col over the codepoints in `src[start..end]`. Mirrors
    /// `advance`: '\n' resets col to 1 and bumps line; any other codepoint
    /// bumps col by 1.
    fn advance(self: *Lexer, start: usize, end: usize) LexError!void {
        var k = start;
        while (k < end) {
            const b = self.src[k];
            if (b == '\n') {
                self.line += 1;
                self.col = 1;
                k += 1;
            } else {
                self.col += 1;
                k += try utf8Len(self.src, k);
            }
        }
    }

    /// Emit a token, flushing any pending NEWLINE first (mirrors `emit`).
    fn emit(self: *Lexer, kind: Kind, value: []const u8, bstart: usize, bend: usize, tline: usize, tcol: usize) LexError!void {
        if (self.pending_newline) {
            if (self.toks.items.len > 0 and self.toks.items[self.toks.items.len - 1].kind != .NEWLINE) {
                try self.toks.append(self.alloc, .{
                    .kind = .NEWLINE,
                    .value = "\\n", // backslash + 'n', as Python's Token("NEWLINE","\\n",...)
                    .byteStart = self.pending_nl_byte,
                    .byteEnd = self.pending_nl_byte,
                    .line = self.pending_nl_line,
                    .col = self.pending_nl_col,
                });
            }
            self.pending_newline = false;
        }
        try self.toks.append(self.alloc, .{
            .kind = kind,
            .value = value,
            .byteStart = bstart,
            .byteEnd = bend,
            .line = tline,
            .col = tcol,
        });
    }

    fn run(self: *Lexer) LexError!void {
        const src = self.src;
        const n = src.len;
        while (self.i < n) {
            const c = src[self.i];
            const tline = self.line;
            const tcol = self.col;
            const ci = self.i;

            // ---- whitespace (space / tab / CR) ----
            if (c == ' ' or c == '\t' or c == '\r') {
                try self.advance(self.i, self.i + 1);
                self.i += 1;
                continue;
            }

            // ---- newline ----
            if (c == '\n') {
                if (self.group_depth == 0 and !self.pending_newline) {
                    self.pending_newline = true;
                    self.pending_nl_byte = self.i;
                    self.pending_nl_line = self.line;
                    self.pending_nl_col = self.col;
                }
                try self.advance(self.i, self.i + 1);
                self.i += 1;
                continue;
            }

            // ---- comment '#' to EOL (discarded) ----
            if (c == '#') {
                var j = self.i;
                while (j < n and src[j] != '\n') j += 1;
                try self.advance(self.i, j);
                self.i = j;
                continue;
            }

            // ---- string with ${ref} interpolation ----
            if (c == '"') {
                var j = self.i + 1;
                var closed = false;
                while (j < n) {
                    const ch = src[j];
                    if (ch == '\\') {
                        if (j + 1 >= n) return self.fail("unterminated escape in string", tline, tcol);
                        j += 2;
                        continue;
                    }
                    if (ch == '"') {
                        j += 1;
                        closed = true;
                        break;
                    }
                    if (ch == '\n') return self.fail("unterminated string (newline in string)", tline, tcol);
                    // verbatim (incl. multi-byte UTF-8); advance by codepoint length.
                    j += try utf8Len(src, j);
                }
                if (!closed) return self.fail("unterminated string", tline, tcol);
                const value = src[ci..j];
                try self.advance(ci, j);
                try self.emit(.STRING, value, ci, j, tline, tcol);
                self.i = j;
                continue;
            }

            // ---- regex literal /.../  (only right after `matches`) ----
            if (c == '/') {
                const ls = self.lastSignificant();
                if (ls != null and ls.?.kind == .IDENT and std.mem.eql(u8, ls.?.value, "matches")) {
                    var j = self.i + 1;
                    var closed = false;
                    while (j < n) {
                        const ch = src[j];
                        if (ch == '\\') {
                            if (j + 1 >= n) return self.fail("unterminated regex escape", tline, tcol);
                            j += 2;
                            continue;
                        }
                        if (ch == '\n') return self.fail("unterminated regex (newline)", tline, tcol);
                        if (ch == '/') {
                            j += 1;
                            closed = true;
                            break;
                        }
                        j += try utf8Len(src, j);
                    }
                    if (!closed) return self.fail("unterminated regex literal", tline, tcol);
                    const value = src[ci..j];
                    try self.advance(ci, j);
                    try self.emit(.REGEX, value, ci, j, tline, tcol);
                    self.i = j;
                    continue;
                }
                return self.fail("unexpected '/' (regex literal is only valid after `matches`)", tline, tcol);
            }

            // ---- path: '.' leading, followed by '/' or letter ----
            if (c == '.') {
                const ls = self.lastSignificant();
                // '.' glued to a preceding value token is a DOT; else leading
                // './' or '.<letter>' begins a PATH; '..' is OP.
                const glued = blk: {
                    if (ls == null) break :blk false;
                    const k = ls.?.kind;
                    const is_value = k == .IDENT or k == .NUMBER or k == .STRING or
                        k == .DURATION or k == .BYTES or k == .REGEX;
                    break :blk is_value and ls.?.byteEnd == ci;
                };
                if (self.i + 1 < n and src[self.i + 1] == '.' and !glued) {
                    try self.advance(self.i, self.i + 2);
                    try self.emit(.OP, "..", ci, self.i + 2, tline, tcol);
                    self.i += 2;
                    continue;
                }
                if (!glued and self.i + 1 < n and (src[self.i + 1] == '/' or isLetter(src[self.i + 1]))) {
                    var j = self.i + 1;
                    while (j < n and isPathChar(src[j])) j += 1;
                    const value = src[ci..j];
                    try self.advance(ci, j);
                    try self.emit(.PATH, value, ci, j, tline, tcol);
                    self.i = j;
                    continue;
                }
                // else falls through to OP handling ('.' as DOT)
            }

            // ---- multi-char operators ----
            var matched_op: ?[]const u8 = null;
            for (MULTI_OPS) |op| {
                if (std.mem.startsWith(u8, src[self.i..], op)) {
                    matched_op = op;
                    break;
                }
            }
            if (matched_op) |op| {
                try self.advance(self.i, self.i + op.len);
                try self.emit(.OP, op, ci, self.i + op.len, tline, tcol);
                self.i += op.len;
                continue;
            }

            // ---- single-char operators ----
            if (isSingleOp(c)) {
                if (c == '(' or c == '[') {
                    self.group_depth += 1;
                } else if (c == ')' or c == ']') {
                    if (self.group_depth > 0) self.group_depth -= 1;
                }
                try self.advance(self.i, self.i + 1);
                try self.emit(.OP, src[ci .. ci + 1], ci, self.i + 1, tline, tcol);
                self.i += 1;
                continue;
            }

            // ---- numbers / durations / bytes ----
            if (isDigit(c) or (c == '-' and self.i + 1 < n and isDigit(src[self.i + 1]))) {
                var j = self.i;
                if (src[j] == '-') j += 1;
                while (j < n and isDigit(src[j])) j += 1;
                var is_float = false;
                if (j < n and src[j] == '.' and j + 1 < n and isDigit(src[j + 1])) {
                    is_float = true;
                    j += 1;
                    while (j < n and isDigit(src[j])) j += 1;
                }
                if (!is_float) {
                    const rest = src[j..];
                    if (matchUnit(rest, &BYTE_UNITS)) |unit| {
                        const after = j + unit.len;
                        if (!(after < n and isIdentPart(src[after]))) {
                            const value = src[ci..after];
                            try self.advance(ci, after);
                            try self.emit(.BYTES, value, ci, after, tline, tcol);
                            self.i = after;
                            continue;
                        }
                    }
                    if (matchUnit(rest, &DURATION_UNITS)) |unit| {
                        const after = j + unit.len;
                        if (!(after < n and isIdentPart(src[after]))) {
                            const value = src[ci..after];
                            try self.advance(ci, after);
                            try self.emit(.DURATION, value, ci, after, tline, tcol);
                            self.i = after;
                            continue;
                        }
                    }
                }
                const value = src[ci..j];
                try self.advance(ci, j);
                try self.emit(.NUMBER, value, ci, j, tline, tcol);
                self.i = j;
                continue;
            }

            // ---- identifiers ----
            if (isLetter(c)) {
                var j = self.i;
                while (j < n and isIdentPart(src[j])) j += 1;
                const value = src[ci..j];
                try self.advance(ci, j);
                try self.emit(.IDENT, value, ci, j, tline, tcol);
                self.i = j;
                continue;
            }

            // unexpected character — Python formats with repr(c). For the corpus
            // (which lexes cleanly) this path is never hit; we keep a plain
            // message. stdout+exit code are what's gated, and a lex error exits 1.
            return self.fail("unexpected character", tline, tcol);
        }

        // trailing NEWLINE trim, then EOF sentinel.
        if (self.toks.items.len > 0 and self.toks.items[self.toks.items.len - 1].kind == .NEWLINE) {
            _ = self.toks.pop();
        }
        try self.toks.append(self.alloc, .{
            .kind = .EOF,
            .value = "<eof>",
            .byteStart = n,
            .byteEnd = n,
            .line = self.line,
            .col = self.col,
        });
    }
};

/// Tokenize `source` into a slice of tokens ending with an EOF sentinel.
/// On a lex error, `err_out` (if non-null) is filled with the source-mapped
/// detail and `error.LexFailed` is returned. Caller owns the returned slice
/// (allocated with `alloc`); token `value` slices reference `source`.
pub fn tokenize(alloc: std.mem.Allocator, source: []const u8, filename: []const u8, err_out: ?*ErrInfo) LexError![]Token {
    var lx = Lexer{ .src = source, .file = filename, .alloc = alloc };
    lx.run() catch |e| {
        if (err_out) |p| {
            if (lx.err) |info| p.* = info;
        }
        lx.toks.deinit(alloc);
        return e;
    };
    return lx.toks.toOwnedSlice(alloc);
}

// --------------------------------------------------------------------------- //
// tests
// --------------------------------------------------------------------------- //

const json_canon = @import("vaked-core").json_canon;

/// Build the same TAB-separated token dump the CLI emits, for unit testing.
fn dumpToksAlloc(alloc: std.mem.Allocator, toks: []const Token) ![]u8 {
    var buf: std.ArrayList(u8) = .empty;
    errdefer buf.deinit(alloc);
    for (toks) |t| {
        try buf.appendSlice(alloc, t.kind.name());
        try buf.append(alloc, '\t');
        var tmp: [24]u8 = undefined;
        try buf.appendSlice(alloc, try std.fmt.bufPrint(&tmp, "{d}", .{t.byteStart}));
        try buf.append(alloc, '\t');
        try buf.appendSlice(alloc, try std.fmt.bufPrint(&tmp, "{d}", .{t.byteEnd}));
        try buf.append(alloc, '\t');
        try buf.appendSlice(alloc, try std.fmt.bufPrint(&tmp, "{d}", .{t.line}));
        try buf.append(alloc, '\t');
        try buf.appendSlice(alloc, try std.fmt.bufPrint(&tmp, "{d}", .{t.col}));
        try buf.append(alloc, '\t');
        try json_canon.writeJsonStringRaw(&buf, alloc, t.value);
        try buf.append(alloc, '\n');
    }
    return buf.toOwnedSlice(alloc);
}

test "token dump: ident, string-with-escape + non-ascii passthrough, comment, punctuation" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();

    // Non-ASCII is only valid INSIDE strings/comments (idents are ASCII-only,
    // exactly as Python's _is_letter). 'é' is 2 bytes (0xC3 0xA9).
    //   name = "a\"é"  # c
    // bytes: n(0)a(1)m(2)e(3) (4)=(5) (6)"(7)a(8)\(9)"(10)é(11,12)"(13)
    //        (14)#(15) (16)c(17)  -> '# c' is a comment, discarded.
    const src = "name = \"a\\\"\u{e9}\" # c";
    const toks = try tokenize(a, src, "<t>", null);
    const got = try dumpToksAlloc(a, toks);
    // IDENT "name": bytes 0..4, col 1.
    // OP "=": bytes 5..6, col 6.
    // STRING raw `"a\"é"` bytes 7..14 (é=2 bytes). Escaper: leading quote→\",
    //   a, \\→ doubled backslash, inner "→\", é passes through, trailing "→\".
    //   → `\"a\\\"é\"`. col counts codepoints: n1 a2 m3 e4 sp5 =6 sp7 → string col 8.
    // EOF: byte 18, col after the whole line. codepoints on line:
    //   name(4) sp(1) =(1) sp(1) "(1)a(1)\(1)"(1)é(1)"(1) sp(1) #(1) sp(1) c(1)
    //   = 17 → col 18.
    const expected =
        "IDENT\t0\t4\t1\t1\tname\n" ++
        "OP\t5\t6\t1\t6\t=\n" ++
        "STRING\t7\t14\t1\t8\t\\\"a\\\\\\\"\u{e9}\\\"\n" ++
        "EOF\t18\t18\t1\t18\t<eof>\n";
    try std.testing.expectEqualStrings(expected, got);
}

test "token dump: newline suppression in group, duration unit, dotted DOT vs PATH" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();

    // "a = 24h\nb = [\n1\n]\n" — NEWLINE after 24h emitted; inside [] suppressed.
    const src = "a = 24h\nb = [\n1\n]\n";
    const toks = try tokenize(a, src, "<t>", null);
    const got = try dumpToksAlloc(a, toks);
    // a(0) (1)=(2) (3)2(4)4(5)h(6)\n(7) b(8) (9)=(10) (11)[(12)\n(13)1(14)\n(15)](16)\n(17)
    const expected =
        "IDENT\t0\t1\t1\t1\ta\n" ++
        "OP\t2\t3\t1\t3\t=\n" ++
        "DURATION\t4\t7\t1\t5\t24h\n" ++
        // NEWLINE text is the two-char Python value `\n` (backslash+n); the
        // escaper doubles the backslash → bytes `\\n` (literal `\\\\n` here).
        "NEWLINE\t7\t7\t1\t8\t\\\\n\n" ++
        "IDENT\t8\t9\t2\t1\tb\n" ++
        "OP\t10\t11\t2\t3\t=\n" ++
        "OP\t12\t13\t2\t5\t[\n" ++
        "NUMBER\t14\t15\t3\t1\t1\n" ++
        "OP\t16\t17\t4\t1\t]\n" ++
        "EOF\t18\t18\t5\t1\t<eof>\n";
    try std.testing.expectEqualStrings(expected, got);
}
