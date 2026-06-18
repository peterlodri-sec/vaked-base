const std = @import("std");
pub const VirtualIo = struct {
    read_queue: std.ArrayListUnmanaged(u8),
    write_queue: std.ArrayListUnmanaged(u8),
    fixtures: std.StringHashMapUnmanaged([]const u8),
    pub fn init(_: std.mem.Allocator) VirtualIo {
        return .{
            .read_queue = .{ .items = &.{}, .capacity = 0 },
            .write_queue = .{ .items = &.{}, .capacity = 0 },
            .fixtures = .{},
        };
    }
    pub fn deinit(self: *VirtualIo) void {
        self.read_queue.deinit(self.read_queue.allocator);
        self.write_queue.deinit(self.write_queue.allocator);
        var it = self.fixtures.valueIterator();
        while (it.next()) |v| self.fixtures.allocator.free(v.*);
        self.fixtures.deinit(self.fixtures.allocator);
    }
    pub fn injectFixture(self: *VirtualIo, allocator: std.mem.Allocator, label: []const u8, data: []const u8) !void {
        const owned = try allocator.dupe(u8, data);
        try self.fixtures.put(allocator, try allocator.dupe(u8, label), owned);
    }
    pub fn pushRead(self: *VirtualIo, allocator: std.mem.Allocator, data: []const u8) !void {
        try self.read_queue.appendSlice(allocator, data);
    }
    pub fn simulateResponse(self: *VirtualIo, label: []const u8) !void {
        _ = self.fixtures.get(label) orelse return error.FixtureNotFound;
    }
    pub fn consumeWrites(self: *VirtualIo, allocator: std.mem.Allocator) ![]const u8 {
        const out = try allocator.dupe(u8, self.write_queue.items);
        self.write_queue.clearAndFree(allocator);
        return out;
    }
};
pub const FIXTURES = struct {
    pub const deepseek_chat =
        \\data: {"id":"chatcmpl-7c242080","choices":[{"delta":{"content":"The Vaked swarm operates"}}]}
        \\
        \\data: {"id":"chatcmpl-7c242080","choices":[{"delta":{"content":" on a Compile-Pass-Only standard."}}]}
        \\
        \\data: [DONE]
    ;
    pub const openrouter_error =
        \\{"error":{"message":"Rate limited","code":429}}
    ;
    pub const vastai_gpu_list =
        \\{"offers":[{"id":12345,"gpu_name":"RTX_4090","num_gpus":1,"dph_total":0.32,"geolocation":"US-East"}]}
    ;
    pub const context7_zig_docs =
        \\{"codeSnippets":[{"codeTitle":"std.Build","codeListCodeExample":[{"code":"pub fn build(b: *std.Build) void { ... }"}]}]}
    ;
};
pub fn loadFixture(io: *VirtualIo, allocator: std.mem.Allocator, label: []const u8, data: []const u8) !void {
    try io.injectFixture(allocator, label, data);
    try io.pushRead(allocator, data);
}
const subagent = @import("subagent.zig");
test "VirtualIo: fixture injection and consumption" {
    const a = std.testing.allocator;
    var io = VirtualIo.init(a);
    defer io.deinit();
    try loadFixture(&io, a, "deepseek", FIXTURES.deepseek_chat);
    try std.testing.expect(io.read_queue.items.len > 0);
    const written = try io.consumeWrites(a);
    defer a.free(written);
}
test "Parallel TUI Merge: dual-stream merge without race conditions" {
    const a = std.testing.allocator;
    var mmap_buf: [4096]u8 align(std.mem.page_size) = undefined;
    @memset(&mmap_buf, 0);
    const mmap: []align(std.mem.page_size) u8 = mmap_buf[0..];
    var pool = subagent.WorkerPool.init(a, mmap);
    const h_id = try pool.spawnHydrator("How to use std.Build in Zig 0.16?");
    const v_id = try pool.spawnVerifier("const x = 1"); // trivial diff
    pool.complete(h_id, FIXTURES.context7_zig_docs);
    pool.complete(v_id, "Build: PASS");
    const h_result = pool.poll(h_id);
    try std.testing.expect(h_result != null);
    try std.testing.expect(std.mem.indexOf(u8, h_result.?, "std.Build") != null);
    const v_result = pool.poll(v_id);
    try std.testing.expect(v_result != null);
    try std.testing.expect(std.mem.indexOf(u8, v_result.?, "PASS") != null);
    try std.testing.expectEqual(@as(u32, 0x7C242080), pool.arena.magic);
    try std.testing.expectEqual(@as(u8, 0), pool.arena.active_hydrators); // completed → decremented
    try std.testing.expectEqual(@as(u8, 0), pool.arena.active_verifiers);
}
test "Memory Plane: ledger append after mocked transaction" {
    const a = std.testing.allocator;
    var mmap_buf: [4096]u8 align(std.mem.page_size) = undefined;
    @memset(&mmap_buf, 0);
    const mmap: []align(std.mem.page_size) u8 = mmap_buf[0..];
    var pool = subagent.WorkerPool.init(a, mmap);
    const s_id = try pool.spawnSynthesizer("ZetaFlow eBPF architecture");
    try std.testing.expectEqual(@as(u8, 1), pool.arena.active_synthesizers);
    const research = "14 nodes synthesized: eBPF maps, XDP hooks, tracepoints, memory barriers";
    pool.complete(s_id, research);
    try std.testing.expectEqual(@as(u8, 0), pool.arena.active_synthesizers);
    const result = pool.poll(s_id);
    try std.testing.expect(result != null);
    try std.testing.expect(std.mem.indexOf(u8, result.?, "14 nodes") != null);
}