const std = @import("std");
const models = @import("models.zig");
extern "c" fn getenv([*:0]const u8) ?[*:0]const u8;
pub const Context7Error = error{ HttpError, ParseError, EmptyResponse, Unauthorized, NotFound };
fn getApiKey() ![]const u8 {
    if (getenv("CONTEXT7_API_KEY")) |key| return std.mem.span(key);
    return Context7Error.Unauthorized;
}
fn fetchJson(io: std.Io,comptime T: type, allocator: std.mem.Allocator, url: []const u8, api_key: []const u8) !T {
    var client: std.http.Client = .{ .allocator = allocator, .io = io };
    defer client.deinit();
    var body: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    defer body.deinit(allocator);
    var body_writer = std.Io.Writer.fromArrayList(&body);
    const auth = try std.fmt.allocPrint(allocator, "Bearer {s}", .{api_key});
    defer allocator.free(auth);
    const uri = try std.Uri.parse(url);
    var headers: [2]std.http.Header = undefined;
    headers[0] = .{ .name = "Authorization", .value = auth };
    headers[1] = .{ .name = "User-Agent", .value = "vaked-openrouter-zig/0.1" };
    _ = client.fetch(.{
        .location = .{ .uri = uri },
        .method = .GET,
        .response_writer = &body_writer,
        .extra_headers = &headers,
    }) catch return Context7Error.HttpError;
    if (body.items.len == 0) return Context7Error.EmptyResponse;
    return std.json.parseFromSlice(T, allocator, body.items, .{ .ignore_unknown_fields = true }) catch
        return Context7Error.ParseError;
}
pub fn searchLibrary(io: std.Io,allocator: std.mem.Allocator, library_name: []const u8, query: []const u8) !models.SearchResponse {
    const api_key = try getApiKey();
        const endpoint = if (getenv("CONTEXT7_ENDPOINT")) |ep| std.mem.span(ep) else "https://context7.com/api/v2";
    const url = try std.fmt.allocPrint(allocator, "{s}/libs/search?libraryName={s}&query={s}", .{ endpoint, library_name, query });
    defer allocator.free(url);
    return fetchJson(io, models.SearchResponse, allocator, url, api_key);
}
pub fn getContext(io: std.Io,allocator: std.mem.Allocator, library_id: []const u8, query: []const u8) !models.ContextResponse {
    const api_key = try getApiKey();
        const endpoint = if (getenv("CONTEXT7_ENDPOINT")) |ep| std.mem.span(ep) else "https://context7.com/api/v2";
    const url = try std.fmt.allocPrint(allocator, "{s}/context?libraryId={s}&query={s}&type=json", .{ endpoint, library_id, query });
    defer allocator.free(url);
    return fetchJson(io, models.ContextResponse, allocator, url, api_key);
}
pub fn resolveLibraryId(io: std.Io,allocator: std.mem.Allocator, name: []const u8) !?models.Library {
    const r = searchLibrary(io, allocator, name, "documentation") catch return null;
    if (r.results.len == 0) return null;
    return r.results[0];
}
pub fn queryDocs(io: std.Io,allocator: std.mem.Allocator, name: []const u8, query: []const u8) !models.ContextResponse {
    const lib = try resolveLibraryId(allocator, name) orelse return Context7Error.NotFound;
    return getContext(io, allocator, lib.id, query);
}