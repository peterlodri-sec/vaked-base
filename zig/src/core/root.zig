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

test {
    _ = @import("span.zig");
    _ = @import("provenance.zig");
    _ = @import("value.zig");
    _ = @import("graph.zig");
}
