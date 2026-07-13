//! memgraph_test — offline unit tests for the memgraph module.
//!
//! These tests exercise the generic framing functions (`sendFrameWriter`,
//! `recvFrameReader`) and `Query.callersOf` using in-memory buffers only.
//! No real sockets are opened.
//!
//! Test coverage:
//!   1. Framing codec against known byte vectors (encode → decode roundtrip)
//!   2. Partial-read reassembly with a chunked in-memory reader
//!   3. Oversized-response rejection
//!   4. Request-builder helper output (`Query.callersOf`)
//!   5. Edge cases: empty frame, single-byte frame, frame at capacity boundary
//!
//! Run with:  zig test memgraph_test.zig --mod memgraph::AG-UI/Core/memgraph.zig
//! Or if integrated into a build.zig:
//!   const tests = b.addTest(.{ .root_source_file = b.path("AG-UI/Core/memgraph_test.zig") });

const std = @import("std");
const memgraph = @import("AG-UI/Core/memgraph.zig");

// ── Test helpers ────────────────────────────────────────────────────────────

/// A `std.io.Reader` wrapper that artificially limits each `read()` call to at
/// most `chunk_size` bytes, even when the underlying FixedBufferStream has more
/// available. This simulates partial reads from a real socket.
fn ChunkedReader(comptime chunk_size: usize) type {
    return struct {
        inner: std.io.FixedBufferStream([]const u8),
        eof: bool = false,

        const Self = @This();

        pub fn init(data: []const u8) Self {
            return .{ .inner = std.io.fixedBufferStream(data) };
        }

        pub fn read(self: *Self, dest: []u8) !usize {
            if (self.eof) return 0;
            if (self.inner.pos >= self.inner.buffer.len) {
                self.eof = true;
                return 0;
            }
            const end = @min(self.inner.pos + chunk_size, self.inner.buffer.len);
            const n = end - self.inner.pos;
            @memcpy(dest[0..n], self.inner.buffer[self.inner.pos..end]);
            self.inner.pos = end;
            if (self.inner.pos >= self.inner.buffer.len) {
                self.eof = true;
            }
            return n;
        }

        pub fn reader(self: *Self) std.io.Reader(*Self) {
            return .{ .context = self, .readFn = readFn };
        }

        fn readFn(context: *Self, dest: []u8) anyerror!usize {
            return context.read(dest);
        }
    };
}

/// A test helper: roundtrip `data` through `sendFrameWriter` → in-memory buffer
/// → `recvFrameReader`, asserting the result equals the original `data`.
fn testRoundtrip(allocator: std.mem.Allocator, data: []const u8) !void {
    var buf: [4096]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    // Encode
    try memgraph.sendFrameWriter(fbs.writer(), data);

    // Decode
    const written = fbs.getWritten();
    var reader_impl = ChunkedReader(128).init(written);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(allocator, reader);
    defer allocator.free(result);

    try std.testing.expectEqualStrings(data, result);
}

// ── 1. Framing codec: known byte vectors ────────────────────────────────────

test "framing: encode-decode roundtrip — simple JSON" {
    const data =
        \\{"jsonrpc":"2.0","id":1,"result":{"callers":["main","init"]}}
    ;
    try testRoundtrip(std.testing.allocator, data);
}

test "framing: encode-decode roundtrip — empty string" {
    try testRoundtrip(std.testing.allocator, "");
}

test "framing: encode-decode roundtrip — single character" {
    try testRoundtrip(std.testing.allocator, "X");
}

test "framing: encode-decode roundtrip — contains embedded newline-like escapes" {
    // The data contains JSON-escaped \n but no literal newline.
    // This ensures the delimiter detection isn't confused by escaped content.
    const data =
        \\{"text":"line1\\nline2\\nline3","done":true}
    ;
    try testRoundtrip(std.testing.allocator, data);
}

test "framing: encode appends exactly one newline" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    const data = "{\"a\":1}";
    try memgraph.sendFrameWriter(fbs.writer(), data);

    const written = fbs.getWritten();
    try std.testing.expectEqual(data.len + 1, written.len);
    try std.testing.expectEqualStrings(data, written[0..data.len]);
    try std.testing.expectEqual(memgraph.FRAME_DELIMITER, written[data.len]);
}

test "framing: encode empty string produces single newline" {
    var buf: [64]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    try memgraph.sendFrameWriter(fbs.writer(), "");

    const written = fbs.getWritten();
    try std.testing.expectEqual(@as(usize, 1), written.len);
    try std.testing.expectEqual(memgraph.FRAME_DELIMITER, written[0]);
}

test "framing: decode empty frame (just newline) returns empty string" {
    const framed = "\n";
    var reader_impl = ChunkedReader(128).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings("", result);
}

