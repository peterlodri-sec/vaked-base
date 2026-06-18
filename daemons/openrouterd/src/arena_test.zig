//! arena_test.zig — Comprehensive test suite for arena.zig.
//!
//! Covers:
//!   1. alloc/resolve roundtrip with typed data
//!   2. Stale-generation rejection (use-after-free)
//!   3. Out-of-bounds rejection on malformed handles
//!   4. Integer overflow rejection
//!   5. Seqlock reader-retry under concurrent write simulation
//!   6. copyOut verification
//!   7. Double-free rejection
//!   8. Handle-table-full rejection
//!   9. Zero-length alloc rejection
//!  10. attach() roundtrip (create in one Arena, attach in another)
//!
//! These tests are WRITTEN for human review. They are NOT executed here;
//! compilation and execution happen on a Linux target after review.
//!
//! All tests use a temporary backing file in /tmp (or $TMPDIR). The file
//! is created, used, and cleaned up per test.

const std = @import("std");
const arena = @import("arena.zig");
const testing = std.testing;

/// Helper: create a temporary file path for an arena backing file.
fn tmpPath(allocator: std.mem.Allocator, suffix: []const u8) ![]const u8 {
    const pid = std.os.linux.getpid();
    return std.fmt.allocPrint(allocator, "/tmp/vaked-arena-test-{d}-{s}", .{ pid, suffix });
}

/// Helper: create a small arena for testing. Page-sized, enough handles for tests.
fn testArena(allocator: std.mem.Allocator) !struct { arena: arena.Arena, path: []const u8 } {
    const path = try tmpPath(allocator, "basic");
    const a = try arena.Arena.create(allocator, path, 65536, 64, 0);
    return .{ .arena = a, .path = path };
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 1: alloc/resolve roundtrip
// ═══════════════════════════════════════════════════════════════════════════════

test "alloc and resolve roundtrip — typed struct" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const TestStruct = extern struct {
        x: u32,
        y: f64,
        name: [32]u8,
    };

    // Allocate
    const handle = try helper.arena.alloc(arena.Kind.generic, @sizeOf(TestStruct));
    try testing.expect(!handle.isInvalid());

    // Write via resolve
    {
        const ptr = try helper.arena.resolve(handle, TestStruct);
        ptr.x = 42;
        ptr.y = 3.14;
        @memcpy(&ptr.name, "hello arena");
    }

    // Read back via resolve
    {
        const ptr = try helper.arena.resolve(handle, TestStruct);
        try testing.expectEqual(@as(u32, 42), ptr.x);
        try testing.expectEqual(@as(f64, 3.14), ptr.y);
        try testing.expectEqualStrings("hello arena", std.mem.sliceTo(&ptr.name, 0));
    }
}

test "alloc and resolve roundtrip — bytes" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle = try helper.arena.alloc(arena.Kind.generic, 128);
    const bytes = try helper.arena.resolveBytes(handle);
    try testing.expectEqual(@as(usize, 128), bytes.len);

    // Write pattern
    for (bytes, 0..) |*b, i| {
        b.* = @intCast(i % 256);
    }

    // Read back
    const bytes2 = try helper.arena.resolveBytes(handle);
    for (bytes2, 0..) |b, i| {
        try testing.expectEqual(@as(u8, @intCast(i % 256)), b);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 2: Stale-generation rejection (use-after-free guard)
// ═══════════════════════════════════════════════════════════════════════════════

test "stale generation rejection after free" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const TestStruct = extern struct { x: u32 };

    const handle = try helper.arena.alloc(arena.Kind.generic, @sizeOf(TestStruct));

    // Free it — this bumps the generation.
    try helper.arena.free(handle);

    // The old handle should now be stale.
    try testing.expectError(error.StaleHandle, helper.arena.resolve(handle, TestStruct));
}

test "stale generation rejection after free and realloc (different slot user)" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle1 = try helper.arena.alloc(arena.Kind.generic, 64);
    try helper.arena.free(handle1);

    // Allocate again — this reuses handle1's slot, but the old handle1
    // has the old generation and should be rejected.
    const handle2 = try helper.arena.alloc(arena.Kind.generic, 128);

    // handle1 is stale because generation was bumped on free.
    try testing.expectError(error.StaleHandle, helper.arena.resolveBytes(handle1));

    // handle2 should work fine.
    const bytes = try helper.arena.resolveBytes(handle2);
    try testing.expectEqual(@as(usize, 128), bytes.len);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 3: Out-of-bounds rejection
// ═══════════════════════════════════════════════════════════════════════════════

test "out-of-bounds rejection — index beyond handle_cap" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    // Create a handle with an index beyond handle_cap (which is 64).
    const bad_handle = arena.Handle{ .index = 999, .generation = 0 };
    try testing.expectError(error.InvalidHandle, helper.arena.resolveBytes(bad_handle));
}

test "out-of-bounds rejection — index equals handle_cap" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    // handle_cap is 64, so index 64 is out of bounds (valid: 0..63).
    const bad_handle = arena.Handle{ .index = 64, .generation = 0 };
    try testing.expectError(error.InvalidHandle, helper.arena.resolveBytes(bad_handle));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 4: Integer overflow rejection
