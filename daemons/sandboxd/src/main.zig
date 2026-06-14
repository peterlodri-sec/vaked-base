//! sandboxd — namespace/cgroup/exec enforcement daemon.
//!
//! Backend: native-exec (Linux namespaces + cgroups v2 + seccomp).
//! Stub. Implementation starts WP4-S1 (Jun 24 2026).
//! See docs/superpowers/plans/2026-06-14-wp4-kickoff.md.

const std = @import("std");

pub fn main() !void {
    const stderr = std.io.getStdErr().writer();
    try stderr.print("sandboxd v0.1.0-dev — stub, WP4-S1 starts Jun 24\n", .{});
    std.process.exit(1);
}
