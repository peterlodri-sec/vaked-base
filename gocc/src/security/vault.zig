const std = @import("std");

// Secret regex patterns (ASCII byte scanning — no regex engine needed)
pub const SecretPattern = struct {
    prefix: []const u8,
    min_len: usize,
};

pub const PATTERNS = [_]SecretPattern{
    .{ .prefix = "ghp_", .min_len = 40 }, // GitHub PAT
    .{ .prefix = "sk-", .min_len = 20 }, // OpenAI key
    .{ .prefix = "AKIA", .min_len = 20 }, // AWS access key
    .{ .prefix = "xoxb-", .min_len = 20 }, // Slack bot token
    .{ .prefix = "xoxp-", .min_len = 20 }, // Slack user token
    .{ .prefix = "glpat-", .min_len = 20 }, // GitLab PAT
};

/// Scan buf for known secret patterns. Returns index of first match or null.
pub fn findSecret(buf: []const u8) ?struct { start: usize, len: usize } {
    for (PATTERNS) |pat| {
        var i: usize = 0;
        // Use <= so a prefix at exactly buf.len - prefix.len is checked.
        while (i + pat.prefix.len <= buf.len) : (i += 1) {
            if (std.mem.startsWith(u8, buf[i..], pat.prefix)) {
                // Find end of secret (alphanumeric + allowed chars)
                var end = i + pat.prefix.len;
                while (end < buf.len and isSecretChar(buf[end])) end += 1;
                if (end - i >= pat.min_len) {
                    return .{ .start = i, .len = end - i };
                }
            }
        }
    }
    return null;
}

fn isSecretChar(c: u8) bool {
    return std.ascii.isAlphanumeric(c) or c == '_' or c == '-' or c == '.';
}

/// Compute a 12-byte PoL hash: SHA256(key_bytes || pid_bytes || secret_bytes)[0..12]
pub fn polHash(key: []const u8, pid: u32, secret: []const u8) [12]u8 {
    var h = std.crypto.hash.sha2.Sha256.init(.{});
    h.update(key);
    h.update(std.mem.asBytes(&pid));
    h.update(secret);
    var digest: [32]u8 = undefined;
    h.final(&digest);
    return digest[0..12].*;
}

/// In-memory vault mapping 12-byte hash -> sealed secret bytes.
/// Uses a simple array list (real impl would use sodium_malloc locked pages).
pub const Vault = struct {
    alloc: std.mem.Allocator,
    entries: std.ArrayListUnmanaged(VaultEntry),

    pub const VaultEntry = struct {
        hash: [12]u8,
        secret: []u8, // heap-allocated copy
    };

    pub fn init(alloc: std.mem.Allocator) Vault {
        return .{ .alloc = alloc, .entries = .empty };
    }

    pub fn deinit(self: *Vault) void {
        for (self.entries.items) |e| self.alloc.free(e.secret);
        self.entries.deinit(self.alloc);
    }

    pub fn store(self: *Vault, hash: [12]u8, secret: []const u8) !void {
        const copy = try self.alloc.dupe(u8, secret);
        try self.entries.append(self.alloc, .{ .hash = hash, .secret = copy });
    }

    pub fn lookup(self: *const Vault, hash: [12]u8) ?[]const u8 {
        for (self.entries.items) |e| {
            if (std.mem.eql(u8, &e.hash, &hash)) return e.secret;
        }
        return null;
    }
};

// ---- Tests ---------------------------------------------------------------

test "findSecret detects ghp_ pattern" {
    const buf = "Authorization: Bearer ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
    const match = findSecret(buf);
    try std.testing.expect(match != null);
    // "ghp_" starts at index 22 in the string above
    try std.testing.expectEqual(@as(usize, 22), match.?.start);
    // total length = "ghp_" (4) + 40 x's = 44, which is >= min_len 40
    try std.testing.expect(match.?.len >= 40);
}

test "findSecret returns null for clean input" {
    const buf = "Hello world";
    try std.testing.expect(findSecret(buf) == null);
}

test "polHash deterministic" {
    const key = "test-signing-key";
    const pid: u32 = 12345;
    const secret = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
    const h1 = polHash(key, pid, secret);
    const h2 = polHash(key, pid, secret);
    try std.testing.expectEqualSlices(u8, &h1, &h2);
}

test "Vault store/lookup roundtrip" {
    var vault = Vault.init(std.testing.allocator);
    defer vault.deinit();

    const secret = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
    const hash = polHash("key", 1, secret);
    try vault.store(hash, secret);

    const found = vault.lookup(hash);
    try std.testing.expect(found != null);
    try std.testing.expectEqualSlices(u8, secret, found.?);
}

test "Vault lookup miss" {
    var vault = Vault.init(std.testing.allocator);
    defer vault.deinit();

    const secret = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
    const hash = polHash("key", 1, secret);
    try vault.store(hash, secret);

    // Wrong hash — all zeros
    const wrong_hash = [_]u8{0} ** 12;
    try std.testing.expect(vault.lookup(wrong_hash) == null);
}

test "npm exploit scenario: findSecret detects TOKEN= env var with ghp_ value" {
    const buf = "TOKEN=ghp_abc123abcdefghijklmnopqrstuvwxyz1234";
    const match = findSecret(buf);
    try std.testing.expect(match != null);
    // ghp_ starts at index 6 ("TOKEN=")
    try std.testing.expectEqual(@as(usize, 6), match.?.start);
    // The secret value "ghp_abc123abcdefghijklmnopqrstuvwxyz1234" has 40 chars
    try std.testing.expect(match.?.len >= 40);
}
