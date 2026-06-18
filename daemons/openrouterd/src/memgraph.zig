//! memgraph — Codebase Memory Graph client for the AG-UI agent core (Primitive 1).
//!
//! Connects over AF_UNIX to an external `codebase-memory-mcp` server (tree-sitter
//! call-graph, out of scope). This is a CLIENT only: socket(2), connect(2),
//! sendto(2), recvfrom(2), close(2) — all in the wired seccomp 22-list.
//! bind / listen / accept are deliberately absent.
//!
//! ## Framing: NDJSON (newline-delimited JSON)
//!
//! Each request and response is a single, complete JSON object terminated by a
//! single '\n' (0x0a) byte. No length prefix. The wire looks like:
//!
//!   → {"jsonrpc":"2.0","method":"tools/call",...}\n
//!   ← {"jsonrpc":"2.0","result":{...}}\n
//!
//! Why NDJSON over length-prefixed:
//!   1. Human-debuggable with `socat - UNIX-CONNECT:<path>` or strace.
//!   2. Avoids framing attacks on length fields (nonexistent here).
//!   3. Trivial partial-read reassembly: buffer until '\n', then parse.
//!   4. Matches MCP stdio transport convention (JSON-RPC lines).
//!
//! ## Bounds
//!
//! MAX_RESPONSE_BYTES = 1 MiB. Responses exceeding this are rejected with
//! error.ResponseTooLarge before any JSON parsing. The server is expected to
//! keep call-graph responses well under this limit.
//!
//! ## Error set
//!
//!   ConnectFailed      — socket() or connect() returned an error
//!   SendFailed         — sendto() could not write the full request
//!   RecvFailed         — recvfrom() returned a system error
//!   ResponseTooLarge   — accumulated bytes exceeded MAX_RESPONSE_BYTES
//!   ConnectionClosed   — recvfrom() returned 0 (peer closed)
//!
//! ## Limitations
//!
//! - One request → one response per query() call. No pipelining.
//! - The client reconnects for every query() — no persistent connection,
//!   by design: this keeps the agent primitive stateless between calls
//!   and avoids dangling fd state in the sandbox.
//! - JSON is opaque. The caller builds request strings and parses response
//!   strings. This module does NOT hardcode the MCP schema.
//!
//! Zig 0.16, stdlib only, x86_64-linux. No dependencies.

const std = @import("std");

// ── Constants ───────────────────────────────────────────────────────────────

/// Maximum response bytes the client will accept before raising ResponseTooLarge.
pub const MAX_RESPONSE_BYTES: usize = 1_048_576; // 1 MiB

/// Framing delimiter: a single newline terminates every NDJSON message.
pub const FRAME_DELIMITER: u8 = '\n';

/// Receive chunk size for the partial-read loop. Matches a typical page size
/// to avoid excessive syscalls without wasting stack.
const RECV_CHUNK: usize = 4096;

// ── Error set ───────────────────────────────────────────────────────────────

pub const Error = error{
    ConnectFailed,
    SendFailed,
    RecvFailed,
    ResponseTooLarge,
    ConnectionClosed,
};

// ── Client ──────────────────────────────────────────────────────────────────

