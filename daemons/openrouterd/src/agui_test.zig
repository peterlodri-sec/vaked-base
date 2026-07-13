//! agui_test.zig — Comprehensive test suite for agui.zig.
//!
//! Covers:
//!   1. Each AGUI_Event variant serializes to its EXACT expected JSON byte string
//!   2. JSON string escaping: ", \, \n, \t, control chars → \u00XX
//!   3. frameSSE: hex chunk length equals byte count; CRLFs correct
//!   4. sseResponseHeaders: all required HTTP headers present; \r\n\r\n terminator
//!   5. EventQueue: FIFO order, full-queue rejection, empty-queue null-pop
//!   6. EventQueue: single-producer/single-consumer integrity
//!   7. Edge cases: zero-length strings, Unicode content, large arguments JSON
//!
//! These tests are WRITTEN for human review. They are NOT executed here;
//! compilation and execution happen on a Linux target after review.
//!
//! All tests use std.io.fixedBufferStream — ZERO syscalls, ZERO file I/O,
//! ZERO allocations outside the test allocator.

const std = @import("std");
const agui = @import("agui.zig");
const testing = std.testing;

// ═══════════════════════════════════════════════════════════════════════════════
// Helper: build an AGUI_Event.chunk with inline content
// ═══════════════════════════════════════════════════════════════════════════════

fn makeChunk(choice_index: u32, content: []const u8) agui.AGUI_Event {
    var event: agui.AGUI_Event = .{ .chunk = .{
        .choice_index = choice_index,
        .content_len = @intCast(content.len),
        .content = undefined,
    } };
    @memcpy(event.chunk.content[0..content.len], content);
    return event;
}

fn makeToolCall(call_id: []const u8, tool_name: []const u8, arguments_json: []const u8) agui.AGUI_Event {
    var event: agui.AGUI_Event = .{ .tool_call = .{
        .call_id_len = @intCast(call_id.len),
        .call_id = undefined,
        .tool_name_len = @intCast(tool_name.len),
        .tool_name = undefined,
        .arguments_len = @intCast(arguments_json.len),
        .arguments_json = undefined,
    } };
    @memcpy(event.tool_call.call_id[0..call_id.len], call_id);
    @memcpy(event.tool_call.tool_name[0..tool_name.len], tool_name);
    @memcpy(event.tool_call.arguments_json[0..arguments_json.len], arguments_json);
    return event;
}

fn makeApproval(request_id: []const u8, description: []const u8) agui.AGUI_Event {
    var event: agui.AGUI_Event = .{ .approval = .{
        .request_id_len = @intCast(request_id.len),
        .request_id = undefined,
        .description_len = @intCast(description.len),
        .description = undefined,
    } };
    @memcpy(event.approval.request_id[0..request_id.len], request_id);
    @memcpy(event.approval.description[0..description.len], description);
    return event;
}

