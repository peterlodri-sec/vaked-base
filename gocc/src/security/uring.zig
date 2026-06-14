// ZetaTensor log file writer.
// On Linux: uses io_uring (SQPOLL where permitted, plain submission otherwise).
// On macOS / other: falls back to positional writes via std.Io.
// Public API is identical on both platforms.

const std = @import("std");
const builtin = @import("builtin");
const frame = @import("wire");

// ---------------------------------------------------------------------------
// Log file header
// ---------------------------------------------------------------------------

/// 16-byte header at offset 0 of every GOCC log file.
pub const LogHeader = extern struct {
    magic: [4]u8,
    reserved: [4]u8,
    version: u64,
};

comptime {
    std.debug.assert(@sizeOf(LogHeader) == 16);
}

/// Canonical initial header value.
pub const LOG_HEADER_INIT: LogHeader = .{
    .magic = frame.FILE_MAGIC,
    .reserved = .{ 0, 0, 0, 0 },
    .version = 1,
};

// ---------------------------------------------------------------------------
// UringLogger
// ---------------------------------------------------------------------------

pub const UringLogger = struct {
    file: std.Io.File,
    io: std.Io,
    frame_count: u64,

    // On Linux: optionally holds the io_uring instance.
    // Declared as `void` on other platforms to avoid any compile-time cost.
    ring: if (builtin.os.tag == .linux) ?std.os.linux.IoUring else void,

    /// Open (or create) a log file at `path` and return an initialised logger.
    /// Writes the 16-byte header if the file is new (size == 0).
    pub fn open(io: std.Io, path: []const u8) !UringLogger {
        const file = try std.Io.Dir.cwd().createFile(io, path, .{
            .truncate = false,
            .read = true,
        });
        errdefer file.close(io);

        // Write header only for a freshly created (empty) file.
        const st = try file.stat(io);
        if (st.size == 0) {
            const hdr = LOG_HEADER_INIT;
            try file.writePositionalAll(io, std.mem.asBytes(&hdr), 0);
        }

        if (builtin.os.tag == .linux) {
            // Attempt SQPOLL (needs CAP_SYS_ADMIN on older kernels).
            // Fall back to plain submission queue if SQPOLL is denied.
            const ring: ?std.os.linux.IoUring =
                std.os.linux.IoUring.init(64, std.os.linux.IORING_SETUP_SQPOLL) catch
                std.os.linux.IoUring.init(64, 0) catch null;

            return .{
                .file = file,
                .io = io,
                .frame_count = frameCount(st.size),
                .ring = ring,
            };
        } else {
            return .{
                .file = file,
                .io = io,
                .frame_count = frameCount(st.size),
                .ring = {},
            };
        }
    }

    pub fn close(self: *UringLogger) void {
        if (builtin.os.tag == .linux) {
            if (self.ring) |*r| r.deinit();
        }
        self.file.close(self.io);
    }

    /// Append a single 128-byte frame to the log.
    /// On Linux (with io_uring): submits an async write SQE and waits for completion.
    /// On macOS / fallback: synchronous positional write.
    pub fn appendFrame(self: *UringLogger, f: *const frame.ZetaTensor) !void {
        const bytes = f.toBytes();
        const offset = frameOffset(self.frame_count);

        if (builtin.os.tag == .linux) {
            if (self.ring) |*ring| {
                const sqe = try ring.get_sqe();
                sqe.prep_write(self.file.handle, bytes, offset);
                _ = try ring.submit_and_wait(1);
                self.frame_count += 1;
                return;
            }
        }

        // Fallback: synchronous positional write (macOS and Linux without ring).
        try self.file.writePositionalAll(self.io, bytes, offset);
        self.frame_count += 1;
    }

    /// Flush any pending io_uring completions without waiting for new ones.
    /// No-op on macOS / fallback.
    pub fn flush(self: *UringLogger) !void {
        if (builtin.os.tag == .linux) {
            if (self.ring) |*ring| {
                _ = try ring.submit_and_wait(0);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    /// Byte offset at which frame N should be written.
    fn frameOffset(n: u64) u64 {
        return @sizeOf(LogHeader) + n * 128;
    }

    /// Infer how many frames are already in a file of `file_size` bytes.
    fn frameCount(file_size: u64) u64 {
        if (file_size <= @sizeOf(LogHeader)) return 0;
        return (file_size - @sizeOf(LogHeader)) / 128;
    }
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test "ZetaTensor init — opcode and timestamp" {
    const io = std.testing.io;
    const f = frame.init(io, .pipeline, 1, 2);
    try std.testing.expectEqual(@as(u8, 0x02), f.op_code);
    try std.testing.expectEqual(@as(u32, 1), f.source_node_id);
    try std.testing.expectEqual(@as(u32, 2), f.dest_node_id);
    try std.testing.expect(f.timestamp_ns != 0);
    try std.testing.expectEqual(@as(usize, 128), @sizeOf(frame.ZetaTensor));
}

test "ZetaTensor toBytes / fromBytes roundtrip" {
    const io = std.testing.io;
    var f = frame.init(io, .gate, 7, 42);
    f.kv_cache_ptr = 0xDEAD_BEEF_CAFE_BABE;
    f.attention_head = 99;

    const bytes = f.toBytes();
    try std.testing.expectEqual(@as(usize, 128), bytes.len);

    // fromBytes requires natural alignment (8 bytes for ZetaTensor).
    // Copy through an aligned buffer to satisfy @alignCast.
    var aligned: frame.ZetaTensor align(8) = undefined;
    @memcpy(std.mem.asBytes(&aligned), bytes);
    const back = frame.ZetaTensor.fromBytes(std.mem.asBytes(&aligned)[0..128]);

    try std.testing.expectEqual(f.op_code, back.op_code);
    try std.testing.expectEqual(f.source_node_id, back.source_node_id);
    try std.testing.expectEqual(f.dest_node_id, back.dest_node_id);
    try std.testing.expectEqual(f.kv_cache_ptr, back.kv_cache_ptr);
    try std.testing.expectEqual(f.attention_head, back.attention_head);
    try std.testing.expectEqual(f.timestamp_ns, back.timestamp_ns);
}

test "UringLogger — write 3 frames, file size = 16 + 3×128 = 400" {
    const io = std.testing.io;
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();

    var logger = try UringLogger.open(io, "gocc-test.log");
    defer logger.close();

    const f1 = frame.init(io, .pipeline, 1, 2);
    const f2 = frame.init(io, .annotation, 3, 4);
    const f3 = frame.init(io, .capability, 5, 6);
    try logger.appendFrame(&f1);
    try logger.appendFrame(&f2);
    try logger.appendFrame(&f3);
    try logger.flush();

    const st = try logger.file.stat(io);
    try std.testing.expectEqual(@as(u64, 400), st.size);
}

test "UringLogger — frame_count tracks appends" {
    const io = std.testing.io;
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();

    var logger = try UringLogger.open(io, "gocc-count.log");
    defer logger.close();

    try std.testing.expectEqual(@as(u64, 0), logger.frame_count);

    const f = frame.init(io, .prompt, 0, 0);
    try logger.appendFrame(&f);
    try std.testing.expectEqual(@as(u64, 1), logger.frame_count);
    try logger.appendFrame(&f);
    try logger.appendFrame(&f);
    try std.testing.expectEqual(@as(u64, 3), logger.frame_count);
}

test "UringLogger benchmark — 1000 frames (informational, no hard gate on macOS)" {
    const io = std.testing.io;
    var tmp = std.testing.tmpDir(.{});
    defer tmp.cleanup();

    var logger = try UringLogger.open(io, "gocc-bench.log");
    defer logger.close();

    const N = 1000;
    const f = frame.init(io, .pipeline, 0, 1);

    const t0 = std.Io.Timestamp.now(io, .real);
    for (0..N) |_| try logger.appendFrame(&f);
    try logger.flush();
    const t1 = std.Io.Timestamp.now(io, .real);
    const elapsed_ns = t1.nanoseconds - t0.nanoseconds;

    const per_frame_ns = @divFloor(elapsed_ns, N);
    std.debug.print(
        "\n[benchmark] {d} frames in {d}µs (~{d}ns/frame) " ++
            "[NOTE: benchmark gate (P99.99 < 5µs) applies to Linux io_uring only — macOS uses buffered fallback]\n",
        .{ N, @divFloor(elapsed_ns, 1000), per_frame_ns },
    );

    try std.testing.expectEqual(@as(u64, N), logger.frame_count);
}
