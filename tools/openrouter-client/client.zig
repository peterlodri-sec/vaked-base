const std = @import("std");
pub const OpenRouterBridge = struct {
    endpoint: []const u8 = "https://openrouter.ai/api/v1/chat/completions",
    auth_token_nickname: []const u8,
    pub fn streamCompletions(self: OpenRouterBridge, a: std.mem.Allocator, ctx: []const u8) !void {
        var client = std.http.Client{ .allocator = a };
        defer client.deinit();
        const uri = try std.Uri.parse(self.endpoint);
        var hb: [4096]u8 = undefined;
        var req = try client.open(.POST, uri, .{ .server_header_buffer = &hb });
        defer req.deinit();
        try req.headers.append("Authorization", "Bearer OPENROUTER_AUTH_NICKNAME");
        try req.headers.append("Content-Type", "application/json");
        var pb: [8192]u8 = undefined;
        const body = try std.fmt.bufPrint(&pb, "{{\"model\":\"deepseek/deepseek-chat\",\"messages\":[{{\"role\":\"user\",\"content\":\"{s}\"}}]}}", .{ctx});
        req.transfer_encoding = .{ .content_length = body.len };
        try req.send();
        try req.writeAll(body);
        try req.finish();
        try req.wait();
    }
};
test "init" { const b = OpenRouterBridge{ .auth_token_nickname = "t" }; _ = b; }
