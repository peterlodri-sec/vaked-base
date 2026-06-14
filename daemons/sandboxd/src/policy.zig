//! sandboxd — pure policy + CLI logic (WP4-S1).
//!
//! No syscalls. The isolation backend (unshare/execvpe/seccomp, WP4-S2) calls
//! into this module but lives elsewhere; everything here is deterministic and
//! testable on any host.
//!
//! Policy schema is the SAME as `agent_guardd` (see agent_guardd/policy.py,
//! the WP4 oracle, and docs/superpowers/plans/2026-06-14-wp4-kickoff.md
//! "First task"): a `runtime` string + a list of egress `membranes`, each with
//! a deny/allow `default` posture and an `allow[]` rule set. sandboxd-S1 only
//! parses and validates structure; the egress `decide()` verdict is guardd's
//! job and is intentionally NOT ported here.

const std = @import("std");

/// One allow rule, mirroring agent_guardd Rule. In the oracle only `host` and
/// `port` are required; `proto` defaults to "tcp" and `cidr` to `host + "/32"`.
pub const Rule = struct {
    proto: []const u8,
    host: []const u8,
    cidr: []const u8,
    port: i64,
};

/// One egress membrane, mirroring agent_guardd Membrane. Every field except the
/// allow-set is optional in the oracle (`default` defaults to "deny").
pub const Membrane = struct {
    name: []const u8,
    principal: []const u8,
    grant: ?[]const u8,
    default: []const u8,
    allow: []Rule,
    observe: ?[]const u8,
};

/// A parsed policy document, mirroring agent_guardd Policy.
pub const Policy = struct {
    runtime: []const u8,
    membranes: []Membrane,
};

/// Errors from policy parsing. `ParseError` is malformed JSON; `MissingField`
/// is a required field absent (oracle: an allow rule without `host` or `port`).
pub const PolicyError = error{
    ParseError,
    MissingField,
    WrongType,
};

/// The CLI split mirroring the kickoff "First task": sandboxd's own args (e.g.
/// `--policy <file>`) come before the first `--`; the target command + its argv
/// come after. Returns slices into the input `args` (no allocation).
///
///   sandboxd --policy p.json -- /bin/sh -c "echo hi"
///   ^---------- own ---------^    ^------- target -----^
///
/// Edge behaviour (pinned):
///   - no `--` present  -> all args are own; target is empty.
///   - trailing `--`    -> target is empty (`[]`), own is everything before.
///   - leading `--`     -> own is empty, target is everything after.
///   - splits on the FIRST `--` only; later `--` belong to the target argv.
pub const ArgSplit = struct {
    own: [][]const u8,
    target: [][]const u8,
};

pub fn splitArgs(args: [][]const u8) ArgSplit {
    for (args, 0..) |arg, i| {
        if (std.mem.eql(u8, arg, "--")) {
            return .{ .own = args[0..i], .target = args[i + 1 ..] };
        }
    }
    return .{ .own = args, .target = args[args.len..] };
}

/// Parse `--policy <file>` bytes (agent_guardd schema JSON) into a Policy.
/// Malformed JSON maps to `PolicyError.ParseError`. The returned Parsed owns
/// the arena that backs both the JSON tree and the Policy's allocations and
/// borrowed string slices; the caller must `deinit()` it when done.
pub fn parsePolicyBytes(
    allocator: std.mem.Allocator,
    bytes: []const u8,
) PolicyError!std.json.Parsed(Policy) {
    const json_parsed = std.json.parseFromSlice(std.json.Value, allocator, bytes, .{}) catch
        return PolicyError.ParseError;
    errdefer json_parsed.deinit();

    // Reuse the JSON arena for the Policy so one deinit frees everything.
    const arena = json_parsed.arena.allocator();
    const pol = try parsePolicy(arena, json_parsed.value);

    return .{ .arena = json_parsed.arena, .value = pol };
}

