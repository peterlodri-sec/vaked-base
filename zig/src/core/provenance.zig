//! `Provenance` — where a graph node came from in source.
//! Port of `vakedc/graph.py:Provenance`. `decl` is `"<kind> <name>"`.

const Span = @import("span.zig").Span;

pub const Provenance = struct {
    file: []const u8,
    decl: []const u8, // "<kind> <name>", e.g. "fiber mediaCompress"
    span: Span,
};
