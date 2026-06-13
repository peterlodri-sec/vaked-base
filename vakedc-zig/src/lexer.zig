// vakedc-zig lexer — UTF-8 → tokens with exact byte spans
const std = @import("std");

pub const TokenKind = enum {
    IDENT,
    STRING,
    NUMBER,
    DURATION,
    BYTES,
    PATH,
    REGEX,
    LBRACE,
    RBRACE,
    LBRACKET,
    RBRACKET,
    LPAREN,
    RPAREN,
    COLON,
    COMMA,
    SEMICOLON,
    DOT,
    DOUBLEDOT,
    PIPE,
    AT,
    ARROW,
    ASSIGN,
    QASSIGN,
    LT,
    GT,
    LTE,
    GTE,
    NEWLINE,
    EOF,
    ERROR,
};

pub const Token = struct {
    kind: TokenKind,
    value: []const u8,
    byteStart: u32,
    byteEnd: u32,
    line: u32,
    col: u32,
};

pub const Lexer = struct {
    allocator: std.mem.Allocator,
    source: []const u8,
    pos: usize,
    line: u32,
    col: u32,
    depth: usize,
    tokens: std.ArrayList(Token),

    pub fn init(allocator: std.mem.Allocator, source: []const u8) !Lexer {
        return Lexer{
            .allocator = allocator,
            .source = source,
            .pos = 0,
            .line = 1,
            .col = 1,
            .depth = 0,
            .tokens = std.ArrayList(Token).init(allocator),
        };
    }

    pub fn deinit(self: *Lexer) void {
        self.tokens.deinit();
    }

    pub fn tokenize(self: *Lexer) !void {
        while (self.pos < self.source.len) {
            const ch = self.source[self.pos];

            // Skip whitespace (except newlines)
            if (ch == ' ' or ch == '\t') {
                self.advance();
                continue;
            }

            // Newlines
            if (ch == '\n' or ch == '\r') {
                try self.lexNewline();
                continue;
            }

            // Comments
            if (ch == '#') {
                self.skipComment();
                continue;
            }

            // Single-character operators
            if (ch == '{') {
                try self.emit(TokenKind.LBRACE, 1);
                self.depth += 1;
                continue;
            }
            if (ch == '}') {
                self.depth = if (self.depth > 0) self.depth - 1 else 0;
                try self.emit(TokenKind.RBRACE, 1);
                continue;
            }
            if (ch == '[') {
                try self.emit(TokenKind.LBRACKET, 1);
                self.depth += 1;
                continue;
            }
            if (ch == ']') {
                self.depth = if (self.depth > 0) self.depth - 1 else 0;
                try self.emit(TokenKind.RBRACKET, 1);
                continue;
            }
            if (ch == '(') {
                try self.emit(TokenKind.LPAREN, 1);
                self.depth += 1;
                continue;
            }
            if (ch == ')') {
                self.depth = if (self.depth > 0) self.depth - 1 else 0;
                try self.emit(TokenKind.RPAREN, 1);
                continue;
            }
            if (ch == ':') {
                try self.emit(TokenKind.COLON, 1);
                continue;
            }
            if (ch == ',') {
                try self.emit(TokenKind.COMMA, 1);
                continue;
            }
            if (ch == ';') {
                try self.emit(TokenKind.SEMICOLON, 1);
                continue;
            }
            if (ch == '@') {
                try self.emit(TokenKind.AT, 1);
                continue;
            }
            if (ch == '|') {
                try self.emit(TokenKind.PIPE, 1);
                continue;
            }

            // Multi-character operators
            if (self.pos + 1 < self.source.len) {
                const next = self.source[self.pos + 1];
                if (ch == '-' and next == '>') {
                    try self.emit(TokenKind.ARROW, 2);
                    continue;
                }
                if (ch == '.' and next == '.') {
                    try self.emit(TokenKind.DOUBLEDOT, 2);
                    continue;
                }
                if (ch == '<' and next == '=') {
                    try self.emit(TokenKind.LTE, 2);
                    continue;
                }
                if (ch == '>' and next == '=') {
                    try self.emit(TokenKind.GTE, 2);
                    continue;
                }
                if (ch == '?' and next == '=') {
                    try self.emit(TokenKind.QASSIGN, 2);
                    continue;
                }
            }

            // Single-char ops
            if (ch == '.') {
                try self.emit(TokenKind.DOT, 1);
                continue;
            }
            if (ch == '=') {
                try self.emit(TokenKind.ASSIGN, 1);
                continue;
            }
            if (ch == '<') {
                try self.emit(TokenKind.LT, 1);
                continue;
            }
            if (ch == '>') {
                try self.emit(TokenKind.GT, 1);
                continue;
            }

            // Strings
            if (ch == '"') {
                try self.lexString();
                continue;
            }

            // Numbers
            if (std.ascii.isDigit(ch)) {
                try self.lexNumber();
                continue;
            }

            // Identifiers and keywords
            if (std.ascii.isAlpha(ch) or ch == '_') {
                try self.lexIdent();
                continue;
            }

            // Unknown character
            try self.emit(TokenKind.ERROR, 1);
        }

        // EOF
        try self.emitToken(TokenKind.EOF, "");
    }

    fn lexNewline(self: *Lexer) !void {
        if (self.source[self.pos] == '\r' and self.pos + 1 < self.source.len and self.source[self.pos + 1] == '\n') {
            self.pos += 2;
        } else {
            self.pos += 1;
        }

        self.line += 1;
        self.col = 1;

        // Only emit NEWLINE if depth == 0 (not inside grouping)
        if (self.depth == 0) {
            try self.emitToken(TokenKind.NEWLINE, "\n");
        }
    }

    fn lexString(self: *Lexer) !void {
        const start = self.pos;
        const start_col = self.col;
        self.pos += 1; // skip opening quote

        var value = std.ArrayList(u8).init(self.allocator);
        defer value.deinit();

        while (self.pos < self.source.len and self.source[self.pos] != '"') {
            const ch = self.source[self.pos];
            if (ch == '\\' and self.pos + 1 < self.source.len) {
                self.pos += 1;
                try value.append(self.source[self.pos]);
            } else {
                try value.append(ch);
            }
            self.pos += 1;
            self.col += 1;
        }

        if (self.pos < self.source.len) {
            self.pos += 1; // skip closing quote
            self.col += 1;
        }

        const token = Token{
            .kind = TokenKind.STRING,
            .value = try self.allocator.dupe(u8, value.items),
            .byteStart = @intCast(start),
            .byteEnd = @intCast(self.pos),
            .line = @intCast(self.line),
            .col = @intCast(start_col),
        };
        try self.tokens.append(token);
    }

    fn lexNumber(self: *Lexer) !void {
        const start = self.pos;

        // Read digits, tracking whether we've seen a dot
        var has_dot = false;
        while (self.pos < self.source.len and (std.ascii.isDigit(self.source[self.pos]) or self.source[self.pos] == '.')) {
            if (self.source[self.pos] == '.') {
                if (has_dot) break; // reject multiple dots
                has_dot = true;
            }
            self.pos += 1;
            self.col += 1;
        }

        // Check for duration or bytes suffix
        const num_end = self.pos;
        while (self.pos < self.source.len and std.ascii.isAlpha(self.source[self.pos])) {
            self.pos += 1;
            self.col += 1;
        }

        const value = self.source[start..self.pos];
        const suffix = self.source[num_end..self.pos];
        const kind = if (suffix.len == 0) TokenKind.NUMBER else if (isDurationSuffix(suffix)) TokenKind.DURATION else if (isBytesSuffix(suffix)) TokenKind.BYTES else TokenKind.ERROR;

        try self.emitToken(kind, value);
    }

    fn lexIdent(self: *Lexer) !void {
        const start = self.pos;

        while (self.pos < self.source.len and (std.ascii.isAlphaNumeric(self.source[self.pos]) or self.source[self.pos] == '_' or self.source[self.pos] == '-')) {
            self.pos += 1;
            self.col += 1;
        }

        const value = self.source[start..self.pos];
        try self.emitToken(TokenKind.IDENT, value);
    }

    fn skipComment(self: *Lexer) void {
        while (self.pos < self.source.len and self.source[self.pos] != '\n' and self.source[self.pos] != '\r') {
            self.pos += 1;
        }
    }

    fn advance(self: *Lexer) void {
        if (self.pos < self.source.len) {
            self.pos += 1;
            self.col += 1;
        }
    }

    fn emit(self: *Lexer, kind: TokenKind, len: usize) !void {
        const value = self.source[self.pos .. self.pos + len];
        try self.emitToken(kind, value);
        self.pos += len;
        self.col += len;
    }

    fn emitToken(self: *Lexer, kind: TokenKind, value: []const u8) !void {
        const token = Token{
            .kind = kind,
            .value = try self.allocator.dupe(u8, value),
            .byteStart = @intCast(self.pos),
            .byteEnd = @intCast(self.pos + value.len),
            .line = self.line,
            .col = self.col,
        };
        try self.tokens.append(token);
    }
};

fn isDurationSuffix(suffix: []const u8) bool {
    const suffixes = [_][]const u8{ "ns", "us", "ms", "s", "m", "h", "d" };
    for (suffixes) |suf| {
        if (std.mem.eql(u8, suffix, suf)) {
            return true;
        }
    }
    return false;
}

fn isBytesSuffix(suffix: []const u8) bool {
    const suffixes = [_][]const u8{ "B", "KB", "MB", "GB", "TB" };
    for (suffixes) |suf| {
        if (std.mem.eql(u8, suffix, suf)) {
            return true;
        }
    }
    return false;
}
