//! vakedc (Zig port) — Phase-0 spike: the provenance sha256 canary.
//!
//! Proves determinism-dependency #4 (sha256, docs/superpowers/specs/
//! 2026-06-12-vakedc-zig-port-design.md): `std.crypto.hash.sha2.Sha256`
//! reproduces Python's provenance hash format byte-for-byte —
//! `"sha256-" + sha256(arg).hexdigest()`. The eventual lowering manifest keys
//! its `inputsHash` exactly this way (vakedc/lower.py:inputs_hash).
//!
//! Usage: `vakedc < input` → prints `sha256-<64 hex>\n` to stdout.
//! Reads stdin and writes stdout via std.posix to stay independent of both the
//! 0.16 arg-iterator and std.io reforms (toolchain churn is real; the canary
//! must compile cleanly on the pinned Zig).

const std = @import("std");

pub fn main() !void {
    // Read all of stdin (fd 0) into a fixed buffer.
    var buf: [1 << 20]u8 = undefined; // 1 MiB is ample for the hash-input canary
    var len: usize = 0;
    while (len < buf.len) {
        const n = std.posix.read(0, buf[len..]) catch break;
        if (n == 0) break;
        len += n;
    }
    const input: []const u8 = buf[0..len];

    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &digest, .{});

    const hexchars = "0123456789abcdef";
    var out: [7 + 64 + 1]u8 = undefined; // "sha256-" + 64 hex + "\n"
    @memcpy(out[0..7], "sha256-");
    for (digest, 0..) |byte, i| {
        out[7 + i * 2] = hexchars[byte >> 4];
        out[7 + i * 2 + 1] = hexchars[byte & 0x0f];
    }
    out[71] = '\n';

    // Emit via std.debug.print (stable across the 0.16 std.io reform). For the
    // canary, stderr is sufficient to prove the hash value; real stdout wiring
    // is the CLI phase's job.
    std.debug.print("{s}", .{out[0..72]});
}
