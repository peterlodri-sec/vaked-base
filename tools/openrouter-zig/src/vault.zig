const std = @import("std");
extern "c" fn getenv([*:0]const u8) ?[*:0]const u8;
const BASE = "https://bao.crabcc.app/v1";
const DEFAULT_TOKEN_ENV = "VAULT_TOKEN";
pub const VaultError = error{
    Unauthorized,
    NotFound,
    HttpError,
    ParseError,
    SecretNotFound,
};
pub const VaultHealth = struct {
    initialized: bool,
    sealed: bool,
    standby: bool,
    version: []const u8,
    cluster_name: []const u8,
};
pub const Vault = struct {
    allocator: std.mem.Allocator,
    io: std.Io,
    token: []const u8,
    base_url: []const u8,
    pub fn init(allocator: std.mem.Allocator, io: std.Io) !Vault {
        const token = if (getenv(DEFAULT_TOKEN_ENV)) |t|
            try allocator.dupe(u8, std.mem.span(t))
        else if (getenv("BAO_TOKEN")) |t|
            try allocator.dupe(u8, std.mem.span(t))
        else
            return VaultError.Unauthorized;
        return Vault{ .allocator = allocator, .io = io, .token = token, .base_url = BASE };
    }
    pub fn deinit(self: *Vault) void {
        self.allocator.free(self.token);
    }
    pub fn health(self: *Vault) !VaultHealth {
        const url = try std.fmt.allocPrint(self.allocator, "{s}/sys/health", .{self.base_url});
        defer self.allocator.free(url);
        return self._get(VaultHealth, url);
    }
    pub fn getSecret(self: *Vault, path: []const u8) ![]const u8 {
        const url = try std.fmt.allocPrint(self.allocator, "{s}/secret/data/{s}", .{ self.base_url, path });
        defer self.allocator.free(url);
        const parsed = try self._get(struct { data: struct { data: struct { value: ?[]const u8 } } }, url);
        if (parsed.data.data.value) |v| return self.allocator.dupe(u8, v);
        return VaultError.SecretNotFound;
    }
    pub fn resolveSecret(self: *Vault, vault_path: []const u8, env_var: []const u8) ![]const u8 {
        if (self.getSecret(vault_path)) |val| {
            std.log.info("secret {s} from vault", .{vault_path});
            return val;
        } else |_| {}
        if (getenv(env_var.ptr)) |val| {
            std.log.info("secret {s} from env", .{vault_path});
            return self.allocator.dupe(u8, std.mem.span(val));
        }
        std.log.err("secret {s} not found (vault + {s})", .{ vault_path, env_var });
        return VaultError.SecretNotFound;
    }
    fn _get(self: *Vault, comptime T: type, url: []const u8) !T {
        var client: std.http.Client = .{ .allocator = self.allocator, .io = self.io };
        defer client.deinit();
        var resp: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
        defer resp.deinit(self.allocator);
        var w = std.Io.Writer.fromArrayList(&resp);
        const uri = try std.Uri.parse(url);
        var h: [2]std.http.Header = undefined;
        h[0] = .{ .name = "X-Vault-Token", .value = self.token };
        h[1] = .{ .name = "User-Agent", .value = "vaked-vault-zig/0.1" };
        _ = client.fetch(.{ .location = .{ .uri = uri }, .method = .GET, .response_writer = &w, .extra_headers = &h }) catch return VaultError.HttpError;
        const parsed = std.json.parseFromSlice(T, self.allocator, resp.items, .{ .ignore_unknown_fields = true }) catch return VaultError.ParseError;
        return parsed.value;
    }
};
test "vault init without token" {
    const testing = std.testing;
    if (getenv("VAULT_TOKEN")) |_| return error.SkipZigTest; // skip if token set
    try testing.expectError(VaultError.Unauthorized, Vault.init(testing.allocator, undefined));
}