/// A one-shot AF_UNIX client to the codebase-memory-mcp server.
///
/// Usage:
///   var client = try Client.connect("/run/codebase-memory-mcp.sock");
///   defer client.deinit();
///   const resp = try client.query(allocator, request_json);
pub const Client = struct {
    fd: std.posix.socket_t,

    const Self = @This();

    /// Open an AF_UNIX SOCK_STREAM socket and connect to `path`.
    /// Returns ConnectFailed on any socket() or connect() error.
    pub fn connect(path: []const u8) !Self {
        const fd = std.posix.socket(std.posix.AF.UNIX, std.posix.SOCK.STREAM, 0) catch |e| {
            std.log.err("memgraph: socket(AF_UNIX, SOCK_STREAM) failed: {s}", .{@errorName(e)});
            return error.ConnectFailed;
        };
        errdefer std.posix.close(fd);

        var addr: std.posix.sockaddr.un = undefined;
        addr.family = std.posix.AF.UNIX;

        // Copy the path into sun_path. POSIX requires null termination
        // for pathname sockets (not abstract).
        if (path.len >= addr.path.len) {
            std.log.err("memgraph: socket path too long ({d} bytes, max {d})", .{ path.len, addr.path.len - 1 });
            std.posix.close(fd);
            return error.ConnectFailed;
        }
        @memcpy(addr.path[0..path.len], path);
        addr.path[path.len] = 0; // null-terminate

        // Address length = family field + path bytes + null terminator.
        const addr_len: std.posix.socklen_t = @intCast(@offsetOf(std.posix.sockaddr.un, "path") + path.len + 1);

        std.posix.connect(fd, @ptrCast(&addr), addr_len) catch |e| {
            std.log.err("memgraph: connect({s}) failed: {s}", .{ path, @errorName(e) });
            std.posix.close(fd);
            return error.ConnectFailed;
        };

        std.log.debug("memgraph: connected to {s} (fd {d})", .{ path, fd });
        return Self{ .fd = fd };
    }

    /// Close the underlying socket. Safe to call multiple times.
    pub fn deinit(self: *Self) void {
        if (self.fd >= 0) {
            std.posix.close(self.fd);
            self.fd = -1;
        }
    }

    /// Send `request_json` (opaque JSON string) and return the response as an
    /// owned byte slice allocated with `allocator`. The caller must free the
    /// returned slice.
    ///
    /// This is a one-shot: the client reconnects on every call.
    pub fn query(self: Self, allocator: std.mem.Allocator, request_json: []const u8) (Error || std.mem.Allocator.Error)![]u8 {
        // 1. Frame and send
        try sendFrame(self.fd, request_json);

        // 2. Receive framed response
        return recvFrame(allocator, self.fd);
    }
};

// ── Generic framing (testable, reader/writer-based) ───────────────────────

/// Write `data` followed by FRAME_DELIMITER to a `std.io.Writer`.
/// This is the generic, testable version used by `memgraph_test.zig`
/// with `std.io.fixedBufferStream`.
pub fn sendFrameWriter(writer: anytype, data: []const u8) !void {
    try writer.writeAll(data);
    try writer.writeByte(FRAME_DELIMITER);
}

/// Read from a `std.io.Reader` until FRAME_DELIMITER, then return the line
/// (without the delimiter) as an owned slice. Enforces MAX_RESPONSE_BYTES.
///
/// The reader must return `error.EndOfStream` on EOF. Short reads within the
/// stream are handled automatically by the reader's `read` method (the generic
/// `read` contract returns 0..buffer.len bytes; a `FixedBufferStream` reader
/// returns all available bytes at once).
pub fn recvFrameReader(allocator: std.mem.Allocator, reader: anytype) ![]u8 {
    var buf = try std.ArrayListUnmanaged(u8).initCapacity(allocator, RECV_CHUNK);
    defer buf.deinit(allocator);

    while (true) {
        // Ensure we have room for at least one more chunk.
        if (buf.capacity - buf.items.len < RECV_CHUNK) {
            const grow_to = @min(buf.capacity * 2, MAX_RESPONSE_BYTES);
            if (grow_to <= buf.capacity) {
                return error.ResponseTooLarge;
            }
            try buf.ensureTotalCapacity(allocator, grow_to);
        }

        const spare = buf.unusedCapacitySlice();
        const chunk = spare[0..@min(spare.len, RECV_CHUNK)];
        const n = reader.read(chunk) catch |e| switch (e) {
            error.EndOfStream => {
                if (buf.items.len == 0) return error.ConnectionClosed;
                return error.ConnectionClosed;
            },
            else => return error.RecvFailed,
        };

        if (n == 0) {
            if (buf.items.len == 0) return error.ConnectionClosed;
            return error.ConnectionClosed;
        }

        buf.items.len += n;

        if (buf.items.len > MAX_RESPONSE_BYTES) {
            return error.ResponseTooLarge;
        }

        if (std.mem.indexOfScalar(u8, buf.items, FRAME_DELIMITER)) |delim_idx| {
            const frame = try allocator.dupe(u8, buf.items[0..delim_idx]);
            return frame;
        }
    }
}

