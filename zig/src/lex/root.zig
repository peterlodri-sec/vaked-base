//! vaked-lex — the lexer module. Root of the `vaked-lex` build module so its
//! files stay within their own module subtree (Zig 0.16 module boundaries).
//! Depends on `vaked-core` (the lexer's unit-test reuses the canonical-JSON
//! string escaper). Re-exported by the parser (Phase 2) and the CLI.

pub const token = @import("token.zig");
pub const Token = token.Token;
pub const Kind = token.Kind;

pub const lexer = @import("lexer.zig");
pub const tokenize = lexer.tokenize;
pub const Lexer = lexer.Lexer;
pub const LexError = lexer.LexError;
pub const ErrInfo = lexer.ErrInfo;
pub const PINNED_UNICODE = lexer.PINNED_UNICODE;

test {
    _ = @import("token.zig");
    _ = @import("lexer.zig");
}
