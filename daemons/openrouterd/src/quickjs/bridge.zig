//! QuickJS bridge — embed QuickJS in the Zig daemon.
//! Zig handles all network I/O (TLS). QuickJS handles agent logic.
//! Uses subprocess qjs for now (FFI embedding follow-up).
const std = @import("std");

const SCRIPT = @embedFile("agent_logic.js");

/// Run a QuickJS function and return the JSON result.
/// Spawns `qjs --std -e <script>` and captures stdout.
pub fn callFunction(allocator: std.mem.Allocator, func: []const u8, args_json: []const u8) ![]const u8 {
    const qjs_path = "/opt/homebrew/bin/qjs"; // configurable

    var argv = std.ArrayListUnmanaged([]const u8){ .items = &.{}, .capacity = 0 };
    defer argv.deinit(allocator);
    try argv.append(allocator, qjs_path);
    try argv.append(allocator, "--std");
    try argv.append(allocator, "-e");

    // Build the eval script: load agent logic + call function
    const script = try std.fmt.allocPrint(allocator,
        \\{s}
        \\console.log(JSON.stringify({s}({s})));
    , .{ SCRIPT, func, args_json });
    defer allocator.free(script);

    try argv.append(allocator, script);

    var child = std.process.Child.init(argv.items, allocator);
    child.stdout_behavior = .Pipe;
    child.stderr_behavior = .Pipe;

    try child.spawn();
    const stdout = try child.stdout.?.reader().readAllAlloc(allocator, 1024 * 1024);
    _ = try child.wait();

    return stdout;
}

/// Quick benchmark: time a function call
pub fn bench(allocator: std.mem.Allocator) !void {
    const start = std.time.milliTimestamp();

    var i: usize = 0;
    while (i < 100) : (i += 1) {
        const result = try callFunction(allocator, "_routeModel", "\"write a sorting function\"");
        allocator.free(result);
    }

    const elapsed = std.time.milliTimestamp() - start;
    std.debug.print("QuickJS: 100 _routeModel calls in {d}ms ({d:.1}ms/call)\n", .{ elapsed, @as(f64, @floatFromInt(elapsed)) / 100.0 });
}