test "framing: decode trailing data after newline is ignored" {
    // The recvFrameReader should return only the first line and ignore
    // anything after the delimiter.
    const framed = "{\"a\":1}\n{\"b\":2}\n";
    var reader_impl = ChunkedReader(128).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings("{\"a\":1}", result);
}

// ── 2. Partial-read reassembly ──────────────────────────────────────────────

test "partial-read: frame delivered in 1-byte chunks" {
    const msg = "{\"jsonrpc\":\"2.0\",\"result\":{\"ok\":true}}";
    const framed = try std.fmt.allocPrint(std.testing.allocator, "{s}\n", .{msg});
    defer std.testing.allocator.free(framed);

    var reader_impl = ChunkedReader(1).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings(msg, result);
}

test "partial-read: frame delivered in 7-byte chunks (odd alignment)" {
    const msg = "{\"callers\":[\"alpha\",\"beta\",\"gamma\",\"delta\",\"epsilon\"]}";
    const framed = try std.fmt.allocPrint(std.testing.allocator, "{s}\n", .{msg});
    defer std.testing.allocator.free(framed);

    var reader_impl = ChunkedReader(7).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings(msg, result);
}

test "partial-read: newline is the very first byte (larger chunks)" {
    const framed = "\n{\"ignored\":true}\n";
    var reader_impl = ChunkedReader(16).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings("", result);
}

test "partial-read: newline arrives in a separate chunk from data" {
    // Simulate the case where the newline arrives in a subsequent recvfrom call.
    // We use ChunkedReader with stride = data.len, so the first read gets all
    // the data and the second read gets the newline.
    const data = "{\"x\":1}";
    const framed = try std.fmt.allocPrint(std.testing.allocator, "{s}\n", .{data});
    defer std.testing.allocator.free(framed);

    var reader_impl = ChunkedReader(data.len).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings(data, result);
}

test "partial-read: newline splits across chunk boundary" {
    // With chunk_size=1, the '\n' after the data arrives in its own read() call.
    const msg = "hello";
    const framed = try std.fmt.allocPrint(std.testing.allocator, "{s}\n", .{msg});
    defer std.testing.allocator.free(framed);

    var reader_impl = ChunkedReader(1).init(framed);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(std.testing.allocator, reader);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings(msg, result);
}

test "partial-read: very large frame at capacity boundary" {
    const allocator = std.testing.allocator;

    // Build a frame exactly at MAX_RESPONSE_BYTES - 1 (the largest allowed).
    const size = memgraph.MAX_RESPONSE_BYTES - 1;
    const payload = try allocator.alloc(u8, size);
    defer allocator.free(payload);
    @memset(payload, 'A');

    var framed_buf = try std.ArrayList(u8).initCapacity(allocator, size + 1);
    defer framed_buf.deinit();
    try framed_buf.appendSlice(payload);
    try framed_buf.append(memgraph.FRAME_DELIMITER);

    var reader_impl = ChunkedReader(511).init(framed_buf.items);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(allocator, reader);
    defer allocator.free(result);
    try std.testing.expectEqual(size, result.len);
    try std.testing.expectEqualStrings(payload, result);
}

// ── 3. Oversized-response rejection ─────────────────────────────────────────

test "oversized: exactly MAX_RESPONSE_BYTES + 1 with delimiter rejected" {
    const allocator = std.testing.allocator;

    const size = memgraph.MAX_RESPONSE_BYTES + 1; // one byte over
    const payload = try allocator.alloc(u8, size);
    defer allocator.free(payload);
    @memset(payload, 'B');
    payload[size - 1] = memgraph.FRAME_DELIMITER; // newline at the end

    var reader_impl = ChunkedReader(4096).init(payload);
    const reader = reader_impl.reader();
    const result = memgraph.recvFrameReader(allocator, reader);
    try std.testing.expectError(error.ResponseTooLarge, result);
}

test "oversized: well over MAX_RESPONSE_BYTES without delimiter" {
    const allocator = std.testing.allocator;

    const size = memgraph.MAX_RESPONSE_BYTES + 4096;
    const payload = try allocator.alloc(u8, size);
    defer allocator.free(payload);
    @memset(payload, 'C');
    // No newline — just a huge blob.

    var reader_impl = ChunkedReader(4096).init(payload);
    const reader = reader_impl.reader();
    const result = memgraph.recvFrameReader(allocator, reader);
    try std.testing.expectError(error.ResponseTooLarge, result);
}

test "oversized: growing through multiple chunks crosses limit" {
    const allocator = std.testing.allocator;

    // Build data that grows the internal buffer through several iterations
    // before the limit check fires. Use chunk_size=RECV_CHUNK to exercise
    // the capacity-growth path.
    const size = memgraph.MAX_RESPONSE_BYTES + 1;
    const payload = try allocator.alloc(u8, size);
    defer allocator.free(payload);
    @memset(payload, 'D');
    payload[size - 1] = '\n';

    const recv_chunk: usize = if (@hasDecl(memgraph, "RECV_CHUNK")) memgraph.RECV_CHUNK else 4096;

    var reader_impl = ChunkedReader(recv_chunk).init(payload);
    const reader = reader_impl.reader();
    const result = memgraph.recvFrameReader(allocator, reader);
    try std.testing.expectError(error.ResponseTooLarge, result);
}

