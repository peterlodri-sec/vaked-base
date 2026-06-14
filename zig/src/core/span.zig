//! Source span — byte/line/col provenance for a declaration or token.
//! Port of `vakedc/graph.py:Span`. `byteEnd` is exclusive; line/col are 1-based.

pub const Span = struct {
    byteStart: usize,
    byteEnd: usize,
    line: usize,
    col: usize,
};
