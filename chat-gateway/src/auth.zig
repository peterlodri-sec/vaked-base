const std = @import("std");
const HmacSha256 = std.crypto.auth.hmac.sha2.HmacSha256;
/// Genesis Hash (hex string, raw bytes to be authenticated)
const GENESIS_HASH_HEX = "7c242080f5f821e5eaf563fe2208d60632c451687baf65f4fe8e4a0d226e3ecf";
/// Decode a hex character to its nibble value.
fn hexNibble(c: u8) ?u8 {
    return switch (c) {
        '0'...'9' => c - '0',
        'a'...'f' => c - 'a' + 10,
        'A'...'F' => c - 'A' + 10,
        else => null,
    };
}
/// Decode hex string into out buffer. Returns number of bytes written, or null on bad input.
fn hexDecode(out: []u8, hex: []const u8) ?usize {
    if (hex.len % 2 != 0) return null;
    const n = hex.len / 2;
    if (out.len < n) return null;
    var i: usize = 0;
    while (i < n) : (i += 1) {
        const hi = hexNibble(hex[i * 2]) orelse return null;
        const lo = hexNibble(hex[i * 2 + 1]) orelse return null;
        out[i] = (hi << 4) | lo;
    }
    return n;
}
/// Compute HMAC-SHA256 over the genesis hash bytes, keyed by `salt`.
/// Writes the 32-byte MAC into `out`.
fn computeToken(out: *[HmacSha256.mac_length]u8, salt: []const u8) void {
    var msg: [32]u8 = undefined;
    const n = hexDecode(&msg, GENESIS_HASH_HEX) orelse unreachable;
    HmacSha256.create(out, msg[0..n], salt);
}
/// Constant-time comparison of two equal-length byte slices.
fn constEql(a: []const u8, b: []const u8) bool {
    if (a.len != b.len) return false;
    var diff: u8 = 0;
    for (a, b) |x, y| diff |= x ^ y;
    return diff == 0;
}
/// Verify a hex-encoded token string against the HMAC of the genesis hash
/// salted with `salt` (the value of GENESIS_SALT, supplied by caller).
/// Returns true if the token is valid.
pub fn verify(token: []const u8, salt: []const u8) bool {
    var expected: [HmacSha256.mac_length]u8 = undefined;
    computeToken(&expected, salt);
    // Decode provided token from hex.
    var provided: [HmacSha256.mac_length]u8 = undefined;
    const n = hexDecode(&provided, token) orelse return false;
    if (n != HmacSha256.mac_length) return false;
    return constEql(&provided, &expected);
}
/// Convenience: produce the canonical hex token for a given salt.
pub fn generate(out: *[HmacSha256.mac_length * 2]u8, salt: []const u8) void {
    var mac: [HmacSha256.mac_length]u8 = undefined;
    computeToken(&mac, salt);
    const hex_chars = "0123456789abcdef";
    for (mac, 0..) |b, i| {
        out[i * 2] = hex_chars[b >> 4];
        out[i * 2 + 1] = hex_chars[b & 0x0f];
    }
}
// In your main:
// const salt = lookupEnv(init.minimal.env, "GENESIS_SALT") orelse "";
// const ok = auth.verify(user_token, salt);
pub fn main() !void {}