test "oversized: empty reader returns ConnectionClosed" {
    const empty: []const u8 = &.{};
    var reader_impl = ChunkedReader(128).init(empty);
    const reader = reader_impl.reader();
    const result = memgraph.recvFrameReader(std.testing.allocator, reader);
    try std.testing.expectError(error.ConnectionClosed, result);
}

// ── 4. Request-builder helper output ────────────────────────────────────────

test "Query.callersOf: simple symbol" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "src/main.zig:main");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"src/main.zig:main\"}}}",
        req,
    );
}

test "Query.callersOf: symbol with double-quote" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "say \"hello\"");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"say \\\"hello\\\"\"}}}",
        req,
    );
}

test "Query.callersOf: symbol with backslash" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "path\\to\\symbol");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"path\\\\to\\\\symbol\"}}}",
        req,
    );
}

test "Query.callersOf: symbol with newline escape" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "line1\nline2");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"line1\\nline2\"}}}",
        req,
    );
}

test "Query.callersOf: symbol with tab and carriage-return" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "col1\tcol2\r");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"col1\\tcol2\\r\"}}}",
        req,
    );
}

test "Query.callersOf: empty symbol" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"\"}}}",
        req,
    );
}

test "Query.callersOf: fully-qualified Zig symbol" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "memgraph.zig:Query.callersOf");
    defer std.testing.allocator.free(req);
    try std.testing.expectEqualStrings(
        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"memgraph.zig:Query.callersOf\"}}}",
        req,
    );
}

test "Query.callersOf: output is valid NDJSON (no embedded newline)" {
    const req = try memgraph.Query.callersOf(std.testing.allocator, "test\nsymbol");
    defer std.testing.allocator.free(req);
    // The output must not contain a literal \n — the newline in the symbol
    // must be escaped as \\n.
    try std.testing.expect(std.mem.indexOfScalar(u8, req, '\n') == null);
    // Verify the escape sequence is present.
    try std.testing.expect(std.mem.indexOf(u8, req, "\\n") != null);
}

// ── 5. Roundtrip: Query.callersOf → sendFrameWriter → recvFrameReader ─────

test "roundtrip: Query.callersOf through framing codec" {
    const allocator = std.testing.allocator;

    const req = try memgraph.Query.callersOf(allocator, "daemons/openrouterd/src/seccomp.zig:apply");
    defer allocator.free(req);

    var buf: [4096]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    try memgraph.sendFrameWriter(fbs.writer(), req);

    const written = fbs.getWritten();
    var reader_impl = ChunkedReader(64).init(written);
    const reader = reader_impl.reader();
    const result = try memgraph.recvFrameReader(allocator, reader);
    defer allocator.free(result);

    try std.testing.expectEqualStrings(req, result);
}

// ── 6. Writer contract: sendFrameWriter with limited writer ─────────────────

/// A writer that only accepts `max_write` bytes per `write()` call,
/// simulating a constrained output buffer.
fn LimitedWriter(comptime max_write: usize) type {
    return struct {
        inner: *std.io.FixedBufferStream([]u8),

        const Self = @This();

        pub fn write(self: Self, bytes: []const u8) !usize {
            const n = @min(bytes.len, max_write);
            _ = try self.inner.write(bytes[0..n]);
            return n;
        }

        pub fn writeAll(self: Self, bytes: []const u8) !void {
            var pos: usize = 0;
            while (pos < bytes.len) {
                const n = try self.write(bytes[pos..]);
                if (n == 0) return error.OutOfMemory;
                pos += n;
            }
        }

        pub fn writeByte(self: Self, byte: u8) !void {
            _ = try self.write(&[_]u8{byte});
        }

        pub fn writer(self: *Self) std.io.Writer(*Self) {
            return .{ .context = self, .writeFn = writeFn };
        }

        fn writeFn(context: *Self, bytes: []const u8) anyerror!usize {
            return context.write(bytes);
        }
    };
}

test "writer: sendFrameWriter handles short writes via LimitedWriter" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    var limited = LimitedWriter(1).init(&fbs);

    const data = "{\"a\":1}";
    try memgraph.sendFrameWriter(limited.writer(), data);

    const written = fbs.getWritten();
    try std.testing.expectEqual(data.len + 1, written.len);
    try std.testing.expectEqualStrings(data, written[0..data.len]);
    try std.testing.expectEqual(memgraph.FRAME_DELIMITER, written[data.len]);
}
