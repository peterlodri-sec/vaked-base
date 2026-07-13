//! agui.zig — AG-UI (Agent-User Interface) SSE event core.
//! Pure Zig stdlib, zero external dependencies.
//!
//! Provides:
//!   1. AGUI_Event tagged union — 3 event kinds (chunk, tool_call, approval)
//!   2. serialize()            — emit exact JSON to any std.io.Writer
//!   3. frameSSE()             — wrap JSON in HTTP/1.1 chunked-transfer SSE frame
//!   4. sseResponseHeaders()   — emit HTTP/1.1 200 SSE response head
//!   5. EventQueue(T, cap)     — thread-safe fixed-capacity ring buffer
//!
//! ASSUMPTIONS (stated explicitly, per spec):
//!   1. Zig 0.16, stdlib only, x86_64-linux target. No external dependencies.
//!   2. All strings use fixed-capacity inline buffers — the entire AGUI_Event
//!      is trivially copyable (no heap pointers). This enables zero-allocation
//!      EventQueue push/pop hot path.
//!   3. tool_call.arguments_json holds pre-serialized raw JSON (emitted verbatim,
//!      not string-escaped). The producer is responsible for valid JSON.
//!   4. The EventQueue uses std.Thread.Mutex. On Linux this maps to futex(2)
//!      which IS in the 22-syscall seccomp allowlist.
//!   5. frameSSE() and sseResponseHeaders() are PURE byte producers. They touch
//!      NO sockets, NO files, NO syscalls. All socket syscalls belong in the
//!      caller's transport layer.
//!   6. All functions accept anytype writer; no dynamic dispatch overhead.
//!
//! SECCOMP / TRANSPORT GAP (HONEST — do not hand-wave):
//!   This module is the PURE SSE event core — it never calls bind, listen,
//!   accept4, setsockopt, or any socket-management syscall. An actual inbound
//!   SSE HTTP server requires at minimum:
//!
//!     socket()     — already in the 22-list
//!     setsockopt() — NOT in the 22-list  (SO_REUSEADDR, SO_REUSEPORT)
//!     bind()       — NOT in the 22-list
//!     listen()     — NOT in the 22-list
//!     accept4()    — NOT in the 22-list
//!
//!   Of these, setsockopt + bind + listen + accept4 are MISSING from the wired
//!   22-syscall allowlist [read, write, openat, close, socket, connect, sendto,
//!   recvfrom, epoll_create1, epoll_ctl, epoll_wait, mmap, munmap, mprotect,
//!   brk, exit, exit_group, getrandom, clock_gettime, futex, io_uring_setup,
//!   io_uring_enter].
//!
//!   Three options (the human decides; this module does NOT pick):
//!     (A) Start the listen-loop BEFORE seccomp is applied — create socket,
//!         setsockopt, bind, listen, THEN apply seccomp, THEN accept loop.
//!     (B) Extend the allowlist by ~4 syscalls: setsockopt, bind, listen,
//!         accept4 (and possibly getpeername for logging).
//!     (C) Run the SSE server as a separate unsandboxed front process that
//!         forwards events to the sandboxed daemon over a pre-connected
//!         socket (connect-only, within the 22-list).

const std = @import("std");

// ═══════════════════════════════════════════════════════════════════════════════
// Capacity constants — tune these for your workload
// ═══════════════════════════════════════════════════════════════════════════════

/// Maximum bytes in a chunk's `delta.content` string.
pub const MAX_CONTENT: usize = 8192;

/// Maximum bytes in a call_id / request_id string.
pub const MAX_CALL_ID: usize = 128;

/// Maximum bytes in a tool_name string.
pub const MAX_TOOL_NAME: usize = 128;

/// Maximum bytes in an approval description string.
pub const MAX_DESCRIPTION: usize = 1024;

/// Maximum bytes of pre-serialized tool-call arguments JSON.
pub const MAX_ARGUMENTS_JSON: usize = 8192;

