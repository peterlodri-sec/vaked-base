// ZetaTensor: 128-byte, 64-byte aligned wire frame for gocc inter-node messaging.
// Fields ordered u64-first to eliminate internal padding in extern struct.
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
} align(64);

comptime {
    const std = @import("std");
    std.debug.assert(@sizeOf(ZetaTensor) == 128);
    std.debug.assert(@alignOf(ZetaTensor) == 64);
}