// ── Socket framing (private, used by Client) ────────────────────────────────

/// Write `data` followed by FRAME_DELIMITER to fd via sendto(2).
fn sendFrame(fd: std.posix.socket_t, data: []const u8) Error!void {
    var sent: usize = 0;
    while (sent < data.len) {
        const n = std.posix.sendto(fd, data[sent..], 0, null, 0) catch |e| {
            std.log.err("memgraph: sendto failed: {s}", .{@errorName(e)});
            return error.SendFailed;
        };
        if (n == 0) return error.ConnectionClosed;
        sent += n;
    }

    const delim = [_]u8{FRAME_DELIMITER};
    const nd = std.posix.sendto(fd, &delim, 0, null, 0) catch |e| {
        std.log.err("memgraph: sendto (delim) failed: {s}", .{@errorName(e)});
        return error.SendFailed;
    };
    if (nd != 1) return error.SendFailed;

    std.log.debug("memgraph: sent {d} bytes + newline", .{data.len});
}

/// Read from fd via recvfrom(2) until FRAME_DELIMITER.
fn recvFrame(allocator: std.mem.Allocator, fd: std.posix.socket_t) (Error || std.mem.Allocator.Error)![]u8 {
    var buf = try std.ArrayListUnmanaged(u8).initCapacity(allocator, RECV_CHUNK);
    defer buf.deinit(allocator);

    while (true) {
        if (buf.capacity - buf.items.len < RECV_CHUNK) {
            const grow_to = @min(buf.capacity * 2, MAX_RESPONSE_BYTES);
            if (grow_to <= buf.capacity) {
                return error.ResponseTooLarge;
            }
            try buf.ensureTotalCapacity(allocator, grow_to);
        }

        const spare = buf.unusedCapacitySlice();
        const n = std.posix.recvfrom(
            fd,
            spare[0..@min(spare.len, RECV_CHUNK)],
            0,
            null,
            null,
        ) catch |e| {
            std.log.err("memgraph: recvfrom failed: {s}", .{@errorName(e)});
            return error.RecvFailed;
        };

        if (n == 0) {
            if (buf.items.len == 0) return error.ConnectionClosed;
            return error.ConnectionClosed;
        }

        buf.items.len += n;

        if (buf.items.len > MAX_RESPONSE_BYTES) {
            return error.ResponseTooLarge;
        }

        if (std.mem.indexOfScalar(u8, buf.items, FRAME_DELIMITER)) |delim_idx| {
            const frame = try allocator.dupe(u8, buf.items[0..delim_idx]);
            return frame;
        }
    }
}

// ── Typed query helpers ─────────────────────────────────────────────────────

