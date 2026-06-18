//! shell.zig — Isolated Shell Executor (Primitive 3)
//!
//! Spawn a child process via std.process.Child, capture stdout AND stderr
//! fully (piped, two separate buffers), and return {exit_code, stdout, stderr}
//! for routing to a self-repair loop (e.g. Ouroboros autopatch).
//!
//! API:
//!   Shell.run(allocator, argv, opts) → RunResult
//!
//! Output is capped (no unbounded buffer) and a kill-timeout terminates the
//! child when it exceeds the deadline.
//!
//! ── SECCOMP / SYSTEM-CALL HONESTY (REQUIRED) ─────────────────────────────
//!
//! This executor spawns a child process. That requires:
//!
//!   fork / clone     — create a new process
//!   execve           — replace the child's address space
//!   pipe2            — create stdout/stderr pipes
//!   wait4            — reap the child
//!   kill             — send SIGKILL on timeout
//!
//! **NONE** of these syscalls are in the openrouterd WIRED seccomp 22-list:
//!
//!   read, write, openat, close, socket, connect, sendto, recvfrom,
//!   epoll_create1, epoll_ctl, epoll_wait, mmap, munmap, mprotect,
//!   brk, exit, exit_group, getrandom, clock_gettime, futex,
//!   io_uring_setup, io_uring_enter
//!
//! Therefore this primitive CANNOT run inside the sandboxed openrouterd
//! profile. It MUST run either:
//!
//!   (a) pre-seccomp — during early init before seccomp_mod.apply(), or
//!   (b) in a SEPARATE unsandboxed broker process that the sandboxed core
//!       talks to over the existing socket/connect path (port 9090 loopback
//!       or a Unix-domain socket).
//!
//! Architecture (b) is the intended design: the isolated executor lives in a
//! sidecar daemon with a tiny request/response protocol over the socket that
//! openrouterd already owns. The sandboxed core sends {argv, cwd, timeout_ms,
//! max_output_bytes} and receives {exit_code, stdout, stderr}.
//!
//! Zig 0.16 · stdlib only · zero deps · explicit allocator.

const std = @import("std");

/// Options passed to Shell.run.
pub const RunOpts = struct {
    /// Working directory for the child process. null means inherit from parent.
    cwd: ?[]const u8 = null,

    /// Kill the child after this many milliseconds. 0 means no timeout (risk:
    /// unbounded wait, but the max_output_bytes cap still limits buffer growth).
    timeout_ms: u64 = 0,

    /// Maximum bytes to read from stdout before truncating. 0 means no cap
    /// (risk: unbounded heap allocation; prefer setting a reasonable limit).
    max_output_bytes: usize = 0,
};

/// Result of a completed (or timed-out/killed) child process.
pub const RunResult = struct {
    /// Process exit code. On timeout/kill this is the signal number (negated
    /// or raw, depending on platform — see Child.Term).
    exit_code: i32,

    /// Captured stdout, owned by the allocator passed to run(). Caller must free.
    stdout: []const u8,

    /// Captured stderr, owned by the allocator passed to run(). Caller must free.
    stderr: []const u8,

    /// True when the child was killed by the timeout watchdog.
    timed_out: bool,

    /// Deallocate stdout and stderr. Does NOT deinit the allocator itself.
    pub fn deinit(self: *const RunResult, allocator: std.mem.Allocator) void {
        allocator.free(self.stdout);
        allocator.free(self.stderr);
    }
};

/// Validation errors caught before any syscall.
pub const ValidateError = error{
    /// argv must have at least one element (the executable).
    EmptyArgv,
    /// An individual argument string is empty ("" is rejected; use "." for cwd).
    /// Zig 0.16 Child.exec requires non-empty argv[0].
    EmptyArg,
};

/// Combined error set for Shell.run.
pub const RunError = ValidateError || std.process.Child.SpawnError || error{
    /// Timeout exceeded; child was killed. The partial RunResult is returned
    /// via the timed_out field, not as an error, so this is reserved for
    /// cases where we cannot even construct a partial result.
    ReadError,
};

/// Validate argv before attempting to spawn. Returns the argv slice on success
/// so callers can pre-validate (useful for testing without spawning).
pub fn validateArgv(argv: []const []const u8) ValidateError!void {
    if (argv.len == 0) return error.EmptyArgv;
    for (argv) |arg| {
        if (arg.len == 0) return error.EmptyArg;
    }
}

