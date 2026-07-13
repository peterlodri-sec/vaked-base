//! shell_test.zig — standalone tests for shell.zig (Primitive 3)
//!
//! This file exercises the PURE-LOGIC paths of shell.zig:
//!   - argv validation
//!   - output-cap truncation logic (via pipe read, no spawn)
//!   - timeout-config plumbing
//!   - result struct lifecycle
//!
//! Run with:  zig test shell_test.zig --deps shell=../shell.zig ?
//! Or (standard): zig test src/shell_test.zig (if shell.zig is in the same dir,
//! just @import it — Zig resolves relative to the test root).
//!
//! SPAWN-DEPENDENT PATHS ARE NOT TESTED HERE.
//! See the UNTESTED PATHS section at the bottom of shell.zig for the inventory.
//!
//! Zig 0.16 · stdlib only · zero deps.

const std = @import("std");
const shell = @import("shell.zig");

// ── argv validation ─────────────────────────────────────────────────────────

test "validateArgv: empty argv slice" {
    try std.testing.expectError(error.EmptyArgv, shell.validateArgv(&[_][]const u8{}));
}

test "validateArgv: single empty string" {
    try std.testing.expectError(error.EmptyArg, shell.validateArgv(&[_][]const u8{""}));
}

test "validateArgv: valid single arg" {
    try shell.validateArgv(&[_][]const u8{"ls"});
}

test "validateArgv: valid multi arg" {
    try shell.validateArgv(&[_][]const u8{ "echo", "-n", "hello world" });
}

test "validateArgv: trailing empty string rejected" {
    try std.testing.expectError(error.EmptyArg, shell.validateArgv(&[_][]const u8{ "cat", "-", "" }));
}

test "validateArgv: leading empty string rejected" {
    try std.testing.expectError(error.EmptyArg, shell.validateArgv(&[_][]const u8{ "", "cat" }));
}

// ── RunOpts plumbing ────────────────────────────────────────────────────────

test "RunOpts: all defaults are zero/null" {
    const opts = shell.RunOpts{};
    try std.testing.expectEqual(@as(?[]const u8, null), opts.cwd);
    try std.testing.expectEqual(@as(u64, 0), opts.timeout_ms);
    try std.testing.expectEqual(@as(usize, 0), opts.max_output_bytes);
}

test "RunOpts: explicit fields" {
    const opts = shell.RunOpts{
        .cwd = "/tmp",
        .timeout_ms = 5000,
        .max_output_bytes = 65536,
    };
    try std.testing.expectEqualStrings("/tmp", opts.cwd.?);
    try std.testing.expectEqual(@as(u64, 5000), opts.timeout_ms);
    try std.testing.expectEqual(@as(usize, 65536), opts.max_output_bytes);
}

test "RunOpts: cwd set to null explicitly" {
    const opts = shell.RunOpts{ .cwd = null, .timeout_ms = 100, .max_output_bytes = 1 };
    try std.testing.expectEqual(@as(?[]const u8, null), opts.cwd);
}

// ── RunResult struct ────────────────────────────────────────────────────────

test "RunResult: field assignment and deinit" {
    const a = std.testing.allocator;
    const out = try a.dupe(u8, "stdout-data");
    const err = try a.dupe(u8, "stderr-data");

    const rr = shell.RunResult{
        .exit_code = 0,
        .stdout = out,
        .stderr = err,
        .timed_out = false,
    };
    defer rr.deinit(a);

    try std.testing.expectEqual(@as(i32, 0), rr.exit_code);
    try std.testing.expectEqualStrings("stdout-data", rr.stdout);
    try std.testing.expectEqualStrings("stderr-data", rr.stderr);
    try std.testing.expectEqual(false, rr.timed_out);
}

test "RunResult: exit_code negative on signal" {
    const a = std.testing.allocator;
    const out = try a.dupe(u8, "");
    const err = try a.dupe(u8, "");
    defer {
        a.free(out);
        a.free(err);
    }

    const rr = shell.RunResult{
        .exit_code = -9, // SIGKILL
        .stdout = out,
        .stderr = err,
        .timed_out = true,
    };
    try std.testing.expectEqual(@as(i32, -9), rr.exit_code);
    try std.testing.expectEqual(true, rr.timed_out);
}

