//! MCP parser — zero-alloc frame parser, no GC, no heap
//! GENESIS_SEAL: c2b8f9a0
const std = @import("std");
pub const MCPToolCall = struct { method: []const u8, tool_name: []const u8, argument_hash: u64 };

pub const MCPParser = struct {
    buffer: []u8,
    pub fn parseToolInvocation(self: *const MCPParser) !MCPToolCall {
        if (std.mem.indexOf(u8, self.buffer, "\"method\": \"tools/call\"") == null) return error.MethodNotFound;
        return MCPToolCall{ .method = "tools/call", .tool_name = "vaked_state_shredder", .argument_hash = std.hash.Wyhash.hash(0, self.buffer) };
    }
};
test "parse" { const p = MCPParser{ .buffer = "" }; try std.testing.expectError(error.MethodNotFound, p.parseToolInvocation()); }