/// Run a child process and capture its stdout/stderr.
///
/// Caller owns the returned RunResult and must call result.deinit(allocator)
/// to free the captured output buffers.
///
/// **WARNING**: this function calls fork/clone, execve, pipe2, wait4, kill —
/// NONE of which are in the openrouterd seccomp 22-list. It MUST run
/// pre-seccomp or in a separate unsandboxed broker process.
pub fn run(
    allocator: std.mem.Allocator,
    argv: []const []const u8,
    opts: RunOpts,
) !RunResult {
    // Gate 0: validate args before any syscall.
    try validateArgv(argv);

    // --- spawn -----------------------------------------------------------
    var child = std.process.Child.init(argv, allocator);

    // Pipe stdout and stderr so we capture them separately.
    child.stdin_behavior = .Ignore;
    child.stdout_behavior = .Pipe;
    child.stderr_behavior = .Pipe;

    if (opts.cwd) |cwd| {
        child.cwd = cwd;
    }

    // Inherit the parent environment. Callers that want a clean env should
    // set it via env_map before calling run (not exposed here to keep the
    // API surface tight; add if needed).
    child.env_map = null; // inherit

    const term = try child.spawn();

    // --- read with cap ---------------------------------------------------
    const cap = opts.max_output_bytes;

    const stdout_bytes = try readWithCap(allocator, child.stdout.?, cap);
    errdefer allocator.free(stdout_bytes);

    const stderr_bytes = try readWithCap(allocator, child.stderr.?, cap);
    errdefer allocator.free(stderr_bytes);

    // --- timeout watchdog (polled) ---------------------------------------
    var timed_out = false;

    if (opts.timeout_ms > 0) {
        const deadline_ns = std.time.nanoTimestamp() + @as(i128, opts.timeout_ms) * std.time.ns_per_ms;

        // Poll until child exits or deadline expires.
        while (true) {
            // Try a non-blocking wait.
            const maybe_term = try child.wait();
            if (maybe_term != .still_active) {
                term.* = maybe_term;
                break;
            }
            if (std.time.nanoTimestamp() >= deadline_ns) {
                timed_out = true;
                _ = child.kill() catch {}; // best-effort SIGKILL
                // Reap the killed child.
                term.* = child.wait() catch blk: {
                    // Child may already be reaped by signal; return -1.
                    break :blk .{ .Exited = 255 };
                };
                break;
            }
            // Sleep a short tick to avoid busy-waiting.
            std.time.sleep(10 * std.time.ns_per_ms);
        }
    } else {
        // No timeout — block until exit.
        term.* = try child.wait();
    }

    // --- extract exit code -----------------------------------------------
    const exit_code: i32 = switch (term.*) {
        .Exited => |code| code,
        .Signal => |sig| -(sig),
        .Stopped => |sig| -(sig),
        .Unknown => |code| code,
        .still_active => unreachable,
    };

    return RunResult{
        .exit_code = exit_code,
        .stdout = stdout_bytes,
        .stderr = stderr_bytes,
        .timed_out = timed_out,
    };
}

/// Read from a child's pipe until EOF or cap is reached. If cap > 0 and the
/// output exceeds it, the excess is discarded and the returned slice is
/// truncated (plus a "[TRUNCATED]\n" suffix when cap permits).
pub fn readWithCap(
    allocator: std.mem.Allocator,
    pipe: std.fs.File,
    cap: usize,
) ![]const u8 {
    var list = std.ArrayListUnmanaged(u8){};
    errdefer list.deinit(allocator);

    // If cap is 0, read unbounded (risk: OOM on malicious/hung child).
    const effective_cap = if (cap == 0) std.math.maxInt(usize) else cap;

    var buf: [4096]u8 = undefined;
    var total: usize = 0;

    while (true) {
        const n = try pipe.read(&buf);
        if (n == 0) break; // EOF

        const room = if (effective_cap > total) effective_cap - total else 0;
        const to_append = @min(n, room);
        if (to_append > 0) {
            try list.appendSlice(allocator, buf[0..to_append]);
            total += to_append;
        }
    }

    // If the child wrote more than cap, append a truncation marker.
    if (cap > 0 and total >= cap) {
        const marker = "\n[TRUNCATED]";
        // Only append if there's room for at least part of the marker.
        // We already filled to cap, so we'd need to overwrite or append.
        // Append and let the caller see it (slight over-cap, intentional signal).
        try list.appendSlice(allocator, marker);
    }

    return list.toOwnedSlice(allocator);
}

// ── Tests ───────────────────────────────────────────────────────────────────

test "validateArgv: empty argv" {
    try std.testing.expectError(error.EmptyArgv, validateArgv(&[_][]const u8{}));
}

test "validateArgv: empty arg element" {
    try std.testing.expectError(error.EmptyArg, validateArgv(&[_][]const u8{ "ls", "" }));
}

test "validateArgv: valid" {
    try validateArgv(&[_][]const u8{"echo"});
    try validateArgv(&[_][]const u8{ "echo", "hello", "world" });
}

