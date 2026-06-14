//! vaked-check — the 0011 type-system checker (stages 3-4). Root of the
//! `vaked-check` build module so its files stay within their own subtree (Zig
//! 0.16 module boundaries). Depends on `vaked-core` (Diagnostic + Value),
//! `vaked-lex` (tokens, for the source-position map) and `vaked-parse` (AST).
//!
//! Faithful port of `vakedc/check.py`: a pure function of (a parsed .vaked file
//! + the built-in catalog `vaked/schema/builtins.vaked`) → a deterministic,
//! source-mapped, sorted list of `Diagnostic`. The byte gate (oracle) compares
//! the emitted `{"diagnostics": [...]}` JSON against Python over the corpus.

pub const checker = @import("checker.zig");
pub const checkSource = checker.checkSource;
pub const loadBuiltins = checker.loadBuiltins;
pub const Builtins = checker.Builtins;
pub const CheckError = checker.CheckError;

test {
    _ = @import("checker.zig");
}
