//! patch_test.zig — Unit tests for the Atomic Patch Editor (patch.zig).
//!
//! Run from the vakedz directory:
//!   zig test src/patch_test.zig
//!
//! Tests use std.testing.tmpDir for isolated temp directories.
//! No build/compile/run on developer machine per CLAUDE.md.

const std = @import("std");
const patch = @import("patch.zig");
const testing = std.testing;

// ---------------------------------------------------------------------------
// findBlock tests
// ---------------------------------------------------------------------------

test "findBlock: unique match in middle" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t1.txt", .data = "aaa\nbbb\nccc\nddd\n" });
    const result = try patch.findBlock(testing.allocator, tmp.dir, "t1.txt", &[_][]const u8{ "bbb", "ccc" });
    try testing.expectEqual(@as(usize, 1), result.line_start);
    try testing.expectEqual(@as(usize, 3), result.line_end);
    try testing.expectEqual(true, result.trailing_newline);
}

test "findBlock: no match" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t2.txt", .data = "aaa\nbbb\nccc\n" });
    try testing.expectError(error.NoMatch, patch.findBlock(testing.allocator, tmp.dir, "t2.txt", &[_][]const u8{"zzz"}));
}

test "findBlock: multiple matches" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t3.txt", .data = "dup\noriginal\ndup\n" });
    try testing.expectError(error.MultipleMatches, patch.findBlock(testing.allocator, tmp.dir, "t3.txt", &[_][]const u8{"dup"}));
}

test "findBlock: match at file start" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t4.txt", .data = "first\nsecond\nthird\n" });
    const result = try patch.findBlock(testing.allocator, tmp.dir, "t4.txt", &[_][]const u8{"first"});
    try testing.expectEqual(@as(usize, 0), result.line_start);
    try testing.expectEqual(@as(usize, 0), result.byte_offset);
    try testing.expectEqual(true, result.trailing_newline);
}

test "findBlock: match at file end" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t5.txt", .data = "one\ntwo\nthree\n" });
    const result = try patch.findBlock(testing.allocator, tmp.dir, "t5.txt", &[_][]const u8{"three"});
    try testing.expectEqual(@as(usize, 2), result.line_start);
    try testing.expectEqual(@as(usize, 3), result.line_end);
    try testing.expectEqual(true, result.trailing_newline);
}

test "findBlock: file with no trailing newline" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t6.txt", .data = "line1\nline2" });
    const result = try patch.findBlock(testing.allocator, tmp.dir, "t6.txt", &[_][]const u8{"line2"});
    try testing.expectEqual(@as(usize, 1), result.line_start);
    try testing.expectEqual(false, result.trailing_newline);
}

test "findBlock: empty anchor returns InvalidAnchor" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t7.txt", .data = "anything\n" });
    try testing.expectError(error.InvalidAnchor, patch.findBlock(testing.allocator, tmp.dir, "t7.txt", &[_][]const u8{}));
}

test "findBlock: empty file, non-empty anchor" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t8.txt", .data = "" });
    try testing.expectError(error.NoMatch, patch.findBlock(testing.allocator, tmp.dir, "t8.txt", &[_][]const u8{"x"}));
}

test "findBlock: anchor longer than file" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t9.txt", .data = "short\n" });
    try testing.expectError(error.NoMatch, patch.findBlock(testing.allocator, tmp.dir, "t9.txt", &[_][]const u8{ "short", "missing" }));
}

test "findBlock: single line match" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "t10.txt", .data = "only\n" });
    const result = try patch.findBlock(testing.allocator, tmp.dir, "t10.txt", &[_][]const u8{"only"});
    try testing.expectEqual(@as(usize, 0), result.line_start);
    try testing.expectEqual(@as(usize, 1), result.line_end);
    try testing.expectEqual(true, result.trailing_newline);
}

// ---------------------------------------------------------------------------
// applyBlock tests
// ---------------------------------------------------------------------------

test "applyBlock: unique-match replace roundtrip" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r1.txt", .data = "line1\nline2\nline3\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r1.txt", &[_][]const u8{"line2"}, &[_][]const u8{"REPLACED"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r1.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("line1\nREPLACED\nline3\n", result);
}

