//! sandboxd — namespace / exec enforcement daemon (WP4-S1 skeleton).
//!
//! Usage: `sandboxd --policy <file> -- <argv...>`
//!
//! 1. Parse `--policy <file>` (JSON; same schema as the `agent_guardd` egress
//!    membrane policy — `agent_guardd/policy.py`).
//! 2. `unshare(CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWUSER)`.
//! 3. `execvpe` the target argv in the new namespace.
//! 4. Log a sandbox-start entry to eventd over an append-only unix socket.
//!
//! The namespace + exec + socket paths are Linux-only (raw syscalls via
//! `std.os.linux`). They are guarded by a comptime target check so the file
//! still compiles for non-Linux hosts (where they return `error.Unsupported`).
//! The pure-logic parts (CLI split, policy parse) are host-portable and unit
//! tested with `zig build test`.

const std = @import("std");
const builtin = @import("builtin");
const linux = std.os.linux;
const Allocator = std.mem.Allocator;

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------

/// The parsed command line: the `--policy <file>` value and the target argv
/// after the `--` separator. Pure over a pre-collected argv slice so it is
/// trivially unit-testable.
const Cli = struct {
    policy_path: []const u8,
    target_argv: []const []const u8,
};

const CliError = error{
    MissingPolicy,
    MissingSeparator,
    EmptyTarget,
};

/// Split `args` (program name already stripped) into a `Cli`.
///
/// Grammar: `--policy <file> -- <argv...>`. Everything after the first bare
/// `--` is the target argv (verbatim, including any further `--`).
fn parseCli(args: []const []const u8) CliError!Cli {
    var policy_path: ?[]const u8 = null;
    var i: usize = 0;
    while (i < args.len) : (i += 1) {
        const a = args[i];
        if (std.mem.eql(u8, a, "--")) {
            const target = args[i + 1 ..];
            if (target.len == 0) return CliError.EmptyTarget;
            return Cli{
                .policy_path = policy_path orelse return CliError.MissingPolicy,
                .target_argv = target,
            };
        }
        if (std.mem.eql(u8, a, "--policy")) {
            if (i + 1 >= args.len) return CliError.MissingPolicy;
            policy_path = args[i + 1];
            i += 1;
        }
    }
    return CliError.MissingSeparator;
}

// ---------------------------------------------------------------------------
// Policy (mirror of agent_guardd/policy.py)
// ---------------------------------------------------------------------------

/// One allow rule — an emitted `allow[]` entry of `gen/ebpf.policy.json`.
/// Mirrors `agent_guardd.policy.Rule` (proto/host/cidr/port). `proto` and
/// `cidr` are optional in the document; std.json cannot synthesise the
/// host-derived `cidr` default (`host + "/32"`), so it stays null when absent
/// — fine for the deny-all-network skeleton, which carries no allow rules.
const Rule = struct {
    proto: []const u8 = "tcp",
    host: []const u8,
    cidr: ?[]const u8 = null,
    port: i64,
};

/// One egress membrane. Mirrors `agent_guardd.policy.Membrane`
/// (membrane/principal/grant/default/allow/observe).
const Membrane = struct {
    membrane: []const u8 = "",
    principal: []const u8 = "",
    grant: ?[]const u8 = null,
    default: []const u8 = "deny",
    allow: []const Rule = &.{},
    observe: ?[]const u8 = null,
};

/// The whole policy document. Mirrors `agent_guardd.policy.Policy`
/// (runtime/membranes).
const Policy = struct {
    runtime: []const u8 = "",
    membranes: []const Membrane = &.{},
};

/// Parse a `gen/ebpf.policy.json` document. Caller owns the returned
/// `std.json.Parsed(Policy)` and must `deinit()` it. `ignore_unknown_fields`
/// is set because real documents carry fields beyond this skeleton's mirror.
fn parsePolicy(gpa: Allocator, bytes: []const u8) !std.json.Parsed(Policy) {
    return std.json.parseFromSlice(Policy, gpa, bytes, .{
        .ignore_unknown_fields = true,
    });
}

