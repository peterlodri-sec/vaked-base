const std = @import("std");
const models = @import("models.zig");
const DEFAULT_BUDGET: f64 = 6.00;
extern "c" fn getenv([*:0]const u8) ?[*:0]const u8;
fn budgetPath(allocator: std.mem.Allocator) ![]const u8 {
    const home = if (getenv("HOME")) |h| std.mem.span(h) else ".";
    return std.fs.path.join(allocator, &.{ home, ".orcli_budget" });
}
pub fn readBudget(io: std.Io, allocator: std.mem.Allocator) !models.BudgetState {
    const path = try budgetPath(allocator);
    defer allocator.free(path);
    const content = std.Io.Dir.cwd().readFileAlloc(io, path, allocator, @enumFromInt(1024)) catch {
        return models.BudgetState{ .remaining = DEFAULT_BUDGET, .cap = DEFAULT_BUDGET };
    };
    defer allocator.free(content);
    const value = std.fmt.parseFloat(f64, std.mem.trim(u8, content, " \n\r")) catch DEFAULT_BUDGET;
    return models.BudgetState{ .remaining = value, .cap = DEFAULT_BUDGET };
}
pub fn writeBudget(io: std.Io, allocator: std.mem.Allocator, remaining: f64) !void {
    const path = try budgetPath(allocator);
    defer allocator.free(path);
    const buf = try std.fmt.allocPrint(allocator, "{d:.4}", .{remaining});
    defer allocator.free(buf);
    const file = try std.Io.Dir.createFileAbsolute(io, path, .{});
    defer file.close(io);
    try file.writePositionalAll(io, buf, 0);
}
pub fn trackCost(
    io: std.Io,
    allocator: std.mem.Allocator,
    prompt_tokens: u32,
    completion_tokens: u32,
    prompt_cost_per_m: f64,
    completion_cost_per_m: f64,
) !models.BudgetState {
    const cost = (@as(f64, @floatFromInt(prompt_tokens)) * prompt_cost_per_m +
        @as(f64, @floatFromInt(completion_tokens)) * completion_cost_per_m) / 1_000_000.0;
    const current = try readBudget(io, allocator);
    const remaining = current.remaining - cost;
    try writeBudget(io, allocator, remaining);
    return models.BudgetState{ .remaining = remaining, .cap = current.cap };
}
pub fn formatBudget(allocator: std.mem.Allocator, state: models.BudgetState) ![]const u8 {
    return std.fmt.allocPrint(allocator, "${d:.4} remaining · cap ${d:.2}", .{ state.remaining, state.cap });
}