// ═══════════════════════════════════════════════════════════════════════════════
// AGUI_Event — tagged union of all outbound SSE event kinds
// ═══════════════════════════════════════════════════════════════════════════════

pub const AGUI_Event = union(enum) {
    /// agent/chunk — streaming token delta for a single choice.
    /// JSON: {"event":"agent/chunk","payload":{"choice_index":<int>,"delta":{"content":"<str>"}}}
    chunk: struct {
        choice_index: u32,
        content_len: u16,
        content: [MAX_CONTENT]u8,
    },

    /// tool/call — worker is invoking a tool.
    /// JSON: {"event":"tool/call","payload":{"call_id":"<str>","tool_name":"<str>","arguments":<json-object>}}
    /// NOTE: arguments_json is emitted VERBATIM (no string escaping). Producer
    /// must supply valid, well-formed JSON bytes.
    tool_call: struct {
        call_id_len: u8,
        call_id: [MAX_CALL_ID]u8,
        tool_name_len: u8,
        tool_name: [MAX_TOOL_NAME]u8,
        arguments_len: u16,
        arguments_json: [MAX_ARGUMENTS_JSON]u8,
    },

    /// interaction/approval — worker needs human approval.
    /// JSON: {"event":"interaction/approval","payload":{"request_id":"<str>","description":"<str>"}}
    approval: struct {
        request_id_len: u8,
        request_id: [MAX_CALL_ID]u8,
        description_len: u16,
        description: [MAX_DESCRIPTION]u8,
    },
};

// ═══════════════════════════════════════════════════════════════════════════════
// JSON string escaping — pure, no allocation
// ═══════════════════════════════════════════════════════════════════════════════