test "RunResult: deinit frees both buffers" {
    const a = std.testing.allocator;
    const out = try a.dupe(u8, "a" ** 100);
    const err = try a.dupe(u8, "b" ** 200);

    var rr = shell.RunResult{
        .exit_code = 1,
        .stdout = out,
        .stderr = err,
        .timed_out = false,
    };
    rr.deinit(a);

    // After deinit, the struct fields still hold the original values
    // (exit_code and timed_out are copies, not heap pointers).
    try std.testing.expectEqual(@as(i32, 1), rr.exit_code);
    try std.testing.expectEqual(false, rr.timed_out);
}

// ── readWithCap (pipe-based, no spawn) ──────────────────────────────────────

test "readWithCap: data under cap — no truncation" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    _ = try std.posix.write(pipe_fds[1], "abc123");
    std.posix.close(pipe_fds[1]); // EOF

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 1024);
    defer a.free(result);

    try std.testing.expectEqualStrings("abc123", result);
}

test "readWithCap: data exactly at cap — truncation marker" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    _ = try std.posix.write(pipe_fds[1], "ABCDE");
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 5);
    defer a.free(result);

    try std.testing.expect(std.mem.startsWith(u8, result, "ABCDE"));
    try std.testing.expect(std.mem.endsWith(u8, result, "[TRUNCATED]"));
}

test "readWithCap: data over cap — truncated + marker" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    const payload = "x" ** 200;
    _ = try std.posix.write(pipe_fds[1], &payload);
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 30);
    defer a.free(result);

    // Should be ≤ 30 + len("\n[TRUNCATED]") bytes.
    try std.testing.expect(result.len <= 30 + "\n[TRUNCATED]".len);
    try std.testing.expect(std.mem.endsWith(u8, result, "[TRUNCATED]"));
    // First 30 chars should all be 'x'.
    const body = result[0 .. result.len - "\n[TRUNCATED]".len];
    for (body) |b| try std.testing.expectEqual(@as(u8, 'x'), b);
}

test "readWithCap: cap=0 means unbounded read" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    _ = try std.posix.write(pipe_fds[1], "no-cap-bounds");
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 0);
    defer a.free(result);

    try std.testing.expectEqualStrings("no-cap-bounds", result);
}

test "readWithCap: empty pipe returns empty slice" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    std.posix.close(pipe_fds[1]); // immediate EOF

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 4096);
    defer a.free(result);

    try std.testing.expectEqualStrings("", result);
}

test "readWithCap: zero cap with empty pipe" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 0);
    defer a.free(result);

    try std.testing.expectEqualStrings("", result);
}

test "readWithCap: large read under large cap" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    // Write >4KB to exercise the read loop across multiple pipe reads.
    const payload = "y" ** 5000;
    _ = try std.posix.write(pipe_fds[1], &payload);
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 10000);
    defer a.free(result);

    try std.testing.expectEqual(@as(usize, 5000), result.len);
    for (result) |b| try std.testing.expectEqual(@as(u8, 'y'), b);
}

test "readWithCap: cap smaller than single read chunk" {
    const a = std.testing.allocator;
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    // Write more than the internal 4096-byte buffer can hold in one read.
    const payload = "z" ** 6000;
    _ = try std.posix.write(pipe_fds[1], &payload);
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try shell.readWithCap(a, read_end, 100);
    defer a.free(result);

    try std.testing.expect(result.len <= 100 + "\n[TRUNCATED]".len);
    try std.testing.expect(std.mem.endsWith(u8, result, "[TRUNCATED]"));
}

// ─────────────────────────────────────────────────────────────────────────────
// UNTESTED PATHS — require real process spawn (forbidden in this workspace)
//
//  1. Shell.run() with a real argv
//     → spawns via fork/clone + execve. Cannot execute; CLAUDE.md forbids
//       builds/execution on the developer machine.
//
//  2. Timeout logic (opts.timeout_ms > 0 with a sleeping child)
//     → requires a child that sleeps past the deadline so the kill() path
//       fires. The poll loop, deadline check, kill, and re-wait are all
//       exercised only with a real child.
//
//  3. cwd option
//     → requires a real child whose working directory can be observed
//       (e.g. `pwd` or `ls` in a known directory).
//
//  4. Concurrent runs
//     → two Shell.run() calls with different argv should not interfere.
//       Requires real spawns running in parallel.
//
//  5. Signal exit codes
//     → exit_code negated from Signal/Stopped term. Only observable
//       with a real child killed by signal (SIGKILL, SIGTERM, etc.).
//
//  6. Large-output stress (e.g. 100MB stdout)
//     → exercises the cap truncation under extreme conditions; requires
//       a real child producing controlled large output.
//
// These paths will be tested in the openrouterd integration test suite
// (daemon-level tests authorised to spawn processes).
// ─────────────────────────────────────────────────────────────────────────────
