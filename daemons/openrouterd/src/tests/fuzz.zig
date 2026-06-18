const std = @import("std");
const subagent = @import("../subagent.zig");

test "ffi: concurrent spawn never duplicates slot" {
    var buf: [65536]u8 align(std.heap.page_size_min) = undefined;
    @memset(&buf, 0);
    var pool = subagent.WorkerPool.init(std.testing.allocator, buf[0..]);

    const slots = [_]u32{
        try pool.spawnHydrator("t1"), try pool.spawnHydrator("t2"),
        try pool.spawnHydrator("t3"), try pool.spawnHydrator("t4"),
    };
    for (0..slots.len) |i| {
        for (i+1..slots.len) |j| {
            try std.testing.expect(slots[i] != slots[j]);
        }
    }
}

test "ffi: atomic slot acquisition" {
    var buf: [65536]u8 align(std.heap.page_size_min) = undefined;
    @memset(&buf, 0);
    var pool = subagent.WorkerPool.init(std.testing.allocator, buf[0..]);
    _ = try pool.spawnHydrator("a");
    _ = try pool.spawnHydrator("b");
    try std.testing.expect(pool.arena.active_hydrators == 2);
}

test "ffi: complete and poll cycle" {
    var buf: [65536]u8 align(std.heap.page_size_min) = undefined;
    @memset(&buf, 0);
    var pool = subagent.WorkerPool.init(std.testing.allocator, buf[0..]);
    const id = try pool.spawnHydrator("task");
    pool.complete(id, "result");
    try std.testing.expectEqualStrings("result", pool.poll(id).?);
}
