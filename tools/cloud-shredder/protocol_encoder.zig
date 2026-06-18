const std = @import("std");
const tables = @import("../../daemons/synapsed/viewport_tables.zig");
pub const ProtocolEncoder = struct {
    pub fn encodeMeshState(view_table: *const tables.MeshViewportTable, out: []u8) !usize {
        const raw = std.mem.asBytes(view_table);
        if (out.len < raw.len) return error.BufferOverflow;
        @memcpy(out[0..raw.len], raw);
        return raw.len;
    }
};
test "encode" { var t = tables.MeshViewportTable.init(); var buf: [4096]u8 = undefined; _ = try ProtocolEncoder.encodeMeshState(&t, &buf); }