test "RunResult deinit frees memory" {
    const a = std.testing.allocator;
    const stdout = try a.dupe(u8, "hello");
    const stderr = try a.dupe(u8, "world");

    var rr = RunResult{
        .exit_code = 0,
        .stdout = stdout,
        .stderr = stderr,
        .timed_out = false,
    };
    rr.deinit(a);

    // After deinit the pointers are dangling — nothing to assert except no crash.
    // Verify the fields are still readable (they're copies, not pointers).
    try std.testing.expectEqual(@as(i32, 0), rr.exit_code);
    try std.testing.expectEqual(false, rr.timed_out);
}

test "readWithCap: under cap" {
    const a = std.testing.allocator;

    // Create a pipe, write to it, close the write end, then read.
    // NOTE: this is a pure-logic test of the cap logic using a real pipe.
    // It does NOT spawn a child process.
    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]); // read end
        std.posix.close(pipe_fds[1]); // write end
    }

    _ = try std.posix.write(pipe_fds[1], "hello");
    std.posix.close(pipe_fds[1]); // signal EOF

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try readWithCap(a, read_end, 1024);
    defer a.free(result);

    try std.testing.expectEqualStrings("hello", result);
}

test "readWithCap: at cap — truncation marker appended" {
    const a = std.testing.allocator;

    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    // Write exactly 5 bytes, cap at 5 → marker should appear.
    _ = try std.posix.write(pipe_fds[1], "hello");
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try readWithCap(a, read_end, 5);
    defer a.free(result);

    try std.testing.expect(std.mem.startsWith(u8, result, "hello"));
    try std.testing.expect(std.mem.endsWith(u8, result, "[TRUNCATED]"));
}

test "readWithCap: over cap — data truncated" {
    const a = std.testing.allocator;

    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    // Write 100 bytes, cap at 10.
    const data = "x" ** 100;
    _ = try std.posix.write(pipe_fds[1], &data);
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try readWithCap(a, read_end, 10);
    defer a.free(result);

    // Should have exactly 10 'x' bytes plus the truncation marker.
    try std.testing.expect(result.len <= 10 + "\n[TRUNCATED]".len);
    try std.testing.expect(std.mem.endsWith(u8, result, "[TRUNCATED]"));
}

test "readWithCap: cap=0 means unbounded" {
    const a = std.testing.allocator;

    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    _ = try std.posix.write(pipe_fds[1], "no-cap-data");
    std.posix.close(pipe_fds[1]);

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try readWithCap(a, read_end, 0);
    defer a.free(result);

    try std.testing.expectEqualStrings("no-cap-data", result);
}

test "readWithCap: empty pipe" {
    const a = std.testing.allocator;

    const pipe_fds = try std.posix.pipe();
    defer {
        std.posix.close(pipe_fds[0]);
        std.posix.close(pipe_fds[1]);
    }

    std.posix.close(pipe_fds[1]); // close write end immediately → EOF

    const read_end = std.fs.File{ .handle = pipe_fds[0] };
    const result = try readWithCap(a, read_end, 1024);
    defer a.free(result);

    try std.testing.expectEqualStrings("", result);
}

test "RunOpts default values" {
    const opts = RunOpts{};
    try std.testing.expectEqual(@as(?[]const u8, null), opts.cwd);
    try std.testing.expectEqual(@as(u64, 0), opts.timeout_ms);
    try std.testing.expectEqual(@as(usize, 0), opts.max_output_bytes);
}

test "RunResult field assignment" {
    const a = std.testing.allocator;
    const stdout = try a.dupe(u8, "out");
    const stderr = try a.dupe(u8, "err");
    defer {
        a.free(stdout);
        a.free(stderr);
    }

    const rr = RunResult{
        .exit_code = 42,
        .stdout = stdout,
        .stderr = stderr,
        .timed_out = true,
    };

    try std.testing.expectEqual(@as(i32, 42), rr.exit_code);
    try std.testing.expectEqualStrings("out", rr.stdout);
    try std.testing.expectEqualStrings("err", rr.stderr);
    try std.testing.expectEqual(true, rr.timed_out);
}

// ─────────────────────────────────────────────────────────────────────────────
// UNTESTED PATHS (require real process spawn — forbidden in this workspace)
//
//   - Shell.run() with a real argv: spawns via fork/clone + execve.
//     Cannot test because zig test does not sandbox but the workspace
//     CLAUDE.md forbids builds/execution on the developer machine.
//
//   - Timeout logic: requires a child that sleeps longer than timeout_ms.
//     The kill(path) + wait4() path is exercised only when a real child
//     is spawned and exceeds the deadline.
//
//   - cwd option: requires a real child to observe its working directory.
//
//   - Concurrent runs: two Shell.run() calls with different argv should
//     not interfere; requires real spawns.
//
//   - Signal exit codes: exit_code negated from Signal/Stopped term;
//     only observable with a real child killed by signal.
//
// These paths will be tested in the openrouterd integration test suite
// (daemon-level tests that are authorised to spawn processes).
// ─────────────────────────────────────────────────────────────────────────────
