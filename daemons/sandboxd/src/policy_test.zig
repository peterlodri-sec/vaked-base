//! Unit tests for sandboxd WP4-S1 pure logic (src/policy.zig).
//!
//! Expectations derived from the agent_guardd policy.py schema oracle
//! (the WP4 kickoff "First task": `--policy <file>` JSON, "same schema as
//! agent_guardd policy") and the `--`-delimited exec convention.
//!
//! Pure: no unshare/execvpe/seccomp here (those need Linux + privileges and
//! are WP4-S2). Runs anywhere via `zig build test`.

const std = @import("std");
const policy = @import("policy.zig");

// ---- CLI arg split on `--` -------------------------------------------------

test "splitArgs: own flags before --, target argv after" {
    var args = [_][]const u8{ "--policy", "p.json", "--", "/bin/sh", "-c", "echo hi" };
    const split = policy.splitArgs(&args);

    try std.testing.expectEqual(@as(usize, 2), split.own.len);
    try std.testing.expectEqualStrings("--policy", split.own[0]);
    try std.testing.expectEqualStrings("p.json", split.own[1]);

    try std.testing.expectEqual(@as(usize, 3), split.target.len);
    try std.testing.expectEqualStrings("/bin/sh", split.target[0]);
    try std.testing.expectEqualStrings("-c", split.target[1]);
    try std.testing.expectEqualStrings("echo hi", split.target[2]);
}

test "splitArgs: no -- present -> all own, empty target" {
    var args = [_][]const u8{ "--policy", "p.json" };
    const split = policy.splitArgs(&args);
    try std.testing.expectEqual(@as(usize, 2), split.own.len);
    try std.testing.expectEqual(@as(usize, 0), split.target.len);
}

test "splitArgs: trailing -- -> empty target" {
    var args = [_][]const u8{ "--policy", "p.json", "--" };
    const split = policy.splitArgs(&args);
    try std.testing.expectEqual(@as(usize, 2), split.own.len);
    try std.testing.expectEqual(@as(usize, 0), split.target.len);
}

test "splitArgs: leading -- -> empty own, all target" {
    var args = [_][]const u8{ "--", "/bin/true" };
    const split = policy.splitArgs(&args);
    try std.testing.expectEqual(@as(usize, 0), split.own.len);
    try std.testing.expectEqual(@as(usize, 1), split.target.len);
    try std.testing.expectEqualStrings("/bin/true", split.target[0]);
}

test "splitArgs: only first -- splits; later -- belong to target argv" {
    var args = [_][]const u8{ "--policy", "p.json", "--", "git", "log", "--", "path" };
    const split = policy.splitArgs(&args);
    try std.testing.expectEqual(@as(usize, 2), split.own.len);
    try std.testing.expectEqual(@as(usize, 4), split.target.len);
    try std.testing.expectEqualStrings("git", split.target[0]);
    try std.testing.expectEqualStrings("log", split.target[1]);
    try std.testing.expectEqualStrings("--", split.target[2]);
    try std.testing.expectEqualStrings("path", split.target[3]);
}

test "splitArgs: empty args -> empty own and target" {
    var args = [_][]const u8{};
    const split = policy.splitArgs(&args);
    try std.testing.expectEqual(@as(usize, 0), split.own.len);
    try std.testing.expectEqual(@as(usize, 0), split.target.len);
}

// ---- policy JSON parse: deny-all-network -----------------------------------

// Helper: parse JSON bytes into a Policy. The returned Parsed owns the backing
// bytes (its arena); callers keep it alive for the duration of the assertions.
fn parse(allocator: std.mem.Allocator, bytes: []const u8) !struct {
    parsed: std.json.Parsed(std.json.Value),
    pol: policy.Policy,
} {
    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, bytes, .{});
    errdefer parsed.deinit();
    const pol = try policy.parsePolicy(parsed.arena.allocator(), parsed.value);
    return .{ .parsed = parsed, .pol = pol };
}

test "parsePolicy: deny-all-network policy (default=deny, empty allow)" {
    const a = std.testing.allocator;
    const bytes =
        \\{"runtime":"native-exec","membranes":[
        \\  {"membrane":"net","principal":"worker","default":"deny","allow":[]}
        \\]}
    ;
    const r = try parse(a, bytes);
    defer r.parsed.deinit();

    try std.testing.expectEqualStrings("native-exec", r.pol.runtime);
    try std.testing.expectEqual(@as(usize, 1), r.pol.membranes.len);

    const m = r.pol.membranes[0];
    try std.testing.expectEqualStrings("net", m.name);
    try std.testing.expectEqualStrings("worker", m.principal);
    try std.testing.expectEqualStrings("deny", m.default);
    try std.testing.expectEqual(@as(usize, 0), m.allow.len);
}