/// Typed query builders for common codebase-memory operations.
///
/// Each function returns an owned JSON string (allocated with `allocator`)
/// that can be passed directly to `Client.query()`. The JSON conforms to
/// JSON-RPC 2.0 with MCP's `tools/call` method. The caller owns the returned
/// string and must free it.
///
/// Example:
///   const req = try Query.callersOf(allocator, "seccomp.zig:apply");
///   defer allocator.free(req);
///   const resp = try client.query(allocator, req);
///   defer allocator.free(resp);
pub const Query = struct {
    /// Build a JSON-RPC request to call the `callersOf` tool on `symbol`.
    ///
    /// The `symbol` should be a fully-qualified name as understood by the
    /// codebase-memory-mcp server, e.g. "seccomp.zig:apply" or "src/main.zig:main".
    /// The returned JSON is a complete, single-line NDJSON frame (no trailing
    /// newline — the Client adds that).
    pub fn callersOf(allocator: std.mem.Allocator, symbol: []const u8) ![]u8 {
        // Build a JSON-RPC 2.0 tools/call request.
        // The arguments are passed as a JSON object inside `params.arguments`.
        //
        // Template:
        //   {"jsonrpc":"2.0","id":1,"method":"tools/call",
        //    "params":{"name":"callersOf","arguments":{"symbol":"<symbol>"}}}
        //
        // We use counted string building for exact sizing (one allocation).

        // Pre-calculate the exact size needed.
        // "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"\"}}}"
        const prefix = "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"callersOf\",\"arguments\":{\"symbol\":\"";
        const suffix = "\"}}}";

        // We need to escape `symbol` for JSON. Since symbol names in codebases
        // are typically ASCII identifiers with ':', '.', '/', '-', '_', we do a
        // minimal escape pass. For full generality, a JSON encoder would be
        // needed — but this is a demo helper; callers with exotic symbols can
        // build the JSON themselves.

        // Count the escaped length.
        var escaped_len: usize = 0;
        for (symbol) |c| {
            escaped_len += switch (c) {
                '"', '\\' => 2,
                '\n' => 2,
                '\r' => 2,
                '\t' => 2,
                else => 1,
            };
        }

        const total_len = prefix.len + escaped_len + suffix.len;
        const result = try allocator.alloc(u8, total_len);
        errdefer allocator.free(result);

        var pos: usize = 0;
        @memcpy(result[pos..][0..prefix.len], prefix);
        pos += prefix.len;

        for (symbol) |c| {
            switch (c) {
                '"' => {
                    result[pos] = '\\';
                    result[pos + 1] = '"';
                    pos += 2;
                },
                '\\' => {
                    result[pos] = '\\';
                    result[pos + 1] = '\\';
                    pos += 2;
                },
                '\n' => {
                    result[pos] = '\\';
                    result[pos + 1] = 'n';
                    pos += 2;
                },
                '\r' => {
                    result[pos] = '\\';
                    result[pos + 1] = 'r';
                    pos += 2;
                },
                '\t' => {
                    result[pos] = '\\';
                    result[pos + 1] = 't';
                    pos += 2;
                },
                else => {
                    result[pos] = c;
                    pos += 1;
                },
            }
        }

        @memcpy(result[pos..][0..suffix.len], suffix);
        // pos + suffix.len == total_len

        return result;
    }
};

// ── Tests (socket-based; see memgraph_test.zig for in-memory tests) ─────────

test "sendFrame: appends newline to data" {
    const pair = try std.posix.socketpair(std.posix.AF.UNIX, std.posix.SOCK.STREAM, 0);
    defer std.posix.close(pair[0]);
    defer std.posix.close(pair[1]);

    const msg = "{\"jsonrpc\":\"2.0\"}";
    try sendFrame(pair[0], msg);

    var buf: [256]u8 = undefined;
    const n = try std.posix.recvfrom(pair[1], &buf, 0, null, null);
    try std.testing.expectEqual(msg.len + 1, n);
    try std.testing.expectEqualStrings(msg, buf[0..msg.len]);
    try std.testing.expectEqual(FRAME_DELIMITER, buf[msg.len]);
}

test "recvFrame: socket roundtrip" {
    const pair = try std.posix.socketpair(std.posix.AF.UNIX, std.posix.SOCK.STREAM, 0);
    defer std.posix.close(pair[0]);
    defer std.posix.close(pair[1]);

    const msg = "{\"result\":\"ok\"}";
    const framed = try std.fmt.allocPrint(std.testing.allocator, "{s}\n", .{msg});
    defer std.testing.allocator.free(framed);

    _ = try std.posix.sendto(pair[0], framed, 0, null, 0);

    const result = try recvFrame(std.testing.allocator, pair[1]);
    defer std.testing.allocator.free(result);
    try std.testing.expectEqualStrings(msg, result);
}