test "applyBlock: zero-match error" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r2.txt", .data = "line1\nline2\n" });
    try testing.expectError(error.NoMatch, patch.applyBlock(testing.allocator, tmp.dir, "r2.txt", &[_][]const u8{"nonexistent"}, &[_][]const u8{"x"}));
}

test "applyBlock: multi-match error" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r3.txt", .data = "dup\nunique\ndup\n" });
    try testing.expectError(error.MultipleMatches, patch.applyBlock(testing.allocator, tmp.dir, "r3.txt", &[_][]const u8{"dup"}, &[_][]const u8{"x"}));
}

test "applyBlock: block at file start" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r4.txt", .data = "first\nsecond\nthird\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r4.txt", &[_][]const u8{"first"}, &[_][]const u8{"NEW_FIRST"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r4.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("NEW_FIRST\nsecond\nthird\n", result);
}

test "applyBlock: block at file end" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r5.txt", .data = "one\ntwo\nthree\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r5.txt", &[_][]const u8{"three"}, &[_][]const u8{"LAST"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r5.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("one\ntwo\nLAST\n", result);
}

test "applyBlock: multiline new block (larger)" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r6.txt", .data = "A\nB\nC\nD\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r6.txt", &[_][]const u8{ "B", "C" }, &[_][]const u8{ "X", "Y", "Z" });
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r6.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("A\nX\nY\nZ\nD\n", result);
}

test "applyBlock: multiline new block (smaller)" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r7.txt", .data = "A\nB\nC\nD\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r7.txt", &[_][]const u8{ "B", "C" }, &[_][]const u8{"MID"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r7.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("A\nMID\nD\n", result);
}

test "applyBlock: delete block (empty new_lines)" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r8.txt", .data = "keep\nremove\nkeep\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r8.txt", &[_][]const u8{"remove"}, &[_][]const u8{});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r8.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("keep\nkeep\n", result);
}

test "applyBlock: file without trailing newline" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r9.txt", .data = "line1\nline2" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r9.txt", &[_][]const u8{"line2"}, &[_][]const u8{"replaced"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r9.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("line1\nreplaced", result);
}

test "applyBlock: single-line file, replace with multiline" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r10.txt", .data = "solo\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r10.txt", &[_][]const u8{"solo"}, &[_][]const u8{ "alpha", "beta", "gamma" });
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r10.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("alpha\nbeta\ngamma\n", result);
}

test "applyBlock: block at end without trailing newline, multiline replacement" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r11.txt", .data = "A\nB" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r11.txt", &[_][]const u8{"B"}, &[_][]const u8{ "X", "Y" });
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r11.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("A\nX\nY", result);
}

test "applyBlock: replace entire file contents" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r12.txt", .data = "old1\nold2\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r12.txt", &[_][]const u8{ "old1", "old2" }, &[_][]const u8{ "new1", "new2", "new3" });
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r12.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("new1\nnew2\nnew3\n", result);
}

test "applyBlock: preserve exact bytes outside the match" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    const original = "#!/bin/sh\n# comment\necho hello\n# end\n";
    try tmp.dir.writeFile(.{ .sub_path = "r13.txt", .data = original });
    try patch.applyBlock(testing.allocator, tmp.dir, "r13.txt", &[_][]const u8{"echo hello"}, &[_][]const u8{"echo world"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r13.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("#!/bin/sh\n# comment\necho world\n# end\n", result);
}

test "applyBlock: idempotent — replacing with same content" {
    var tmp = testing.tmpDir(.{});
    defer tmp.cleanup();

    try tmp.dir.writeFile(.{ .sub_path = "r14.txt", .data = "A\nB\nC\n" });
    try patch.applyBlock(testing.allocator, tmp.dir, "r14.txt", &[_][]const u8{"B"}, &[_][]const u8{"B"});
    const result = try tmp.dir.readFileAlloc(testing.allocator, "r14.txt", 4096);
    defer testing.allocator.free(result);
    try testing.expectEqualStrings("A\nB\nC\n", result);
}
