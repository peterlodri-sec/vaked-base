//! Token types for the Vaked lexer — port of `vakedc/lexer.py`'s `Token` /
//! token-kind set. `byteEnd` is exclusive; `line`/`col` are 1-based and refer
//! to `byteStart`. `value` is a slice into the (validated UTF-8) source, except
//! for the two synthetic tokens whose text is a fixed literal:
//!   * NEWLINE — value is the two-char string ``\n`` (backslash + 'n'), exactly
//!     as Python emits (`Token("NEWLINE", "\\n", ...)`).
//!   * EOF — value is the literal ``<eof>``.

/// Token kinds, named exactly as `lexer.py` names them.
pub const Kind = enum {
    IDENT,
    STRING,
    NUMBER,
    DURATION,
    BYTES,
    PATH,
    REGEX,
    OP,
    NEWLINE,
    EOF,

    pub fn name(self: Kind) []const u8 {
        return @tagName(self);
    }
};

pub const Token = struct {
    kind: Kind,
    value: []const u8,
    byteStart: usize,
    byteEnd: usize, // exclusive
    line: usize, // 1-based, of byteStart
    col: usize, // 1-based, of byteStart
};
