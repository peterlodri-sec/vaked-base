// ZetaTensor: 128-byte wire frame for gocc inter-node messaging.
// Fields ordered u64-first to eliminate internal padding in extern struct.

const std = @import("std");
const builtin = @import("builtin");

pub const OpCode = enum(u8) {
    annotation = 0x01, // @(...)
    pipeline   = 0x02, // >
    capability = 0x03, // &
    prompt     = 0x04, // ?
    gate       = 0x05, // security gate event
};

pub const PayloadFormat = enum(u8) {
    hash   = 0x00,
    string = 0x01,
    tensor = 0x02,
};

// ASCII magic "GOCC" written at the start of every log file.
pub const FILE_MAGIC: [4]u8 = .{ 'G', 'O', 'C', 'C' };

pub const ZetaTensor = extern struct {
    timestamp_ns: u64,      // 0-7
    kv_cache_ptr: u64,      // 8-15
    source_node_id: u32,    // 16-19
    dest_node_id: u32,      // 20-23
    ppid: u32,              // 24-27
    proc_sign_prefix: u32,  // 28-31
    target_layer: u32,      // 32-35
    attention_head: u32,    // 36-39
    matrix_stride: u32,     // 40-43
    structural_flags: u32,  // 44-47
    payload_len: u16,       // 48-49
    op_code: u8,            // 50
    payload_format: u8,     // 51
    state_hash: [12]u8,     // 52-63
    tensor_data: [64]u8,    // 64-127

    /// Reinterpret the frame as a 128-byte slice (native byte order on x86/ARM).
    pub fn toBytes(self: *const ZetaTensor) *const [128]u8 {
        return @ptrCast(self);
    }

    /// Reinterpret a 128-byte slice as a ZetaTensor frame.
    /// Caller must ensure the pointer is at least 8-byte aligned (natural alignment of ZetaTensor).
    /// Tip: declare the source buffer as `align(8)` or use a ZetaTensor variable directly.
    pub fn fromBytes(bytes: *const [128]u8) *const ZetaTensor {
        return @ptrCast(@alignCast(bytes));
    }
};

// Wire invariant: exactly 128 bytes.
// 64-byte cache-line alignment is a variable-level concern (e.g. `var f: ZetaTensor align(64) = ...`).
comptime {
    std.debug.assert(@sizeOf(ZetaTensor) == 128);
}

/// Create a minimal frame for a pipeline event.
/// `io` is used to read the realtime clock. `ppid` is populated via std.posix.getppid().
pub fn init(io: std.Io, op: OpCode, src: u32, dst: u32) ZetaTensor {
    var f: ZetaTensor = std.mem.zeroes(ZetaTensor);
    f.op_code = @intFromEnum(op);
    f.source_node_id = src;
    f.dest_node_id = dst;
    // Io.Timestamp.nanoseconds is i96; truncate to u64 (wraps ~year 2554, acceptable for a log field).
    const ts = std.Io.Timestamp.now(io, .real);
    f.timestamp_ns = @truncate(@as(u128, @bitCast(@as(i128, ts.nanoseconds))));
    f.ppid = @intCast(std.posix.getppid());
    return f;
}
