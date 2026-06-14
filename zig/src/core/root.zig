//! vaked-core — the shared Vaked library.
//!
//! The compiler (`vakedc`) and, later, the Zig enforcement daemons both import
//! this module. It holds the Labeled Property Graph data model, the canonical
//! JSON writer, and the diagnostics types. Scaffold: only `Span` so far; the
//! rest lands in Tasks 0.3–0.4.

pub const Span = @import("span.zig").Span;

test {
    _ = @import("span.zig");
}