/// Parse a policy JSON document (agent_guardd schema). On success the returned
/// Policy borrows string slices from `parsed`; the caller must keep `parsed`
/// alive (its arena owns the bytes). `parsed` is the result of
/// `std.json.parseFromSlice(std.json.Value, allocator, bytes, .{})`.
///
/// Defaulting follows the oracle's `load_policy`:
///   - runtime: "" if absent
///   - membrane name/principal: "" if absent; grant/observe: null if absent
///   - default: "deny" if absent
///   - rule proto: "tcp" if absent; cidr: host ++ "/32" if absent
/// Required (else MissingField): each allow rule's `host` and `port`.
pub fn parsePolicy(allocator: std.mem.Allocator, value: std.json.Value) PolicyError!Policy {
    if (value != .object) return PolicyError.WrongType;
    const root = value.object;

    const runtime = strOr(root.get("runtime"), "") catch return PolicyError.WrongType;

    const membranes_v = root.get("membranes");
    var membranes: []Membrane = &.{};
    if (membranes_v) |mv| {
        if (mv != .array) return PolicyError.WrongType;
        const items = mv.array.items;
        const out = allocator.alloc(Membrane, items.len) catch return PolicyError.ParseError;
        for (items, 0..) |item, i| {
            out[i] = try parseMembrane(allocator, item);
        }
        membranes = out;
    }

    return .{ .runtime = runtime, .membranes = membranes };
}

fn parseMembrane(allocator: std.mem.Allocator, value: std.json.Value) PolicyError!Membrane {
    if (value != .object) return PolicyError.WrongType;
    const obj = value.object;

    const name = strOr(obj.get("membrane"), "") catch return PolicyError.WrongType;
    const principal = strOr(obj.get("principal"), "") catch return PolicyError.WrongType;
    const grant = optStr(obj.get("grant")) catch return PolicyError.WrongType;
    const default = strOr(obj.get("default"), "deny") catch return PolicyError.WrongType;
    const observe = optStr(obj.get("observe")) catch return PolicyError.WrongType;

    const allow_v = obj.get("allow");
    var allow: []Rule = &.{};
    if (allow_v) |av| {
        if (av != .array) return PolicyError.WrongType;
        const items = av.array.items;
        const out = allocator.alloc(Rule, items.len) catch return PolicyError.ParseError;
        for (items, 0..) |item, i| {
            out[i] = try parseRule(allocator, item);
        }
        allow = out;
    }

    return .{
        .name = name,
        .principal = principal,
        .grant = grant,
        .default = default,
        .allow = allow,
        .observe = observe,
    };
}

fn parseRule(allocator: std.mem.Allocator, value: std.json.Value) PolicyError!Rule {
    if (value != .object) return PolicyError.WrongType;
    const obj = value.object;

    // Required, per oracle (r["host"], r["port"]).
    const host_v = obj.get("host") orelse return PolicyError.MissingField;
    if (host_v != .string) return PolicyError.WrongType;
    const host = host_v.string;

    const port_v = obj.get("port") orelse return PolicyError.MissingField;
    const port: i64 = switch (port_v) {
        .integer => |n| n,
        .string => |s| std.fmt.parseInt(i64, s, 10) catch return PolicyError.WrongType,
        else => return PolicyError.WrongType,
    };

    const proto = strOr(obj.get("proto"), "tcp") catch return PolicyError.WrongType;

    // cidr defaults to host ++ "/32" (oracle: r["host"] + "/32").
    const cidr = if (obj.get("cidr")) |cv| blk: {
        if (cv != .string) return PolicyError.WrongType;
        break :blk cv.string;
    } else std.fmt.allocPrint(allocator, "{s}/32", .{host}) catch return PolicyError.ParseError;

    return .{ .proto = proto, .host = host, .cidr = cidr, .port = port };
}

/// Return the string value, or `fallback` if the key was absent (null Value
/// param). A present-but-non-string value is an error.
fn strOr(maybe: ?std.json.Value, fallback: []const u8) error{WrongType}![]const u8 {
    const v = maybe orelse return fallback;
    return switch (v) {
        .string => |s| s,
        .null => fallback,
        else => error.WrongType,
    };
}

/// Return the optional string: null if absent or JSON null, the string if
/// present, error if present as a non-string.
fn optStr(maybe: ?std.json.Value) error{WrongType}!?[]const u8 {
    const v = maybe orelse return null;
    return switch (v) {
        .string => |s| s,
        .null => null,
        else => error.WrongType,
    };
}
