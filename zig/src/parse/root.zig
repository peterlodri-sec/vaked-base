//! vaked-parse — the parser + resolver module (Phase 2). Root of the
//! `vaked-parse` build module so its files stay within their own module subtree
//! (Zig 0.16 module boundaries). Depends on `vaked-core` (the LPG model + value
//! tree) and `vaked-lex` (token stream). Re-exported by the CLI.

pub const ast = @import("ast.zig");

pub const parser = @import("parser.zig");
pub const parse = parser.parse;
pub const Parser = parser.Parser;
pub const ParseError = parser.ParseError;
pub const ErrInfo = parser.ErrInfo;
pub const isKind = parser.isKind;
pub const KINDS = parser.KINDS;

pub const resolve = @import("resolve.zig");
pub const buildGraph = resolve.buildGraph;
pub const ResolveError = resolve.ResolveError;

test {
    _ = @import("ast.zig");
    _ = @import("parser.zig");
    _ = @import("resolve.zig");
}
