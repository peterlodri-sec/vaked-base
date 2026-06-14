const std = @import("std");
const builtin = @import("builtin");

pub const TpmError = error{
    TpmNotAvailable,
    SealFailed,
    UnsealFailed,
    KeyGenFailed,
};

/// A 32-byte signing key, zeroed on deinit.
pub const SealedKey = struct {
    bytes: [32]u8 = [_]u8{0} ** 32,
    active: bool = false,

    pub fn deinit(self: *SealedKey) void {
        // Zero key material before free (prevents key leakage in heap dumps)
        std.crypto.secureZero(u8, &self.bytes);
        self.active = false;
    }

    pub fn isActive(self: *const SealedKey) bool {
        return self.active;
    }
};

/// Unseal or generate the signing key.
///
/// NixOS: tpm2-tss via tpm2_createprimary + tpm2_create, key sealed to PCR values.
/// macOS: Security.framework SecKeyCreateRandomKey + Secure Enclave (kSecAttrTokenIDSecureEnclave).
/// Fallback (no TPM/SEP): std.crypto.random ephemeral key + console warning.
pub fn unsealKey() TpmError!SealedKey {
    if (builtin.os.tag == .linux) {
        return unsealKeyLinux();
    } else if (builtin.os.tag == .macos) {
        return unsealKeyMacos();
    } else {
        return unsealKeyEphemeral();
    }
}

fn unsealKeyLinux() TpmError!SealedKey {
    // TODO(phase6-real): call tpm2_createprimary + tpm2_unseal via libtss2-esys
    // For now: ephemeral fallback with warning (TPM2 tools not always available in dev)
    std.log.warn("gocc TPM: tpm2-tss not wired (stub) — using ephemeral key", .{});
    return unsealKeyEphemeral();
}

fn unsealKeyMacos() TpmError!SealedKey {
    // TODO(phase6-real): SecKeyCreateRandomKey(kSecAttrTokenIDSecureEnclave) via Security.framework
    std.log.warn("gocc TPM: Secure Enclave not wired (stub) — using ephemeral key", .{});
    return unsealKeyEphemeral();
}

fn unsealKeyEphemeral() TpmError!SealedKey {
    var key: SealedKey = .{ .active = true };
    // Zig 0.16: std.crypto.random removed; use OS primitives directly (same pattern as hook.zig).
    if (builtin.os.tag == .linux) {
        _ = std.os.linux.getrandom(&key.bytes, key.bytes.len, 0);
    } else {
        // macOS / other POSIX: arc4random_buf is always available
        std.c.arc4random_buf(&key.bytes, key.bytes.len);
    }
    return key;
}

// ---- Tests ------------------------------------------------------------------

test "unsealKey returns active key" {
    const key = try unsealKey();
    try std.testing.expect(key.active);
}

test "SealedKey.deinit zeroes bytes" {
    var key: SealedKey = .{ .active = true };
    // Fill with non-zero data first
    @memset(&key.bytes, 0xAB);
    key.deinit();
    const expected = [_]u8{0} ** 32;
    try std.testing.expectEqualSlices(u8, &expected, &key.bytes);
    try std.testing.expect(!key.active);
}

test "ephemeral key bytes are non-zero after generation" {
    const key = try unsealKey();
    // XOR all bytes: p(all zero from random) = 1/2^256 — safe for a scaffold test
    var acc: u8 = 0;
    for (key.bytes) |b| acc |= b;
    try std.testing.expect(acc != 0);
}
