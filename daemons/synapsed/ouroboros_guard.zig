//! Ouroboros guard — verify live patch integrity, zero-alloc, no disk
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const RuntimeDeltas = struct {
    pub fn verifyLivePatchInPlace(code_base: []const u8, signature_token: u64) bool {
        if (code_base.len < 8) return false;
        return std.mem.readInt(u64, code_base[0..8], .little) == signature_token;
    }
};

test "signature matches" {
    var buf = [8]u8{ 0x7C, 0x24, 0x20, 0x80, 0x00, 0x00, 0x00, 0x00 };
    try std.testing.expect(RuntimeDeltas.verifyLivePatchInPlace(&buf, 0x8020247C));
}

test "short buffer rejected" {
    try std.testing.expect(!RuntimeDeltas.verifyLivePatchInPlace(&[_]u8{0}, 0));
}

test "mismatch detected" {
    try std.testing.expect(!RuntimeDeltas.verifyLivePatchInPlace(&[_]u8{0xFF} ** 8, 0x8020247C));
}