/// Write `bytes` as a JSON string value to `writer`, with correct escaping of
///   " → \"
///   \ → \\
///   \n → \\n   (2 chars in JSON: backslash, n)
///   \r → \\r
///   \t → \\t
///   control chars (0x00–0x1F, except above) → \\u00XX
///
/// This function touches NO syscalls — pure byte transformation.
fn writeJsonString(bytes: []const u8, writer: anytype) !void {
    for (bytes) |b| {
        switch (b) {
            '\\' => try writer.writeAll("\\\\"),
            '"'  => try writer.writeAll("\\\""),
            '\n' => try writer.writeAll("\\n"),
            '\r' => try writer.writeAll("\\r"),
            '\t' => try writer.writeAll("\\t"),
            0x00...0x08, 0x0B, 0x0C, 0x0E...0x1F => {
                // control character → \u00XX
                try writer.writeAll("\\u00");
                const hi = (b >> 4) & 0xF;
                const lo = b & 0xF;
                try writer.writeByte(if (hi < 10) @as(u8, '0') + hi else @as(u8, 'a') + (hi - 10));
                try writer.writeByte(if (lo < 10) @as(u8, '0') + lo else @as(u8, 'a') + (lo - 10));
            },
            else => try writer.writeByte(b),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// serialize — emit the EXACT outbound JSON for one AGUI_Event
// ═══════════════════════════════════════════════════════════════════════════════

/// Serialize `event` as its canonical JSON wire format to `writer`.
/// Field names and order match the protocol specification verbatim.
/// Pure — touches NO sockets, NO files, NO syscalls.
pub fn serialize(event: AGUI_Event, writer: anytype) !void {
    switch (event) {
        .chunk => |c| {
            // {"event":"agent/chunk","payload":{"choice_index":<int>,"delta":{"content":"<str>"}}}
            try writer.writeAll("{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":");
            try std.fmt.formatInt(c.choice_index, 10, .lower, .{}, writer);
            try writer.writeAll(",\"delta\":{\"content\":\"");
            try writeJsonString(c.content[0..c.content_len], writer);
            try writer.writeAll("\"}}}");
        },
        .tool_call => |tc| {
            // {"event":"tool/call","payload":{"call_id":"<str>","tool_name":"<str>","arguments":<json-object>}}
            try writer.writeAll("{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"");
            try writeJsonString(tc.call_id[0..tc.call_id_len], writer);
            try writer.writeAll("\",\"tool_name\":\"");
            try writeJsonString(tc.tool_name[0..tc.tool_name_len], writer);
            try writer.writeAll("\",\"arguments\":");
            // arguments_json is pre-serialized — emit verbatim, no escaping
            try writer.writeAll(tc.arguments_json[0..tc.arguments_len]);
            try writer.writeAll("}}");
        },
        .approval => |a| {
            // {"event":"interaction/approval","payload":{"request_id":"<str>","description":"<str>"}}
            try writer.writeAll("{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"");
            try writeJsonString(a.request_id[0..a.request_id_len], writer);
            try writer.writeAll("\",\"description\":\"");
            try writeJsonString(a.description[0..a.description_len], writer);
            try writer.writeAll("\"}}");
        },
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// frameSSE — wrap serialized JSON as an HTTP/1.1 chunked SSE message
// ═══════════════════════════════════════════════════════════════════════════════

/// Frame one already-serialized event JSON as an SSE message over HTTP/1.1
/// chunked transfer encoding.
///
/// Output format (verbatim):
///   <hexlen>\r\n
///   data: <json_bytes>\n\n
///   \r\n
///
/// hexlen is the lowercase-hex byte count of the SSE payload
/// (the "data: " prefix + json_bytes + "\n\n" trailer, NOT including
/// the chunk-delimiter CRLFs).
///
/// Pure — touches NO sockets, NO files, NO syscalls.
pub fn frameSSE(json_bytes: []const u8, writer: anytype) !void {
    // SSE payload = "data: " + <json> + "\n\n"
    const sse_payload_len: usize = "data: ".len + json_bytes.len + "\n\n".len;

    // Chunk header: lowercase hex length + CRLF
    var hex_buf: [16]u8 = undefined;
    const hex_str = std.fmt.formatIntBuf(&hex_buf, sse_payload_len, 16, .lower, .{});
    try writer.writeAll(hex_str);
    try writer.writeAll("\r\n");

    // SSE message body
    try writer.writeAll("data: ");
    try writer.writeAll(json_bytes);
    try writer.writeAll("\n\n");

    // Chunk terminator CRLF
    try writer.writeAll("\r\n");
}

// ═══════════════════════════════════════════════════════════════════════════════
// sseResponseHeaders — emit the HTTP/1.1 200 SSE response head
// ═══════════════════════════════════════════════════════════════════════════════

/// Write the HTTP/1.1 200 OK response head for an SSE stream.
/// Headers: Content-Type: text/event-stream, Cache-Control: no-cache,
/// Connection: keep-alive, Transfer-Encoding: chunked.
///
/// Pure — touches NO sockets, NO files, NO syscalls.
pub fn sseResponseHeaders(writer: anytype) !void {
    try writer.writeAll(
        "HTTP/1.1 200 OK\r\n" ++
        "Content-Type: text/event-stream\r\n" ++
        "Cache-Control: no-cache\r\n" ++
        "Connection: keep-alive\r\n" ++
        "Transfer-Encoding: chunked\r\n" ++
        "\r\n",
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EventQueue — thread-safe fixed-capacity ring buffer
// ═══════════════════════════════════════════════════════════════════════════════

/// A bounded, thread-safe, fixed-capacity ring buffer for worker→emitter
/// event handoff. Zero allocation in the push/pop hot path.
///
/// Uses std.Thread.Mutex (futex on Linux — within the 22-syscall allowlist).
/// Suitable for single-producer/single-consumer usage; the mutex makes MP/MC
/// correct as well, at the cost of contention.
pub fn EventQueue(comptime T: type, comptime capacity: usize) type {
    return struct {
        const Self = @This();

        buf: [capacity]T = undefined,
        mutex: std.Thread.Mutex = .{},
        head: usize = 0,
        tail: usize = 0,
        count: usize = 0,

        /// Create an empty queue. No allocation.
        pub fn init() Self {
            return .{};
        }

        /// Push one event into the queue. Returns error.QueueFull if the
        /// queue is at capacity (non-blocking).
        pub fn push(self: *Self, event: T) error{QueueFull}!void {
            self.mutex.lock();
            defer self.mutex.unlock();

            if (self.count >= capacity) return error.QueueFull;

            self.buf[self.tail] = event;
            self.tail = if (self.tail + 1 >= capacity) 0 else self.tail + 1;
            self.count += 1;
        }

        /// Pop one event from the queue. Returns null if the queue is
        /// empty (non-blocking).
        pub fn pop(self: *Self) ?T {
            self.mutex.lock();
            defer self.mutex.unlock();

            if (self.count == 0) return null;

            const event = self.buf[self.head];
            self.head = if (self.head + 1 >= capacity) 0 else self.head + 1;
            self.count -= 1;
            return event;
        }

        /// Return the current number of queued events.
        pub fn len(self: *Self) usize {
            self.mutex.lock();
            defer self.mutex.unlock();
            return self.count;
        }

        /// True when no events are queued.
        pub fn isEmpty(self: *Self) bool {
            self.mutex.lock();
            defer self.mutex.unlock();
            return self.count == 0;
        }

        /// True when the queue cannot accept more events.
        pub fn isFull(self: *Self) bool {
            self.mutex.lock();
            defer self.mutex.unlock();
            return self.count >= capacity;
        }
    };
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXAMPLE — thin serve() sketch (ILLUSTRATIVE, NOT production)
// ═══════════════════════════════════════════════════════════════════════════════
//
// The function below is an EXAMPLE ONLY. It is NOT callable from a
// seccomp-sandboxed process because it requires bind, listen, accept4, and
// setsockopt — all of which are ABSENT from the 22-syscall allowlist.
//
// Syscalls used by this sketch (annotated):
//
//   socket()       — in 22-list  ✓
//   setsockopt()   — NOT in 22-list  ✗  (SO_REUSEADDR, TCP_NODELAY, …)
//   bind()         — NOT in 22-list  ✗
//   listen()       — NOT in 22-list  ✗
//   accept4()      — NOT in 22-list  ✗
//   write()        — in 22-list  ✓  (used by frameSSE → writer)
//   close()        — in 22-list  ✓
//   epoll_*        — in 22-list  ✓  (if you use epoll for multiplexing)
//
// Three resolution paths (human decides):
//   (A) Start the listen-loop BEFORE seccomp is applied: socket → setsockopt →
//       bind → listen → apply seccomp → accept loop. The accept loop then
//       only calls accept4, read, write, close, epoll_* — but accept4 itself
//       is still missing.
//   (B) Extend the allowlist by ~4 syscalls: setsockopt(54), bind(49),
//       listen(50), accept4(288).  (Numbers are x86_64; verify on your arch.)
//   (C) Run the SSE server as a separate unsandboxed front process that
//       forwards serialized events to the sandboxed daemon over a
//       pre-connected socket (connect+sendto only, within the 22-list).
//
// To use agui.zig in production, wire serialize + frameSSE into your chosen
// transport layer; do NOT copy this sketch verbatim into a sandboxed path.

pub const ServeExample = struct {
    /// EXAMPLE ONLY. See full SECCOMP / TRANSPORT GAP comment above.
    /// Do NOT call from a seccomp-sandboxed process.
    pub fn serve(queue: *EventQueue(AGUI_Event, 256), port: u16) !void {
        _ = queue;
        _ = port;
        // This is a pure skeleton — the syscall gap is documented above.
        // A real implementation would:
        //   1. socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0)   [✓ in 22-list]
        //   2. setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, ...)     [✗ NOT in 22-list]
        //   3. bind(fd, &addr, sizeof(addr))                     [✗ NOT in 22-list]
        //   4. listen(fd, backlog)                               [✗ NOT in 22-list]
        //   5. Loop: accept4(fd, ...) → for each conn:
        //        sseResponseHeaders(conn_writer)
        //        while (queue.pop()) |event|:
        //          serialize(event, &buf)
        //          frameSSE(buf, conn_writer)
        //        chunked-terminator: "0\r\n\r\n"
        //        close(conn_fd)
        return error.SyscallGapDocumentedAbove;
    }
};

// ═══════════════════════════════════════════════════════════════════════════════
// Compile-time layout checks
// ═══════════════════════════════════════════════════════════════════════════════

comptime {
    // AGUI_Event must be large enough for all variants
    if (MAX_CONTENT < 1) @compileError("MAX_CONTENT must be >= 1");
    if (MAX_CALL_ID < 1) @compileError("MAX_CALL_ID must be >= 1");
    if (MAX_TOOL_NAME < 1) @compileError("MAX_TOOL_NAME must be >= 1");
    if (MAX_DESCRIPTION < 1) @compileError("MAX_DESCRIPTION must be >= 1");
    if (MAX_ARGUMENTS_JSON < 1) @compileError("MAX_ARGUMENTS_JSON must be >= 1");

    // content_len, arguments_len, description_len are u16 — must not overflow
    if (MAX_CONTENT > 65535) @compileError("MAX_CONTENT must fit in u16");
    if (MAX_ARGUMENTS_JSON > 65535) @compileError("MAX_ARGUMENTS_JSON must fit in u16");
    if (MAX_DESCRIPTION > 65535) @compileError("MAX_DESCRIPTION must fit in u16");

    // call_id_len, tool_name_len, request_id_len are u8 — must not overflow
    if (MAX_CALL_ID > 255) @compileError("MAX_CALL_ID must fit in u8");
    if (MAX_TOOL_NAME > 255) @compileError("MAX_TOOL_NAME must fit in u8");
}

// ═══════════════════════════════════════════════════════════════════════════════
// Inline structural tests (no syscalls, no allocation beyond test allocator)
// ═══════════════════════════════════════════════════════════════════════════════

test "AGUI_Event: chunk serializes to exact JSON" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    const content = "Hello, world!";

    var event: AGUI_Event = .{ .chunk = .{
        .choice_index = 0,
        .content_len = @intCast(content.len),
        .content = undefined,
    } };
    @memcpy(event.chunk.content[0..content.len], content);

    try serialize(event, fbs.writer());
    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"Hello, world!\"}}}";
    try std.testing.expectEqualStrings(expected, fbs.getWritten());
}

test "AGUI_Event: tool_call serializes to exact JSON" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    const call_id = "call_001";
    const tool_name = "read_file";
    const args_json = "{\"path\":\"/tmp/test\"}";

    var event: AGUI_Event = .{ .tool_call = .{
        .call_id_len = @intCast(call_id.len),
        .call_id = undefined,
        .tool_name_len = @intCast(tool_name.len),
        .tool_name = undefined,
        .arguments_len = @intCast(args_json.len),
        .arguments_json = undefined,
    } };
    @memcpy(event.tool_call.call_id[0..call_id.len], call_id);
    @memcpy(event.tool_call.tool_name[0..tool_name.len], tool_name);
    @memcpy(event.tool_call.arguments_json[0..args_json.len], args_json);

    try serialize(event, fbs.writer());
    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"call_001\",\"tool_name\":\"read_file\",\"arguments\":{\"path\":\"/tmp/test\"}}}";
    try std.testing.expectEqualStrings(expected, fbs.getWritten());
}

test "AGUI_Event: approval serializes to exact JSON" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);
    const request_id = "req_042";
    const description = "Delete production database?";

    var event: AGUI_Event = .{ .approval = .{
        .request_id_len = @intCast(request_id.len),
        .request_id = undefined,
        .description_len = @intCast(description.len),
        .description = undefined,
    } };
    @memcpy(event.approval.request_id[0..request_id.len], request_id);
    @memcpy(event.approval.description[0..description.len], description);

    try serialize(event, fbs.writer());
    const expected = "{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"req_042\",\"description\":\"Delete production database?\"}}";
    try std.testing.expectEqualStrings(expected, fbs.getWritten());
}

test "writeJsonString: escaping" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    // Input contains: quote, backslash, newline, tab, carriage-return, control char (0x01)
    const input: []const u8 = &[_]u8{ 'a', '"', '\\', '\n', '\r', '\t', 0x01, 'z' };

    try writeJsonString(input, fbs.writer());
    // Expected: a\"\\\n\r\t\u0001z
    try std.testing.expectEqualStrings("a\\\"\\\\\\n\\r\\t\\u0001z", fbs.getWritten());
}

test "frameSSE: hex length equals byte count" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    const json_bytes = "{\"x\":1}";
    try frameSSE(json_bytes, fbs.writer());

    const output = fbs.getWritten();

    // SSE payload length = "data: ".len(6) + json_bytes.len(8) + "\n\n".len(2) = 16 = 0x10
    // First 4 bytes should be "10\r\n"
    try std.testing.expect(output.len >= 4);
    try std.testing.expectEqualStrings("10\r\n", output[0..4]);

    // After chunk header: "data: {\"x\":1}\n\n\r\n"
    const expected_body = "data: {\"x\":1}\n\n\r\n";
    try std.testing.expectEqualStrings(expected_body, output[4..]);
}

test "frameSSE: trailing CRLFs present" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    const json_bytes = "hello";
    try frameSSE(json_bytes, fbs.writer());

    const output = fbs.getWritten();

    // hex length: "data: ".len(6) + 5 + 2 = 13 = 0xd
    // Full output: "d\r\ndata: hello\n\n\r\n"
    // Verify trailing bytes are \r\n
    const last_two = output[output.len - 2 ..];
    try std.testing.expectEqual(@as(u8, '\r'), last_two[0]);
    try std.testing.expectEqual(@as(u8, '\n'), last_two[1]);

    // Verify the SSE terminator \n\n is present before the final \r\n
    const terminator_pos = output.len - 4;
    try std.testing.expectEqual(@as(u8, '\n'), output[terminator_pos]);
    try std.testing.expectEqual(@as(u8, '\n'), output[terminator_pos + 1]);
}

test "frameSSE: empty JSON body" {
    var buf: [128]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    try frameSSE("", fbs.writer());

    const output = fbs.getWritten();
    // SSE payload length = "data: ".len(6) + 0 + "\n\n".len(2) = 8 = 0x8
    // Output: "8\r\ndata: \n\n\r\n"
    const expected = "8\r\ndata: \n\n\r\n";
    try std.testing.expectEqualStrings(expected, output);
}

test "sseResponseHeaders: contains required headers" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    try sseResponseHeaders(fbs.writer());

    const output = fbs.getWritten();
    try std.testing.expect(output.len > 0);

    // Must contain the required header fields
    try std.testing.expect(std.mem.indexOf(u8, output, "HTTP/1.1 200 OK") != null);
    try std.testing.expect(std.mem.indexOf(u8, output, "Content-Type: text/event-stream") != null);
    try std.testing.expect(std.mem.indexOf(u8, output, "Cache-Control: no-cache") != null);
    try std.testing.expect(std.mem.indexOf(u8, output, "Connection: keep-alive") != null);
    try std.testing.expect(std.mem.indexOf(u8, output, "Transfer-Encoding: chunked") != null);

    // Must end with \r\n\r\n (empty line terminating headers)
    const last4 = output[output.len - 4 ..];
    try std.testing.expectEqualStrings("\r\n\r\n", last4);
}