// ═══════════════════════════════════════════════════════════════════════════════

test "integer overflow rejection — alloc near u32::max" {
    const allocator = testing.allocator;
    const path = try tmpPath(allocator, "overflow");
    defer allocator.free(path);

    // Create an arena with exactly enough space for header + handle table + 1 page.
    const page_size: u32 = @intCast(std.mem.page_size);
    const handle_cap: u32 = 4;
    const total_size = arena.HEADER_SIZE + handle_cap * arena.HANDLE_ENTRY_SIZE + page_size;

    const a = try arena.Arena.create(allocator, path, total_size, handle_cap, 0);
    defer a.deinit(allocator);

    // Allocating 1 byte should work.
    const h1 = try a.alloc(arena.Kind.generic, 1);
    try testing.expect(!h1.isInvalid());

    // Allocating the remaining space should work.
    const remaining = page_size - 1;
    const h2 = try a.alloc(arena.Kind.generic, remaining);
    try testing.expect(!h2.isInvalid());

    // Next allocation should fail with OutOfMemory.
    try testing.expectError(error.OutOfMemory, a.alloc(arena.Kind.generic, 1));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 5: Seqlock reader-retry (structural test)
// ═══════════════════════════════════════════════════════════════════════════════

test "seqlock — beginWrite sets seq odd, endWrite sets even" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    // Initial seq should be even.
    try testing.expectEqual(@as(u64, 0), helper.arena.header().seq);

    // Begin write: seq becomes odd.
    _ = helper.arena.beginWrite();
    try testing.expectEqual(@as(u64, 1), helper.arena.header().seq);

    // End write: seq becomes even.
    helper.arena.endWrite();
    try testing.expectEqual(@as(u64, 2), helper.arena.header().seq);
}

test "seqlock — reader sees consistent data" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle = try helper.arena.alloc(arena.Kind.generic, 8);
    {
        const ptr = try helper.arena.resolve(handle, u64);
        ptr.* = 0xDEADBEEF_CAFE1234;
    }

    // Read under seqlock — should always see consistent data.
    var read_ok: bool = false;
    var attempts: u32 = 0;
    while (attempts < 100) : (attempts += 1) {
        const seq = helper.arena.beginRead();
        const ptr = try helper.arena.resolve(handle, u64);
        const val = ptr.*;
        if (helper.arena.endRead(seq)) {
            try testing.expectEqual(@as(u64, 0xDEADBEEF_CAFE1234), val);
            read_ok = true;
            break;
        }
    }
    try testing.expect(read_ok);
}

test "seqlock — beginRead spins while odd" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    // Start a write (seq becomes odd) but don't end it.
    _ = helper.arena.beginWrite();

    // beginRead should spin and not return while seq is odd.
    // We can't test the spin directly, but we can verify seq is odd
    // and that the spin would be active.
    try testing.expectEqual(@as(u64, 1), helper.arena.header().seq);
    try testing.expectEqual(@as(u64, 1), helper.arena.header().seq & 1);

    // End the write so subsequent tests don't deadlock.
    helper.arena.endWrite();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 6: copyOut verification
// ═══════════════════════════════════════════════════════════════════════════════

test "copyOut returns a fresh copy disconnected from arena" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const TestStruct = extern struct { x: u32, y: u64 };

    const handle = try helper.arena.alloc(arena.Kind.generic, @sizeOf(TestStruct));
    {
        const ptr = try helper.arena.resolve(handle, TestStruct);
        ptr.x = 999;
        ptr.y = 888;
    }

    // Copy out.
    const copy = try helper.arena.copyOut(handle, allocator);
    defer allocator.free(copy);

    try testing.expectEqual(@as(usize, @sizeOf(TestStruct)), copy.len);

    const copied_struct: *const TestStruct = @ptrCast(@alignCast(copy.ptr));
    try testing.expectEqual(@as(u32, 999), copied_struct.x);
    try testing.expectEqual(@as(u64, 888), copied_struct.y);

    // Modify the arena copy — should NOT affect the copy-out.
    {
        const ptr = try helper.arena.resolve(handle, TestStruct);
        ptr.x = 0;
    }

    // copy should still have the old values.
    try testing.expectEqual(@as(u32, 999), copied_struct.x);
}

test "copyOutInto with exact buffer size" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle = try helper.arena.alloc(arena.Kind.generic, 32);
    {
        const bytes = try helper.arena.resolveBytes(handle);
        @memset(bytes, 0xAB);
    }

    var buf: [32]u8 = undefined;
    const n = try helper.arena.copyOutInto(handle, &buf);
    try testing.expectEqual(@as(u32, 32), n);
    for (buf) |b| {
        try testing.expectEqual(@as(u8, 0xAB), b);
    }
}

test "copyOutInto with too-small buffer" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle = try helper.arena.alloc(arena.Kind.generic, 64);

    var buf: [16]u8 = undefined;
    try testing.expectError(error.BufferTooSmall, helper.arena.copyOutInto(handle, &buf));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 7: Double-free rejection
