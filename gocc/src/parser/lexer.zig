const std = @import("std");

pub const TokenKind = enum {
    at,       // @
    lparen,   // (
    rparen,   // )
    gt,       // >
    amp,      // &
    question, // ?
    colon,    // :
    comma,    // ,
    ident,    // [a-zA-Z_][a-zA-Z0-9_-]*
    string,   // "..." (src includes quotes; parser strips them)
    number,   // [0-9]+(\.[0-9]+)?
    eof,
};

pub const Token = struct {
    kind: TokenKind,
    src: []const u8, // slice of original source
    offset: usize,
};

pub const LexError = error{ UnexpectedChar, UnterminatedString };

pub const Lexer = struct {
    src: []const u8,
    pos: usize = 0,

    pub fn init(src: []const u8) Lexer {
        return .{ .src = src };
    }

    fn skipWs(self: *Lexer) void {
        while (self.pos < self.src.len) {
            switch (self.src[self.pos]) {
                ' ', '\t', '\n', '\r' => self.pos += 1,
                else => break,
            }
        }
    }

    pub fn peek(self: *Lexer) LexError!Token {
        const saved = self.pos;
        const tok = try self.next();
        self.pos = saved;
        return tok;
    }

    pub fn next(self: *Lexer) LexError!Token {
        self.skipWs();

        if (self.pos >= self.src.len) {
            return Token{ .kind = .eof, .src = "", .offset = self.pos };
        }

        const start = self.pos;
        const c = self.src[self.pos];

        switch (c) {
            '@' => { self.pos += 1; return Token{ .kind = .at, .src = self.src[start..self.pos], .offset = start }; },
            '(' => { self.pos += 1; return Token{ .kind = .lparen, .src = self.src[start..self.pos], .offset = start }; },
            ')' => { self.pos += 1; return Token{ .kind = .rparen, .src = self.src[start..self.pos], .offset = start }; },
            '>' => { self.pos += 1; return Token{ .kind = .gt, .src = self.src[start..self.pos], .offset = start }; },
            '&' => { self.pos += 1; return Token{ .kind = .amp, .src = self.src[start..self.pos], .offset = start }; },
            '?' => { self.pos += 1; return Token{ .kind = .question, .src = self.src[start..self.pos], .offset = start }; },
            ':' => { self.pos += 1; return Token{ .kind = .colon, .src = self.src[start..self.pos], .offset = start }; },
            ',' => { self.pos += 1; return Token{ .kind = .comma, .src = self.src[start..self.pos], .offset = start }; },
            '"' => {
                self.pos += 1;
                while (self.pos < self.src.len and self.src[self.pos] != '"') {
                    self.pos += 1;
                }
                if (self.pos >= self.src.len) return error.UnterminatedString;
                self.pos += 1; // consume closing "
                return Token{ .kind = .string, .src = self.src[start..self.pos], .offset = start };
            },
            '0'...'9' => {
                while (self.pos < self.src.len and self.src[self.pos] >= '0' and self.src[self.pos] <= '9') {
                    self.pos += 1;
                }
                // optional decimal part
                if (self.pos + 1 < self.src.len and self.src[self.pos] == '.' and
                    self.src[self.pos + 1] >= '0' and self.src[self.pos + 1] <= '9')
                {
                    self.pos += 1; // consume '.'
                    while (self.pos < self.src.len and self.src[self.pos] >= '0' and self.src[self.pos] <= '9') {
                        self.pos += 1;
                    }
                }
                return Token{ .kind = .number, .src = self.src[start..self.pos], .offset = start };
            },
            'a'...'z', 'A'...'Z', '_' => {
                self.pos += 1;
                while (self.pos < self.src.len) {
                    const ch = self.src[self.pos];
                    if ((ch >= 'a' and ch <= 'z') or (ch >= 'A' and ch <= 'Z') or
                        (ch >= '0' and ch <= '9') or ch == '_' or ch == '-')
                    {
                        self.pos += 1;
                    } else {
                        break;
                    }
                }
                return Token{ .kind = .ident, .src = self.src[start..self.pos], .offset = start };
            },
            else => return error.UnexpectedChar,
        }
    }
};
