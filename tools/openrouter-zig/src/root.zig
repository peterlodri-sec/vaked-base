//! VakedAgent — 1:1 with @vaked/openrouter-ts/src/index.ts
const std = @import("std");
const models = @import("models.zig");
const http = @import("http.zig");
const budget = @import("budget.zig");
const context7 = @import("context7.zig");
extern "c" fn getenv([*:0]const u8) ?[*:0]const u8;

pub const VakedAgent = struct {
    allocator: std.mem.Allocator,
    io: std.Io,
    api_key: []const u8,
    config: models.VakedAgentConfig,
    arena: std.heap.ArenaAllocator,

    pub fn init(allocator: std.mem.Allocator, io: std.Io, config: models.VakedAgentConfig) !VakedAgent {
        const key = config.api_key orelse blk: {
            const env_key = if (getenv("OPENROUTER_API_KEY")) |k|
                std.mem.span(k)
            else {
                std.debug.print("OPENROUTER_API_KEY not set\n", .{});
                return error.NoApiKey;
            };
            break :blk try allocator.dupe(u8, env_key);
        };

        return VakedAgent{ .io = io,
            .allocator = allocator,
            .api_key = key,
            .config = config,
            .arena = std.heap.ArenaAllocator.init(allocator),
        };
    }

    pub fn deinit(self: *VakedAgent) void {
        self.arena.deinit();
        if (self.config.api_key == null) self.allocator.free(self.api_key);
    }

    pub fn ask(self: *VakedAgent, prompt: []const u8) ![]const u8 {
        return self.askWithModel(prompt, self.config.default_model, 500);
    }

    pub fn askWithModel(self: *VakedAgent, prompt: []const u8, model_id: []const u8, max_tokens: u32) ![]const u8 {
        const resp = try http.makeApiCall(self.io, self.allocator, self.api_key, model_id, "You are a helpful assistant.", prompt, max_tokens, false);
        if (resp.choices.len == 0) return error.EmptyResponse;
        const content = resp.choices[0].message.content orelse "";
        if (resp.usage) |usage| {
            if (models.resolveModel(model_id)) |entry| {
                _ = budget.trackCost(self.io, self.allocator, usage.prompt_tokens, usage.completion_tokens, entry.prompt_cost, entry.completion_cost) catch {};
            }
        }
        return self.arena.allocator().dupe(u8, content);
    }

    pub fn code(self: *VakedAgent, prompt: []const u8) ![]const u8 {
        const resp = try http.makeApiCall(self.io, self.allocator, self.api_key, "anthropic/claude-opus-4-8-fast", "Zig 0.16 systems programmer. Write production code. No explanations, only code.", prompt, 2000, false);
        if (resp.choices.len == 0) return error.EmptyResponse;
        const content = resp.choices[0].message.content orelse "";
        return self.arena.allocator().dupe(u8, content);
    }

    pub fn review(self: *VakedAgent, prompt: []const u8) ![]const u8 {
        const resp = try http.makeApiCall(self.io, self.allocator, self.api_key, "anthropic/claude-opus-4-8-fast", "Critical reviewer. 3-5 specific suggestions. Be direct.", prompt, 600, false);
        if (resp.choices.len == 0) return error.EmptyResponse;
        const content = resp.choices[0].message.content orelse "";
        return self.arena.allocator().dupe(u8, content);
    }
};

test "resolve model" {
    const m = models.resolveModel("deepseek");
    try std.testing.expect(m != null);
    try std.testing.expectEqualStrings("deepseek/deepseek-v4-pro", m.?.id);
}

test "model count" {
    try std.testing.expectEqual(@as(usize, 7), models.MODELS.len);
}
