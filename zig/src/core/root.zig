//! vaked-core — the shared Vaked library.
//!
//! The compiler (`vakedc`) and, later, the Zig enforcement daemons both import
//! this module. It holds the Labeled Property Graph data model, the canonical
//! JSON writer (Task 0.4), and the diagnostics types (Phase 3).

pub const Span = @import("span.zig").Span;
pub const Provenance = @import("provenance.zig").Provenance;
pub const Value = @import("value.zig").Value;

pub const graph = @import("graph.zig");
pub const Graph = graph.Graph;
pub const GraphNode = graph.GraphNode;
pub const GraphEdge = graph.GraphEdge;
pub const nodeId = graph.nodeId;

pub const json_canon = @import("json_canon.zig");
pub const graphToCanonical = json_canon.graphToCanonical;
pub const valueDocToPretty = json_canon.valueDocToPretty;
pub const stablePropsKey = json_canon.stablePropsKey;

// The lexer (Phase 1) lives in the separate `vaked-lex` module (see build.zig)
// to respect Zig 0.16 module boundaries. Consumers import `vaked-lex` directly.

test {
    _ = @import("span.zig");
    _ = @import("provenance.zig");
    _ = @import("value.zig");
    _ = @import("graph.zig");
    _ = @import("json_canon.zig");
}
