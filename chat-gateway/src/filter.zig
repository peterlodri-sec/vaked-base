const std = @import("std");

pub const ComplianceResult = struct {
    ok: bool,
    reason: []const u8,
};

const GrammarError = error{
    HashHeaderMissing,
    HashMismatch,
    FileReadFailed,
    OutOfMemory,
};

/// Expected evolution hash. Replace with the value committed in the
/// vaked/grammar/vaked-v0-plus.ebnf header line: "# evolution_hash: <hex>"
const EXPECTED_EVOLUTION_HASH: []const u8 = "0000000000000000000000000000000000000000000000000000000000000000";

const GRAMMAR_PATH = "vaked/grammar/vaked-v0-plus.ebnf";
const HASH_HEADER_PREFIX = "# evolution_hash:";

/// Reads the grammar file header and extracts the declared evolution_hash.
fn readEvolutionHash(allocator: std.mem.Allocator) GrammarError![]u8 {
    const file = std.fs.cwd().openFile(GRAMMAR_PATH, .{}) catch return GrammarError.FileReadFailed;
    defer file.close();

    const contents = file.readToEndAlloc(allocator, 1 << 24) catch return GrammarError.FileReadFailed;
    defer allocator.free(contents);

    var lines = std.mem.splitScalar(u8, contents, '\n');
    while (lines.next()) |line| {
        const trimmed = std.mem.trim(u8, line, " \t\r");
        if (std.mem.startsWith(u8, trimmed, HASH_HEADER_PREFIX)) {
            const raw = trimmed[HASH_HEADER_PREFIX.len..];
            const hash = std.mem.trim(u8, raw, " \t\r");
            return allocator.dupe(u8, hash) catch return GrammarError.OutOfMemory;
        }
        // Stop scanning once we leave the header comment block.
        if (trimmed.len != 0 and !std.mem.startsWith(u8, trimmed, "#")) break;
    }
    return GrammarError.HashHeaderMissing;
}

/// Verifies that the grammar file's declared evolution_hash matches the
/// hash this validator was built against.
pub fn checkEvolutionHash(allocator: std.mem.Allocator) ComplianceResult {
    const found = readEvolutionHash(allocator) catch |err| {
        return switch (err) {
            GrammarError.HashHeaderMissing => .{ .ok = false, .reason = "grammar: evolution_hash header missing" },
            GrammarError.FileReadFailed => .{ .ok = false, .reason = "grammar: unable to read vaked-v0-plus.ebnf" },
            else => .{ .ok = false, .reason = "grammar: hash check internal error" },
        };
    };
    defer allocator.free(found);

    if (!std.mem.eql(u8, found, EXPECTED_EVOLUTION_HASH)) {
        return .{ .ok = false, .reason = "grammar: evolution_hash mismatch (grammar drift detected)" };
    }
    return .{ .ok = true, .reason = "grammar: evolution_hash verified" };
}

/// Grammar constraints applied to incoming prompt text.
const Constraints = struct {
    const max_len: usize = 32 * 1024;
    const max_line_len: usize = 4096;
    const max_consecutive_newlines: usize = 8;
    // Disallowed control characters (allow \t, \n, \r).
    fn isForbiddenControl(c: u8) bool {
        return (c < 0x20 and c != '\t' and c != '\n' and c != '\r') or c == 0x7f;
    }
};

/// Validates that the incoming prompt text conforms to grammar constraints.
fn validateText(text: []const u8) ComplianceResult {
    if (text.len == 0) {
        return .{ .ok = false, .reason = "prompt: empty input" };
    }
    if (text.len > Constraints.max_len) {
        return .{ .ok = false, .reason = "prompt: exceeds maximum length" };
    }
    if (!std.unicode.utf8ValidateSlice(text)) {
        return .{ .ok = false, .reason = "prompt: invalid UTF-8 encoding" };
    }

    var line_len: usize = 0;
    var run_newlines: usize = 0;

    for (text) |c| {
        if (Constraints.isForbiddenControl(c)) {
            return .{ .ok = false, .reason = "prompt: forbidden control character" };
        }
        if (c == '\n') {
            run_newlines += 1;
            if (run_newlines > Constraints.max_consecutive_newlines) {
                return .{ .ok = false, .reason = "prompt: too many consecutive newlines" };
            }
            line_len = 0;
        } else if (c == '\r') {
            line_len = 0;
        } else {
            run_newlines = 0;
            line_len += 1;
            if (line_len > Constraints.max_line_len) {
                return .{ .ok = false, .reason = "prompt: line exceeds maximum length" };
            }
        }
    }

    return .{ .ok = true, .reason = "prompt: compliant" };
}

/// Full pipeline: verify grammar integrity, then validate prompt text.
pub fn validatePrompt(allocator: std.mem.Allocator, text: []const u8) ComplianceResult {
    const hash_result = checkEvolutionHash(allocator);
    if (!hash_result.ok) return hash_result;
    return validateText(text);
}

test "valid prompt passes text constraints" {
    const r = validateText("hello world");
    try std.testing.expect(r.ok);
}

test "empty prompt fails" {
    const r = validateText("");
    try std.testing.expect(!r.ok);
}

test "forbidden control char fails" {
    const r = validateText("bad\x00input");
    try std.testing.expect(!r.ok);
}

test "invalid utf8 fails" {
    const r = validateText(&[_]u8{ 0xff, 0xfe });
    try std.testing.expect(!r.ok);
}