// ---------------------------------------------------------------------------
// Namespace setup (Linux-only)
// ---------------------------------------------------------------------------

const NsError = error{
    Unsupported,
    Unshare,
};

/// Enter fresh mount/pid/net/user namespaces. Linux-only; on any other target
/// this is a comptime-dead branch returning `error.Unsupported`, so the file
/// still compiles (e.g. for the macOS host `zig build test`).
fn enterNamespaces() NsError!void {
    if (builtin.os.tag != .linux) return NsError.Unsupported;
    const flags: usize = linux.CLONE.NEWNS | linux.CLONE.NEWPID |
        linux.CLONE.NEWNET | linux.CLONE.NEWUSER;
    const rc = linux.unshare(flags);
    if (linux.errno(rc) != .SUCCESS) return NsError.Unshare;
}

// ---------------------------------------------------------------------------
// exec (Linux-only)
// ---------------------------------------------------------------------------

const ExecError = error{
    Unsupported,
    EmptyArgv,
    NotFound,
    Exec,
    OutOfMemory,
};

/// `execvpe` the target argv: resolve `argv[0]` against `PATH` (unless it
/// already contains a `/`), then `execve`. Returns only on failure — a
/// successful exec replaces the process image. Linux-only; comptime-guarded.
fn execTarget(
    arena: Allocator,
    argv: []const []const u8,
    envp: [*:null]const ?[*:0]const u8,
) ExecError!noreturn {
    if (builtin.os.tag != .linux) return ExecError.Unsupported;
    if (argv.len == 0) return ExecError.EmptyArgv;

    // Build the NUL-terminated argv vector.
    const argv_z = try arena.allocSentinel(?[*:0]const u8, argv.len, null);
    for (argv, 0..) |a, i| argv_z[i] = (try arena.dupeZ(u8, a)).ptr;

    if (std.mem.indexOfScalar(u8, argv[0], '/') != null) {
        const path0 = try arena.dupeZ(u8, argv[0]);
        _ = linux.execve(path0.ptr, argv_z.ptr, envp);
        return ExecError.Exec;
    }

    // Skeleton resolves a bare argv[0] against a fixed default PATH (the child
    // runs with an empty env; PATH inheritance/filtering is WP4-S2).
    const path_env = "/usr/local/bin:/usr/bin:/bin";
    var it = std.mem.tokenizeScalar(u8, path_env, ':');
    while (it.next()) |dir| {
        const full = try std.fs.path.joinZ(arena, &.{ dir, argv[0] });
        const rc = linux.execve(full.ptr, argv_z.ptr, envp);
        // ENOENT/EACCES on this dir => try the next; anything else is fatal.
        switch (linux.errno(rc)) {
            .NOENT, .ACCES => continue,
            else => return ExecError.Exec,
        }
    }
    return ExecError.NotFound;
}

// ---------------------------------------------------------------------------
// eventd logger stub (Linux-only; append-only unix socket)
// ---------------------------------------------------------------------------

const EventdError = error{
    Unsupported,
    Socket,
    Connect,
    Write,
};