test "parsePolicy: default posture defaults to deny when absent (oracle)" {
    const a = std.testing.allocator;
    // No `default` key, no `allow` key -> oracle defaults default="deny", allow=[].
    const bytes =
        \\{"membranes":[{"principal":"worker"}]}
    ;
    const r = try parse(a, bytes);
    defer r.parsed.deinit();

    try std.testing.expectEqualStrings("", r.pol.runtime); // runtime defaults to ""
    try std.testing.expectEqual(@as(usize, 1), r.pol.membranes.len);
    const m = r.pol.membranes[0];
    try std.testing.expectEqualStrings("deny", m.default);
    try std.testing.expectEqual(@as(usize, 0), m.allow.len);
    try std.testing.expectEqual(@as(?[]const u8, null), m.grant);
    try std.testing.expectEqual(@as(?[]const u8, null), m.observe);
}

test "parsePolicy: allow rule defaults proto=tcp and cidr=host/32 (oracle)" {
    const a = std.testing.allocator;
    const bytes =
        \\{"membranes":[{"default":"deny","allow":[
        \\  {"host":"10.0.0.5","port":443}
        \\]}]}
    ;
    const r = try parse(a, bytes);
    defer r.parsed.deinit();

    const m = r.pol.membranes[0];
    try std.testing.expectEqual(@as(usize, 1), m.allow.len);
    const rule = m.allow[0];
    try std.testing.expectEqualStrings("tcp", rule.proto);
    try std.testing.expectEqualStrings("10.0.0.5", rule.host);
    try std.testing.expectEqualStrings("10.0.0.5/32", rule.cidr);
    try std.testing.expectEqual(@as(i64, 443), rule.port);
}

// ---- malformed-policy rejection --------------------------------------------

test "parsePolicyBytes: invalid JSON -> PolicyError.ParseError" {
    const a = std.testing.allocator;
    const bytes = "{not valid json";
    try std.testing.expectError(
        policy.PolicyError.ParseError,
        policy.parsePolicyBytes(a, bytes),
    );
}

test "parsePolicyBytes: deny-all-network round trip via the file-bytes entry" {
    const a = std.testing.allocator;
    const bytes =
        \\{"runtime":"native-exec","membranes":[
        \\  {"membrane":"net","principal":"worker","default":"deny","allow":[]}
        \\]}
    ;
    const parsed = try policy.parsePolicyBytes(a, bytes);
    defer parsed.deinit();
    try std.testing.expectEqualStrings("native-exec", parsed.value.runtime);
    try std.testing.expectEqual(@as(usize, 1), parsed.value.membranes.len);
    try std.testing.expectEqualStrings("deny", parsed.value.membranes[0].default);
    try std.testing.expectEqual(@as(usize, 0), parsed.value.membranes[0].allow.len);
}

test "parsePolicy: allow rule missing required host is rejected" {
    const a = std.testing.allocator;
    const bytes =
        \\{"membranes":[{"default":"deny","allow":[{"port":443}]}]}
    ;
    const parsed = try std.json.parseFromSlice(std.json.Value, a, bytes, .{});
    defer parsed.deinit();
    try std.testing.expectError(
        policy.PolicyError.MissingField,
        policy.parsePolicy(parsed.arena.allocator(), parsed.value),
    );
}

test "parsePolicy: allow rule missing required port is rejected" {
    const a = std.testing.allocator;
    const bytes =
        \\{"membranes":[{"default":"deny","allow":[{"host":"10.0.0.5"}]}]}
    ;
    const parsed = try std.json.parseFromSlice(std.json.Value, a, bytes, .{});
    defer parsed.deinit();
    try std.testing.expectError(
        policy.PolicyError.MissingField,
        policy.parsePolicy(parsed.arena.allocator(), parsed.value),
    );
}

test "parsePolicy: top-level non-object is rejected" {
    const a = std.testing.allocator;
    const bytes = "[1,2,3]";
    const parsed = try std.json.parseFromSlice(std.json.Value, a, bytes, .{});
    defer parsed.deinit();
    try std.testing.expectError(
        policy.PolicyError.WrongType,
        policy.parsePolicy(parsed.arena.allocator(), parsed.value),
    );
}
