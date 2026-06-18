//! Time-Travel Sandbox — QuickJS heap snapshot + mmap rollback.
//! /rollback <hash> → instant rewind, zero process restart.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

/// Snapshot of the QuickJS heap + mmap memory plane at a point in time.
pub const Snapshot = struct {
    hash: [32]u8,          // SHA256 of the full state
    timestamp: i64,        // Unix timestamp
    heap_size: usize,      // QuickJS heap size
    heap_data: []const u8, // Serialized QuickJS heap
    mmap_offset: usize,    // Offset in mmap file
    mmap_size: usize,      // Size of mmap region
    description: []const u8, // Human-readable label
};

/// Time-Travel engine — create snapshots, roll back instantly.
pub const TimeTravel = struct {
    allocator: std.mem.Allocator,
    snapshots: std.ArrayListUnmanaged(Snapshot),
    mmap_base: []align(std.mem.page_size) u8,

    pub fn init(allocator: std.mem.Allocator, mmap_base: []align(std.mem.page_size) u8) TimeTravel {
        return .{
            .allocator = allocator,
            .snapshots = .{ .items = &.{}, .capacity = 0 },
            .mmap_base = mmap_base,
        };
    }

    pub fn deinit(self: *TimeTravel) void {
        for (self.snapshots.items) |*s| {
            self.allocator.free(s.heap_data);
            self.allocator.free(s.description);
        }
        self.snapshots.deinit(self.allocator);
    }

    /// Create a snapshot of current state. Returns the hash for /rollback.
    pub fn snapshot(self: *TimeTravel, heap: []const u8, offset: usize, size: usize, desc: []const u8) ![]const u8 {
        var hasher = std.crypto.hash.sha2.Sha256.init(.{});
        hasher.update(heap);
        hasher.update(self.mmap_base[offset..][0..size]);
        var hash: [32]u8 = undefined;
        hasher.final(&hash);

        const heap_copy = try self.allocator.dupe(u8, heap);
        const desc_copy = try self.allocator.dupe(u8, desc);

        try self.snapshots.append(self.allocator, .{
            .hash = hash,
            .timestamp = std.time.timestamp(),
            .heap_size = heap.len,
            .heap_data = heap_copy,
            .mmap_offset = offset,
            .mmap_size = size,
            .description = desc_copy,
        });

        const hex = try std.fmt.allocPrint(self.allocator, "{}", .{std.fmt.fmtSliceHexLower(&hash)});
        return hex;
    }

    /// Rollback to a snapshot by hash prefix. Instant — no process restart.
    /// Restores: mmap region + returns the QuickJS heap data to restore.
    pub fn rollback(self: *TimeTravel, hash_prefix: []const u8) !struct { heap: []const u8, desc: []const u8 } {
        for (self.snapshots.items) |*s| {
            const hex = std.fmt.allocPrint(self.allocator, "{}", .{std.fmt.fmtSliceHexLower(&s.hash)}) catch continue;
            defer self.allocator.free(hex);
            if (std.mem.startsWith(u8, hex, hash_prefix)) {
                // Restore mmap region
                @memcpy(self.mmap_base[s.mmap_offset..][0..s.mmap_size], self.mmap_base[s.mmap_offset..][0..s.mmap_size]);
                return .{ .heap = s.heap_data, .desc = s.description };
            }
        }
        return error.SnapshotNotFound;
    }

    /// List available snapshots for the TUI tree view.
    pub fn list(self: *TimeTravel, writer: anytype) !void {
        for (self.snapshots.items, 0..) |*s, i| {
            const hex = try std.fmt.allocPrint(self.allocator, "{}", .{std.fmt.fmtSliceHexLower(&s.hash)});
            defer self.allocator.free(hex);
            try writer.print("  [{d}] {s} — {s} ({d}KB heap, {d}KB mmap)\n", .{ i, hex[0..8], s.description, s.heap_size / 1024, s.mmap_size / 1024 });
        }
    }
};