/// Append one JSON line to the eventd unix socket at `sock_path`.
///
/// The byte format mirrors the eventd payload contract
/// (`eventd/core.py`: a JSON object body; the daemon wraps it in the
/// `{seq,prev,payload,hash}` hash-chain entry). This stub emits only the
/// payload body as a single LF-terminated line; the full canonical-JSON /
/// hash-chain port is WP4-S4. Linux-only; comptime-guarded.
fn logToEventd(sock_path: []const u8, line: []const u8) EventdError!void {
    if (builtin.os.tag != .linux) return EventdError.Unsupported;

    const fd_rc = linux.socket(linux.AF.UNIX, linux.SOCK.STREAM, 0);
    if (linux.errno(fd_rc) != .SUCCESS) return EventdError.Socket;
    const fd: i32 = @intCast(fd_rc);
    defer _ = linux.close(fd);

    var addr = linux.sockaddr.un{ .family = linux.AF.UNIX, .path = undefined };
    if (sock_path.len >= addr.path.len) return EventdError.Connect;
    @memcpy(addr.path[0..sock_path.len], sock_path);
    addr.path[sock_path.len] = 0;

    const c_rc = linux.connect(fd, @ptrCast(&addr), @sizeOf(linux.sockaddr.un));
    if (linux.errno(c_rc) != .SUCCESS) return EventdError.Connect;

    var off: usize = 0;
    while (off < line.len) {
        const w = linux.write(fd, line.ptr + off, line.len - off);
        if (linux.errno(w) != .SUCCESS) return EventdError.Write;
        if (w == 0) return EventdError.Write;
        off += w;
    }
    // LF terminator (one JSON object per line, per eventd/core.py).
    const nl = [_]u8{'\n'};
    if (linux.errno(linux.write(fd, &nl, 1)) != .SUCCESS) return EventdError.Write;
}

