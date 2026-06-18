const std = @import("std");
const models = @import("models.zig");
pub const ApiError = error{ HttpError, ParseError, ApiReturnedError, NoApiKey };
pub fn makeApiCall(io: std.Io,
    allocator: std.mem.Allocator,
    api_key: []const u8,
    model: []const u8,
    system_prompt: ?[]const u8,
    user_prompt: []const u8,
    max_tokens: u32,
    stream: bool,
) !models.ResponsePayload {
    var messages: std.ArrayListUnmanaged(models.Message) = .{ .items = &.{}, .capacity = 0 };
    defer messages.deinit(allocator);
    if (system_prompt) |sys| {
        try messages.append(allocator, .{ .role = "system", .content = sys });
    }
    try messages.append(allocator, .{ .role = "user", .content = user_prompt });
    const payload = models.RequestPayload{
        .model = model, .messages = messages.items,
        .max_tokens = max_tokens, .stream = stream,
    };
    // Zig 0.16: use std.json.fmt + allocPrint for JSON serialization
    const json_str = try std.fmt.allocPrint(allocator, "{}", .{std.json.fmt(payload, .{})});
    defer allocator.free(json_str);
    const auth = try std.fmt.allocPrint(allocator, "Bearer {s}", .{api_key});
    defer allocator.free(auth);
    var client: std.http.Client = .{ .allocator = allocator, .io = io };
    defer client.deinit();
    var response_body: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    defer response_body.deinit(allocator);
    var response_writer = std.Io.Writer.fromArrayList(&response_body);
    const uri = try std.Uri.parse("https://openrouter.ai/api/v1/chat/completions");
    var header_buf: [4]std.http.Header = undefined;
    header_buf[0] = .{ .name = "Content-Type", .value = "application/json" };
    header_buf[1] = .{ .name = "Authorization", .value = auth };
    header_buf[2] = .{ .name = "HTTP-Referer", .value = "https://github.com/peterlodri-sec/vaked-base" };
    header_buf[3] = .{ .name = "X-Title", .value = "vaked-openrouter-zig" };
    _ = client.fetch(.{
        .location = .{ .uri = uri },
        .method = .POST,
        .payload = json_str,
        .response_writer = &response_writer,
        .extra_headers = &header_buf,
    }) catch return ApiError.HttpError;
    const parsed = std.json.parseFromSlice(models.ResponsePayload, allocator, response_body.items, .{ .ignore_unknown_fields = true }) catch {
        if (std.json.parseFromSlice(models.ErrorPayload, allocator, response_body.items, .{ .ignore_unknown_fields = true })) |err_parsed| {
            defer err_parsed.deinit();
            if (err_parsed.value.@"error".message) |msg| {
                std.debug.print("[http] API error: {s}\n", .{msg});
            }
            return ApiError.ApiReturnedError;
        } else |_| return ApiError.ParseError;
    };
    return parsed.value;
}