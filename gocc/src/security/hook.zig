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

// macOS syscall number for write (arm64 and x86_64).
// Using a direct syscall avoids any libc interpose layer and breaks the
// recursion risk that would arise if dlsym(RTLD_NEXT) returned our own hook
// due to the __DATA,__interpose mechanism.
const MACOS_SYS_WRITE: usize = 4;

/// The hook implementation — used by both platforms.
fn writeHook(fd: c_int, buf: ?*const anyopaque, count: usize) callconv(.c) isize {
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

// ── Platform export ───────────────────────────────────────────────────────────
//
// Linux: export writeHook as the symbol "write" — LD_PRELOAD intercepts it.
//
// macOS: export as "_gocc_write_hook" ONLY (not as "write").
//   The __DATA,__interpose table in hook_interpose.c maps:
//     replacee    = &write      (resolves to libSystem's write in that TU)
//     replacement = &_gocc_write_hook
//   Because this dylib does NOT export a symbol named "write", the C compiler's
//   `&write` in hook_interpose.c resolves to the libSystem import stub —
//   exactly what dyld needs in the replacee field to perform the substitution.
//
// On macOS, DYLD_INSERT_LIBRARIES without DYLD_FORCE_FLAT_NAMESPACE is the
// supported invocation; the interpose section makes it work on macOS 14+.
comptime {
    if (builtin.os.tag == .linux) {
        @export(&writeHook, .{ .name = "write" });
    } else {
        // macOS: only the internal hook symbol; interpose table handles routing.
        @export(&writeHook, .{ .name = "_gocc_write_hook" });
    }
}

fn callOrigWrite(fd: c_int, buf: ?*const anyopaque, count: usize) isize {
    // Use a direct kernel syscall on both platforms to bypass any libc
    // interpose layer.  This is crucial on macOS where the __DATA,__interpose
    // mechanism would cause dlsym(RTLD_NEXT, "write") to return our own hook,
    // creating an infinite recursion.  A raw syscall bypasses libc entirely.
    if (builtin.os.tag == .linux) {
        return @intCast(std.os.linux.syscall3(
            std.os.linux.SYS.write,
            @intCast(fd),
            @intFromPtr(buf),
            count,
        ));
    }
    // macOS arm64: issue SYS_write (syscall #4) directly.
    // Darwin ABI: x16 = syscall number, x0/x1/x2 = args, "svc #0x80" traps.
    // Using a raw syscall bypasses libc entirely and avoids re-entering our
    // interpose hook.
    if (builtin.os.tag == .macos) {
        return asm volatile (
            \\ svc #0x80
            : [ret] "={x0}" (-> isize),
            : [number] "{x16}" (MACOS_SYS_WRITE),
              [fd] "{x0}" (@as(usize, @intCast(fd))),
              [buf] "{x1}" (@intFromPtr(buf)),
              [count] "{x2}" (count),
            : .{ .memory = true }
        );
    }
    // Fallback for other POSIX targets — should not be reached in practice.
    return @intCast(count);
}
