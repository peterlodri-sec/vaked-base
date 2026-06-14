pub const TokenKind = enum { at, lparen, rparen, gt, amp, question, colon, comma, ident, string, number, eof };
pub const Token = struct { kind: TokenKind, src: []const u8, offset: usize };
pub const Lexer = struct {
    src: []const u8,
    pos: usize = 0,
    pub fn init(src: []const u8) Lexer { return .{ .src = src }; }
    pub fn next(self: *Lexer) Token { _ = self; return .{ .kind = .eof, .src = "", .offset = 0 }; }
};
