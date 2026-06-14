const std = @import("std");
const core = @import("vaked-core");

pub fn main() !void {
    // Scaffold entry point. Subcommands (lex/parse/check/lower) land in the
    // per-stage tasks. Touch `core` so the import is exercised at scaffold time.
    comptime std.debug.assert(@hasDecl(core, "Span"));
    std.debug.print("vakedc (zig) — not yet implemented\n", .{});
}