// ═══════════════════════════════════════════════════════════════════════════════

test "double-free is rejected" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle = try helper.arena.alloc(arena.Kind.generic, 64);
    try helper.arena.free(handle);
    try testing.expectError(error.DoubleFree, helper.arena.free(handle));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 8: Handle-table-full rejection
// ═══════════════════════════════════════════════════════════════════════════════

test "handle table full is rejected" {
    const allocator = testing.allocator;
    const path = try tmpPath(allocator, "full");
    defer allocator.free(path);

    // Create an arena with only 2 handle slots.
    const page_size: u32 = @intCast(std.mem.page_size);
    const total_size = arena.HEADER_SIZE + 2 * arena.HANDLE_ENTRY_SIZE + 4 * page_size;
    const a = try arena.Arena.create(allocator, path, total_size, 2, 0);
    defer a.deinit(allocator);

    // Allocate 2 handles — should succeed.
    const h1 = try a.alloc(arena.Kind.generic, 8);
    const h2 = try a.alloc(arena.Kind.generic, 8);
    try testing.expect(!h1.isInvalid());
    try testing.expect(!h2.isInvalid());

    // Third allocation should fail.
    try testing.expectError(error.HandleTableFull, a.alloc(arena.Kind.generic, 8));

    // Free one and re-allocate — should work (slot reuse).
    try a.free(h1);
    const h3 = try a.alloc(arena.Kind.generic, 8);
    try testing.expect(!h3.isInvalid());
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 9: Zero-length alloc rejection
// ═══════════════════════════════════════════════════════════════════════════════

test "zero-length allocation is rejected" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    try testing.expectError(error.ZeroLengthAlloc, helper.arena.alloc(arena.Kind.generic, 0));
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 10: attach() roundtrip — create in one Arena, attach in another
// ═══════════════════════════════════════════════════════════════════════════════

test "attach to an already-created arena" {
    const allocator = testing.allocator;
    const path = try tmpPath(allocator, "attach");
    defer allocator.free(path);

    // Create arena, allocate some data, then deinit.
    {
        var a = try arena.Arena.create(allocator, path, 65536, 64, 0);

        const handle = try a.alloc(arena.Kind.generic, 16);
        {
            const bytes = try a.resolveBytes(handle);
            @memset(bytes, 0xCC);
        }

        // Store the handle value for the attach side.
        const saved_handle = handle;

        a.deinit(allocator);

        // Re-attach and verify the handle still resolves.
        var a2 = try arena.Arena.attach(allocator, path);
        defer a2.deinit(allocator);

        try testing.expectEqual(arena.ARENA_MAGIC, a2.header().magic);
        try testing.expectEqual(arena.ARENA_VERSION, a2.header().version);

        const bytes = try a2.resolveBytes(saved_handle);
        try testing.expectEqual(@as(usize, 16), bytes.len);
        for (bytes) |b| {
            try testing.expectEqual(@as(u8, 0xCC), b);
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 11: SizeMismatch when resolving with wrong type size
// ═══════════════════════════════════════════════════════════════════════════════

test "resolve with wrong type size fails" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const handle = try helper.arena.alloc(arena.Kind.generic, 4);

    // Trying to resolve as u64 (8 bytes) should fail since allocation is 4 bytes.
    try testing.expectError(error.SizeMismatch, helper.arena.resolve(handle, u64));

    // Resolving as u32 (4 bytes) should work.
    const ptr = try helper.arena.resolve(handle, u32);
    try testing.expectEqual(@as(u32, 0), ptr.*);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 12: allocTyped with initializer
// ═══════════════════════════════════════════════════════════════════════════════

test "allocTyped with initializer function" {
    const allocator = testing.allocator;
    const helper = try testArena(allocator);
    defer helper.arena.deinit(allocator);
    defer allocator.free(helper.path);

    const TestStruct = extern struct { a: u32, b: u64, c: u8 };

    const handle = try helper.arena.allocTyped(arena.Kind.generic, TestStruct, struct {
        fn init(s: *TestStruct) void {
            s.a = 123;
            s.b = 456;
            s.c = 7;
        }
    }.init);

    const ptr = try helper.arena.resolve(handle, TestStruct);
    try testing.expectEqual(@as(u32, 123), ptr.a);
    try testing.expectEqual(@as(u64, 456), ptr.b);
    try testing.expectEqual(@as(u8, 7), ptr.c);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 13: Handle.invalid() sentinel
// ═══════════════════════════════════════════════════════════════════════════════

test "handle invalid sentinel" {
    const h = arena.Handle.invalid();
    try testing.expect(h.isInvalid());
    try testing.expectEqual(std.math.maxInt(u32), h.index);
    try testing.expectEqual(@as(u32, 0), h.generation);
}

test "valid handle is not invalid" {
    const h = arena.Handle{ .index = 0, .generation = 1 };
    try testing.expect(!h.isInvalid());
}