fn serializeToString(allocator: std.mem.Allocator, event: agui.AGUI_Event) ![]const u8 {
    var list = std.ArrayList(u8).init(allocator);
    try agui.serialize(event, list.writer());
    return list.toOwnedSlice();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 1: chunk serialization — exact JSON match
// ═══════════════════════════════════════════════════════════════════════════════

test "chunk: minimal content" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "chunk: choice_index non-zero" {
    const allocator = testing.allocator;
    const event = makeChunk(3, "token");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":3,\"delta\":{\"content\":\"token\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "chunk: choice_index large" {
    const allocator = testing.allocator;
    const event = makeChunk(4294967295, "x"); // max u32
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":4294967295,\"delta\":{\"content\":\"x\"}}}";
    try testing.expectEqualStrings(expected, json);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 2: tool_call serialization — exact JSON match
// ═══════════════════════════════════════════════════════════════════════════════

test "tool_call: basic" {
    const allocator = testing.allocator;
    const event = makeToolCall("c1", "read", "{\"path\":\"/etc/hosts\"}");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"c1\",\"tool_name\":\"read\",\"arguments\":{\"path\":\"/etc/hosts\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "tool_call: empty arguments object" {
    const allocator = testing.allocator;
    const event = makeToolCall("abc", "noop", "{}");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"abc\",\"tool_name\":\"noop\",\"arguments\":{}}}";
    try testing.expectEqualStrings(expected, json);
}

test "tool_call: nested arguments JSON" {
    const allocator = testing.allocator;
    const event = makeToolCall("x1", "bash", "{\"cmd\":\"ls\",\"args\":[\"-la\",\"/tmp\"],\"env\":{\"HOME\":\"/root\"}}");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"x1\",\"tool_name\":\"bash\",\"arguments\":{\"cmd\":\"ls\",\"args\":[\"-la\",\"/tmp\"],\"env\":{\"HOME\":\"/root\"}}}}";
    try testing.expectEqualStrings(expected, json);
}

test "tool_call: arguments array" {
    const allocator = testing.allocator;
    const event = makeToolCall("arr", "multi", "[1,2,3]");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"arr\",\"tool_name\":\"multi\",\"arguments\":[1,2,3]}}";
    try testing.expectEqualStrings(expected, json);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 3: approval serialization — exact JSON match
// ═══════════════════════════════════════════════════════════════════════════════

test "approval: basic" {
    const allocator = testing.allocator;
    const event = makeApproval("r1", "Allow file deletion?");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"r1\",\"description\":\"Allow file deletion?\"}}";
    try testing.expectEqualStrings(expected, json);
}

test "approval: empty description" {
    const allocator = testing.allocator;
    const event = makeApproval("quiet", "");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"quiet\",\"description\":\"\"}}";
    try testing.expectEqualStrings(expected, json);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 4: JSON string escaping — all required escape sequences
// ═══════════════════════════════════════════════════════════════════════════════

test "escaping: double-quote in content" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "he said \"hello\"");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"he said \\\"hello\\\"\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "escaping: backslash in content" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "path\\to\\file");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"path\\\\to\\\\file\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "escaping: newline in description" {
    const allocator = testing.allocator;
    const event = makeApproval("nl", "line1\nline2");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"nl\",\"description\":\"line1\\nline2\"}}";
    try testing.expectEqualStrings(expected, json);
}

test "escaping: tab in content" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "col1\tcol2");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"col1\\tcol2\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "escaping: carriage-return in content" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "before\rafter");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"before\\rafter\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "escaping: control characters → \\u00XX" {
    const allocator = testing.allocator;
    // Build content with various control chars
    const content = &[_]u8{ 0x00, 0x01, 0x08, 0x0B, 0x0C, 0x0E, 0x1F };
    var event: agui.AGUI_Event = .{ .chunk = .{
        .choice_index = 0,
        .content_len = @intCast(content.len),
        .content = undefined,
    } };
    @memcpy(event.chunk.content[0..content.len], content);

    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"\\u0000\\u0001\\u0008\\u000b\\u000c\\u000e\\u001f\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "escaping: combined escapes in tool_call call_id" {
    const allocator = testing.allocator;
    // call_id containing all the special chars at once
    const call_id = &[_]u8{ '"', '\\', '\n', '\r', '\t', 0x01, 'x' };
    const event = makeToolCall(call_id, "t", "{}");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    // The call_id should appear as: \"\\\n\r\t\u0001x inside the JSON string
    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"\\\"\\\\\\n\\r\\t\\u0001x\",\"tool_name\":\"t\",\"arguments\":{}}}";
    try testing.expectEqualStrings(expected, json);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 5: frameSSE — hex length and CRLF correctness
// ═══════════════════════════════════════════════════════════════════════════════

test "frameSSE: hex length is lowercase" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    // payload length = 6 + 16 + 2 = 24 = 0x18
    const json_bytes = "0123456789abcdef";
    try agui.frameSSE(json_bytes, fbs.writer());

    const output = fbs.getWritten();
    // hex must be lowercase
    try testing.expectEqualStrings("18\r\n", output[0..4]);
}

test "frameSSE: hex length for single-byte payload" {
    var buf: [128]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    // payload length = 6 + 1 + 2 = 9 = 0x9
    try agui.frameSSE("X", fbs.writer());

    const output = fbs.getWritten();
    try testing.expectEqualStrings("9\r\ndata: X\n\n\r\n", output);
}

test "frameSSE: chunk header is correct for each length" {
    // Test several lengths to ensure hex encoding is correct
    const test_cases = [_]struct { json_len: usize, expected_hex: []const u8 }{
        .{ .json_len = 0, .expected_hex = "8" },     // 6+0+2 = 8
        .{ .json_len = 1, .expected_hex = "9" },     // 6+1+2 = 9
        .{ .json_len = 8, .expected_hex = "10" },    // 6+8+2 = 16
        .{ .json_len = 26, .expected_hex = "22" },   // 6+26+2 = 34
        .{ .json_len = 249, .expected_hex = "101" }, // 6+249+2 = 257
    };

    for (test_cases) |tc| {
        var buf: [1024]u8 = undefined;
        var fbs = std.io.fixedBufferStream(&buf);

        const json_bytes = try testing.allocator.alloc(u8, tc.json_len);
        defer testing.allocator.free(json_bytes);
        @memset(json_bytes, 'a');

        try agui.frameSSE(json_bytes, fbs.writer());
        const output = fbs.getWritten();

        // Verify hex prefix
        const hex_end = std.mem.indexOfScalar(u8, output, '\r') orelse return error.TestFailed;
        try testing.expectEqualStrings(tc.expected_hex, output[0..hex_end]);

        // Verify \r\n after hex
        try testing.expectEqual(@as(u8, '\r'), output[hex_end]);
        try testing.expectEqual(@as(u8, '\n'), output[hex_end + 1]);
    }
}

test "frameSSE: full output structure" {
    var buf: [512]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    const json_bytes = "{\"key\":\"value\"}";
    try agui.frameSSE(json_bytes, fbs.writer());

    const output = fbs.getWritten();

    // Parse out the parts
    const first_crlf = std.mem.indexOf(u8, output, "\r\n") orelse return error.TestFailed;
    const hex_str = output[0..first_crlf];

    // After hex\r\n comes "data: <json>\n\n\r\n"
    const after_hex = output[first_crlf + 2 ..];

    // Verify "data: " prefix
    try testing.expectEqualStrings("data: ", after_hex[0..6]);

    // Verify JSON body
    const after_prefix = after_hex[6..];
    try testing.expectEqualStrings(json_bytes, after_prefix[0..json_bytes.len]);

    // After json_bytes: \n\n\r\n
    const trailer = after_prefix[json_bytes.len..];
    try testing.expectEqualStrings("\n\n\r\n", trailer);

    // Verify hex_str parses correctly
    const expected_len = 6 + json_bytes.len + 2; // data: + json + \n\n
    const parsed_len = std.fmt.parseInt(usize, hex_str, 16) catch return error.TestFailed;
    try testing.expectEqual(expected_len, parsed_len);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 6: sseResponseHeaders — required fields and format
// ═══════════════════════════════════════════════════════════════════════════════

test "sseResponseHeaders: exact output" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    try agui.sseResponseHeaders(fbs.writer());

    const output = fbs.getWritten();
    const expected =
        "HTTP/1.1 200 OK\r\n" ++
        "Content-Type: text/event-stream\r\n" ++
        "Cache-Control: no-cache\r\n" ++
        "Connection: keep-alive\r\n" ++
        "Transfer-Encoding: chunked\r\n" ++
        "\r\n";
    try testing.expectEqualStrings(expected, output);
}

test "sseResponseHeaders: ends with empty line" {
    var buf: [256]u8 = undefined;
    var fbs = std.io.fixedBufferStream(&buf);

    try agui.sseResponseHeaders(fbs.writer());

    const output = fbs.getWritten();
    try testing.expect(output.len >= 4);
    try testing.expectEqual(@as(u8, '\r'), output[output.len - 4]);
    try testing.expectEqual(@as(u8, '\n'), output[output.len - 3]);
    try testing.expectEqual(@as(u8, '\r'), output[output.len - 2]);
    try testing.expectEqual(@as(u8, '\n'), output[output.len - 1]);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 7: EventQueue — FIFO order
// ═══════════════════════════════════════════════════════════════════════════════

test "EventQueue: init empty" {
    const Q = agui.EventQueue(u32, 8);
    var q = Q.init();
    try testing.expect(q.isEmpty());
    try testing.expect(!q.isFull());
    try testing.expectEqual(@as(usize, 0), q.len());
}

test "EventQueue: FIFO order" {
    const Q = agui.EventQueue(u32, 8);
    var q = Q.init();

    try q.push(10);
    try q.push(20);
    try q.push(30);

    try testing.expectEqual(@as(usize, 3), q.len());

    try testing.expectEqual(@as(?u32, 10), q.pop());
    try testing.expectEqual(@as(?u32, 20), q.pop());
    try testing.expectEqual(@as(?u32, 30), q.pop());
    try testing.expectEqual(@as(?u32, null), q.pop());

    try testing.expect(q.isEmpty());
}

test "EventQueue: wrap-around FIFO" {
    const Q = agui.EventQueue(u32, 4);
    var q = Q.init();

    // Fill
    try q.push(1);
    try q.push(2);
    try q.push(3);
    try q.push(4);
    try testing.expect(q.isFull());

    // Drain half
    try testing.expectEqual(@as(?u32, 1), q.pop());
    try testing.expectEqual(@as(?u32, 2), q.pop());
    try testing.expect(!q.isFull());
    try testing.expect(!q.isEmpty());

    // Refill — should wrap around
    try q.push(5);
    try q.push(6);
    try testing.expect(q.isFull());

    // Drain all — check order
    try testing.expectEqual(@as(?u32, 3), q.pop());
    try testing.expectEqual(@as(?u32, 4), q.pop());
    try testing.expectEqual(@as(?u32, 5), q.pop());
    try testing.expectEqual(@as(?u32, 6), q.pop());
    try testing.expect(q.isEmpty());
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 8: EventQueue — full-queue rejection
// ═══════════════════════════════════════════════════════════════════════════════

test "EventQueue: push returns QueueFull when full" {
    const Q = agui.EventQueue(u32, 2);
    var q = Q.init();

    try q.push(1);
    try q.push(2);
    try testing.expect(q.isFull());

    const result = q.push(3);
    try testing.expectError(error.QueueFull, result);
}

test "EventQueue: push after pop reopens slot" {
    const Q = agui.EventQueue(u32, 2);
    var q = Q.init();

    try q.push(1);
    try q.push(2);
    try testing.expectError(error.QueueFull, q.push(3));

    _ = q.pop();
    try q.push(3); // should succeed now

    try testing.expectEqual(@as(?u32, 2), q.pop());
    try testing.expectEqual(@as(?u32, 3), q.pop());
}

test "EventQueue: capacity 1" {
    const Q = agui.EventQueue(u32, 1);
    var q = Q.init();

    try q.push(42);
    try testing.expect(q.isFull());
    try testing.expectError(error.QueueFull, q.push(99));

    try testing.expectEqual(@as(?u32, 42), q.pop());
    try testing.expect(q.isEmpty());

    try q.push(99);
    try testing.expectEqual(@as(?u32, 99), q.pop());
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 9: EventQueue — empty-queue null-pop
// ═══════════════════════════════════════════════════════════════════════════════

test "EventQueue: pop returns null when empty" {
    const Q = agui.EventQueue(u32, 4);
    var q = Q.init();

    try testing.expectEqual(@as(?u32, null), q.pop());
    try testing.expectEqual(@as(?u32, null), q.pop()); // idempotent
}

test "EventQueue: pop after drain returns null" {
    const Q = agui.EventQueue(u32, 4);
    var q = Q.init();

    try q.push(1);
    _ = q.pop();
    try testing.expectEqual(@as(?u32, null), q.pop());
    try testing.expect(q.isEmpty());
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 10: EventQueue — single-producer/single-consumer integrity
// ═══════════════════════════════════════════════════════════════════════════════

test "EventQueue: SPSC complete cycle" {
    const Q = agui.EventQueue(u32, 256);
    var q = Q.init();

    // Producer pushes N items
    const N: u32 = 100;
    for (0..N) |i| {
        try q.push(@intCast(i));
    }
    try testing.expectEqual(@as(usize, N), q.len());

    // Consumer pops all N items, verifying order and integrity
    for (0..N) |i| {
        const val = q.pop();
        try testing.expect(val != null);
        try testing.expectEqual(@as(u32, @intCast(i)), val.?);
    }
    try testing.expect(q.isEmpty());
}

test "EventQueue: SPSC interleaved push/pop" {
    const Q = agui.EventQueue(u32, 8);
    var q = Q.init();

    // Push, pop, push, pop — verify no corruption
    try q.push(100);
    try testing.expectEqual(@as(?u32, 100), q.pop());
    try testing.expect(q.isEmpty());

    try q.push(200);
    try q.push(300);
    try testing.expectEqual(@as(?u32, 200), q.pop());
    try q.push(400);
    try testing.expectEqual(@as(?u32, 300), q.pop());
    try testing.expectEqual(@as(?u32, 400), q.pop());
    try testing.expect(q.isEmpty());
}

test "EventQueue: SPSC with large structs" {
    // Use a struct that exercises the copy semantics
    const LargeStruct = struct {
        id: u64,
        data: [128]u8,
        tag: u32,
    };

    const Q = agui.EventQueue(LargeStruct, 16);
    var q = Q.init();

    var item: LargeStruct = undefined;
    item.id = 0xDEADBEEF_CAFEBABE;
    @memset(&item.data, 0xAB);
    item.tag = 42;

    try q.push(item);
    const popped = q.pop().?;

    try testing.expectEqual(item.id, popped.id);
    try testing.expectEqual(item.tag, popped.tag);
    try testing.expectEqualSlices(u8, &item.data, &popped.data);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 11: EventQueue — len, isEmpty, isFull consistency
// ═══════════════════════════════════════════════════════════════════════════════

test "EventQueue: len/isEmpty/isFull consistency" {
    const Q = agui.EventQueue(u8, 4);
    var q = Q.init();

    try testing.expectEqual(@as(usize, 0), q.len());
    try testing.expect(q.isEmpty());
    try testing.expect(!q.isFull());

    try q.push(1);
    try testing.expectEqual(@as(usize, 1), q.len());
    try testing.expect(!q.isEmpty());
    try testing.expect(!q.isFull());

    try q.push(2);
    try q.push(3);
    try q.push(4);
    try testing.expectEqual(@as(usize, 4), q.len());
    try testing.expect(!q.isEmpty());
    try testing.expect(q.isFull());

    _ = q.pop();
    try testing.expectEqual(@as(usize, 3), q.len());
    try testing.expect(!q.isFull());

    _ = q.pop();
    _ = q.pop();
    _ = q.pop();
    try testing.expectEqual(@as(usize, 0), q.len());
    try testing.expect(q.isEmpty());
    try testing.expect(!q.isFull());
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 12: Edge cases — zero-length strings, Unicode, large payloads
// ═══════════════════════════════════════════════════════════════════════════════

test "edge: chunk with zero-length content" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "edge: tool_call with empty call_id and tool_name" {
    const allocator = testing.allocator;
    const event = makeToolCall("", "", "null");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"\",\"tool_name\":\"\",\"arguments\":null}}";
    try testing.expectEqualStrings(expected, json);
}

test "edge: approval with empty request_id" {
    const allocator = testing.allocator;
    const event = makeApproval("", "ok");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"\",\"description\":\"ok\"}}";
    try testing.expectEqualStrings(expected, json);
}

test "edge: tool_call arguments is literal null" {
    const allocator = testing.allocator;
    const event = makeToolCall("c", "t", "null");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"c\",\"tool_name\":\"t\",\"arguments\":null}}";
    try testing.expectEqualStrings(expected, json);
}

test "edge: tool_call arguments is literal boolean" {
    const allocator = testing.allocator;
    const event = makeToolCall("c", "t", "true");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    const expected = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"c\",\"tool_name\":\"t\",\"arguments\":true}}";
    try testing.expectEqualStrings(expected, json);
}

test "edge: Unicode content passes through unescaped" {
    const allocator = testing.allocator;
    const event = makeChunk(0, "café 🌍 — em dash");
    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    // UTF-8 bytes above 0x1F should pass through unmodified (JSON allows raw UTF-8)
    const expected = "{\"event\":\"agent/chunk\",\"payload\":{\"choice_index\":0,\"delta\":{\"content\":\"café 🌍 — em dash\"}}}";
    try testing.expectEqualStrings(expected, json);
}

test "edge: approval with long description near MAX_DESCRIPTION" {
    const allocator = testing.allocator;
    // Fill a description with repeating pattern
    var event: agui.AGUI_Event = .{ .approval = .{
        .request_id_len = 1,
        .request_id = undefined,
        .description_len = 1024,
        .description = undefined,
    } };
    event.approval.request_id[0] = 'A';
    @memset(event.approval.description[0..1024], 'x');

    const json = try serializeToString(allocator, event);
    defer allocator.free(json);

    // Verify it starts and ends correctly
    try testing.expect(std.mem.startsWith(u8, json, "{\"event\":\"interaction/approval\",\"payload\":{\"request_id\":\"A\",\"description\":\""));
    try testing.expect(std.mem.endsWith(u8, json, "\"}}"));

    // The 1024 'x' chars should be in the middle.
    // Total length = prefix(75) + 1024 + suffix(3) = 1102
    try testing.expectEqual(@as(usize, 1102), json.len);
}

test "edge: arguments_json with embedded null byte" {
    // The arguments_json is pre-serialized JSON. If it contains a null byte,
    // the length field controls how many bytes are emitted. This test verifies
    // that the length field is respected, not null-termination.
    const allocator = testing.allocator;
    var event: agui.AGUI_Event = .{ .tool_call = .{
        .call_id_len = 1,
        .call_id = undefined,
        .tool_name_len = 1,
        .tool_name = undefined,
        .arguments_len = 5,
        .arguments_json = undefined,
    } };
    event.tool_call.call_id[0] = 'c';
    event.tool_call.tool_name[0] = 't';
    // Put 5 bytes: 'a', 0, 'b', 'c', 'd'
    event.tool_call.arguments_json[0] = 'a';
    event.tool_call.arguments_json[1] = 0;
    event.tool_call.arguments_json[2] = 'b';
    event.tool_call.arguments_json[3] = 'c';
    event.tool_call.arguments_json[4] = 'd';

    // serializeToString uses ArrayList(u8) which can hold null bytes
    var list = std.ArrayList(u8).init(allocator);
    try agui.serialize(event, list.writer());
    const json = list.toOwnedSlice();
    defer allocator.free(json);

    // The null byte at position 1 is embedded in the arguments value.
    // This is technically invalid JSON if the receiver can't handle it,
    // but the serializer is faithful to the length — it emits all 5 bytes.
    const expected_prefix = "{\"event\":\"tool/call\",\"payload\":{\"call_id\":\"c\",\"tool_name\":\"t\",\"arguments\":";
    try testing.expect(std.mem.startsWith(u8, json, expected_prefix));

    // The 5-byte payload follows: 'a', 0, 'b', 'c', 'd'
    const payload_start = expected_prefix.len;
    try testing.expectEqual(@as(u8, 'a'), json[payload_start]);
    try testing.expectEqual(@as(u8, 0), json[payload_start + 1]);
    try testing.expectEqual(@as(u8, 'b'), json[payload_start + 2]);
    try testing.expectEqual(@as(u8, 'c'), json[payload_start + 3]);
    try testing.expectEqual(@as(u8, 'd'), json[payload_start + 4]);

    // Closing braces
    try testing.expectEqualStrings("}}", json[payload_start + 5 ..]);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 13: Compile-time constant sanity
// ═══════════════════════════════════════════════════════════════════════════════

test "capacity constants are non-zero" {
    try testing.expect(agui.MAX_CONTENT > 0);
    try testing.expect(agui.MAX_CALL_ID > 0);
    try testing.expect(agui.MAX_TOOL_NAME > 0);
    try testing.expect(agui.MAX_DESCRIPTION > 0);
    try testing.expect(agui.MAX_ARGUMENTS_JSON > 0);
}

test "capacity constants fit in their length fields" {
    try testing.expect(agui.MAX_CONTENT <= 65535);
    try testing.expect(agui.MAX_ARGUMENTS_JSON <= 65535);
    try testing.expect(agui.MAX_DESCRIPTION <= 65535);
    try testing.expect(agui.MAX_CALL_ID <= 255);
    try testing.expect(agui.MAX_TOOL_NAME <= 255);
}