/// Build the eventd payload body for a sandbox-start event. The JSON object
/// is the event `payload` the daemon will chain; `kind` follows the eventd
/// kind convention (`payload.kind`).
fn sandboxStartLine(arena: Allocator, principal: []const u8, target0: []const u8) ![]u8 {
    return std.fmt.allocPrint(arena,
        "{{\"kind\":\"sandbox_start\",\"principal\":\"{s}\",\"target\":\"{s}\",\"v\":1}}",
        .{ principal, target0 },
    );
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

const EVENTD_SOCK = "/run/vaked/eventd.sock";

pub fn main(init: std.process.Init) !u8 {
    const arena = init.arena.allocator();
    const gpa = init.gpa;

    const all_args = try init.minimal.args.toSlice(arena);
    if (all_args.len <= 1) {
        std.debug.print("usage: sandboxd --policy <file> -- <argv...>\n", .{});
        return 2;
    }

    const cli = parseCli(all_args[1..]) catch |err| {
        std.debug.print("sandboxd: bad CLI ({t})\n", .{err});
        std.debug.print("usage: sandboxd --policy <file> -- <argv...>\n", .{});
        return 2;
    };

    const bytes = std.Io.Dir.cwd().readFileAlloc(
        init.io,
        cli.policy_path,
        gpa,
        .limited(1 << 20),
    ) catch |err| {
        std.debug.print("sandboxd: cannot read policy {s} ({t})\n", .{ cli.policy_path, err });
        return 1;
    };
    defer gpa.free(bytes);

    var parsed = parsePolicy(gpa, bytes) catch |err| {
        std.debug.print("sandboxd: bad policy json ({t})\n", .{err});
        return 1;
    };
    defer parsed.deinit();
    const policy = parsed.value;

    const principal: []const u8 = if (policy.membranes.len > 0)
        policy.membranes[0].principal
    else
        "";

    // Log sandbox-start (best-effort: the daemon may not be up in dev).
    const line = try sandboxStartLine(arena, principal, cli.target_argv[0]);
    logToEventd(EVENTD_SOCK, line) catch |err| {
        std.debug.print("sandboxd: eventd log skipped ({t})\n", .{err});
    };

    enterNamespaces() catch |err| {
        std.debug.print("sandboxd: namespace setup failed ({t})\n", .{err});
        return 1;
    };

    // Skeleton: exec with an empty environment (deny-all posture leaks no
    // host env into the sandbox). Inheriting/filtering env is WP4-S2.
    const empty_envp = [_:null]?[*:0]const u8{};
    execTarget(arena, cli.target_argv, &empty_envp) catch |err| {
        std.debug.print("sandboxd: exec failed ({t})\n", .{err});
        return 1;
    };
}

// ---------------------------------------------------------------------------
// Tests (pure logic only — no namespace / exec / socket syscalls)
// ---------------------------------------------------------------------------

test "parseCli: policy then separator then argv" {
    const args = [_][]const u8{ "--policy", "p.json", "--", "/bin/sh", "-c", "echo hi" };
    const cli = try parseCli(&args);
    try std.testing.expectEqualStrings("p.json", cli.policy_path);
    try std.testing.expectEqual(@as(usize, 3), cli.target_argv.len);
    try std.testing.expectEqualStrings("/bin/sh", cli.target_argv[0]);
    try std.testing.expectEqualStrings("echo hi", cli.target_argv[2]);
}

test "parseCli: argv may contain its own --" {
    const args = [_][]const u8{ "--policy", "p.json", "--", "git", "--", "log" };
    const cli = try parseCli(&args);
    try std.testing.expectEqual(@as(usize, 3), cli.target_argv.len);
    try std.testing.expectEqualStrings("--", cli.target_argv[1]);
}

test "parseCli: missing separator" {
    const args = [_][]const u8{ "--policy", "p.json" };
    try std.testing.expectError(CliError.MissingSeparator, parseCli(&args));
}

test "parseCli: separator with no target" {
    const args = [_][]const u8{ "--policy", "p.json", "--" };
    try std.testing.expectError(CliError.EmptyTarget, parseCli(&args));
}

test "parseCli: separator but no policy" {
    const args = [_][]const u8{ "--", "/bin/true" };
    try std.testing.expectError(CliError.MissingPolicy, parseCli(&args));
}

test "parsePolicy: deny-all-network minimal policy" {
    const json =
        \\{"runtime":"r0","membranes":[{"membrane":"m0","principal":"agent://a","default":"deny","allow":[]}]}
    ;
    var parsed = try parsePolicy(std.testing.allocator, json);
    defer parsed.deinit();
    const p = parsed.value;
    try std.testing.expectEqualStrings("r0", p.runtime);
    try std.testing.expectEqual(@as(usize, 1), p.membranes.len);
    try std.testing.expectEqualStrings("agent://a", p.membranes[0].principal);
    try std.testing.expectEqualStrings("deny", p.membranes[0].default);
    try std.testing.expectEqual(@as(usize, 0), p.membranes[0].allow.len);
}

test "parsePolicy: allow rule fields mirror agent_guardd" {
    const json =
        \\{"runtime":"r0","membranes":[{"membrane":"m0","principal":"agent://a","default":"deny",
        \\"allow":[{"proto":"tcp","host":"10.0.0.1","cidr":"10.0.0.0/24","port":443}]}]}
    ;
    var parsed = try parsePolicy(std.testing.allocator, json);
    defer parsed.deinit();
    const r = parsed.value.membranes[0].allow[0];
    try std.testing.expectEqualStrings("tcp", r.proto);
    try std.testing.expectEqualStrings("10.0.0.1", r.host);
    try std.testing.expectEqualStrings("10.0.0.0/24", r.cidr.?);
    try std.testing.expectEqual(@as(i64, 443), r.port);
}

test "parsePolicy: unknown fields ignored" {
    const json =
        \\{"runtime":"r0","schema":"v9","membranes":[{"principal":"p","extra":true}]}
    ;
    var parsed = try parsePolicy(std.testing.allocator, json);
    defer parsed.deinit();
    try std.testing.expectEqualStrings("deny", parsed.value.membranes[0].default);
}

test "sandboxStartLine: payload body shape" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const line = try sandboxStartLine(arena.allocator(), "agent://a", "/bin/sh");
    try std.testing.expectEqualStrings(
        "{\"kind\":\"sandbox_start\",\"principal\":\"agent://a\",\"target\":\"/bin/sh\",\"v\":1}",
        line,
    );
}
