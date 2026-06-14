const std = @import("std");
const builtin = @import("builtin");
const vault_mod = @import("vault.zig");

// Transient per-process signing key (32 bytes, zeroed until initHook fills them)
var g_signing_key: [32]u8 = .{0} ** 32;
var g_initialized: bool = false;

/// Called once on first write() interception.
fn initHook() void {
    if (g_initialized) return;
    g_initialized = true;
    // Generate transient signing key with CSPRNG.
    // Zig 0.16 moved random out of std.crypto; use OS primitives directly.
    if (builtin.os.tag == .linux) {
        _ = std.os.linux.getrandom(&g_signing_key, g_signing_key.len, 0);
    } else {
        // macOS / other POSIX: arc4random_buf is always available
        std.c.arc4random_buf(&g_signing_key, g_signing_key.len);
    }
}

/// Helper: cross-platform getpid (std.posix.getpid removed in 0.16).
fn getPid() u32 {
    if (builtin.os.tag == .linux) {
        return @intCast(std.os.linux.getpid());
    } else {
        return @intCast(std.c.getpid());
    }
}

/// Replacement write() — intercepts all writes, scrubs detected secrets.
export fn write(fd: c_int, buf: ?*const anyopaque, count: usize) callconv(.c) isize {
    if (!g_initialized) initHook();

    if (buf == null or count == 0) return callOrigWrite(fd, buf, count);

    const bytes = @as([*]const u8, @ptrCast(buf.?))[0..count];

    // Scan for secrets only in small writes to avoid large stack allocs.
    if (count <= 4096) {
        if (vault_mod.findSecret(bytes)) |match| {
            var scrubbed: [4096]u8 = undefined;
            @memcpy(scrubbed[0..count], bytes);

            const secret = bytes[match.start .. match.start + match.len];
            const pid: u32 = getPid();
            const hash = vault_mod.polHash(&g_signing_key, pid, secret);

            // Format: "GOCC-SCRUBBED::{24-char-hex}" — 40 bytes total.
            // bytesToHex requires a comptime-length array; hash is [12]u8 so this works.
            const hex_hash = std.fmt.bytesToHex(hash, .lower);
            var replacement: [40]u8 = undefined;
            const rep_slice = std.fmt.bufPrint(&replacement, "GOCC-SCRUBBED::{s}", .{hex_hash}) catch replacement[0..0];
            const rep_len = rep_slice.len; // actual chars written

            // Copy the marker over the secret region.
            const replace_len = @min(rep_len, match.len);
            @memcpy(scrubbed[match.start .. match.start + replace_len], rep_slice[0..replace_len]);

            // If the marker is shorter than the secret, zero-pad the remainder
            // to avoid leaking trailing secret bytes in the output.
            if (match.len > rep_len) {
                @memset(scrubbed[match.start + rep_len .. match.start + match.len], 0);
            }

            return callOrigWrite(fd, &scrubbed, count);
        }
    }

    return callOrigWrite(fd, buf, count);
}

fn callOrigWrite(fd: c_int, buf: ?*const anyopaque, count: usize) isize {
    // Use a direct syscall on Linux to bypass ourselves (avoids infinite recursion).
    if (builtin.os.tag == .linux) {
        return @intCast(std.os.linux.syscall3(
            std.os.linux.SYS.write,
            @intCast(fd),
            @intFromPtr(buf),
            count,
        ));
    }
    // macOS: the real write() lives in libSystem; no recursion risk with a
    // dylib preload. Return count to signal success — Phase 5 wires dlsym(RTLD_NEXT).
    _ = .{ fd, buf };
    return @intCast(count);
}
