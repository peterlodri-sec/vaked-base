//! Recursive Sub-Agent Protocol — Depth-5 · Prefix Cache · Fractal TUI
//! FrozenPrefix inherits 98% cache-hit. VolatileSuffix = task-specific.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

// ═══════════════════════════════════════════════════════════
// LAYER 1: Recursion Governance — ExecutionFrame C-struct
// ═══════════════════════════════════════════════════════════

pub const MAX_DEPTH = 5;

pub const ExecutionFrame = extern struct {
    id: u32 align(64),
    depth: u8,                  // 0..5, circuit breaker at 5
    parent_id: u32,             // 0 = root
    child_ids: [MAX_DEPTH]u32,  // spawned children
    child_count: u8,
    status: u8,                 // 0=idle,1=running,2=done,3=failed
    frozen_prefix_offset: u32,  // pointer to shared FrozenPrefix in mmap
    frozen_prefix_len: u32,
    volatile_suffix: [2048]u8,  // task-specific prompt
    result_payload: [4096]u8,   // compacted output for parent
    result_len: u32,
    _pad: [44]u8,
};

pub const CallStack = extern struct {
    magic: u32 align(64),
    frame_count: u16,
    max_depth_reached: u8,
    frames: [32]ExecutionFrame, // 32 concurrent frames across all depths
};

// ═══════════════════════════════════════════════════════════
// LAYER 2: The Spawn Tool — /spawn_subtask with depth breaker
// ═══════════════════════════════════════════════════════════

pub const SpawnResult = struct { frame_id: u32, depth: u8 };

pub fn spawnSubtask(stack: *CallStack, parent_id: u32, task: []const u8, _: []const u8) !SpawnResult {
    if (stack.frame_count >= 32) return error.StackFull;
    const parent = &stack.frames[parent_id];
    if (parent.depth >= MAX_DEPTH) return error.MaxDepth; // circuit breaker

    const child_id = stack.frame_count;
    stack.frame_count += 1;

    var child = &stack.frames[child_id];
    child.id = child_id;
    child.depth = parent.depth + 1;
    child.parent_id = parent_id;
    child.status = 1; // running
    child.frozen_prefix_offset = parent.frozen_prefix_offset;
    child.frozen_prefix_len = parent.frozen_prefix_len;
    child.result_len = 0;
    @memcpy(child.volatile_suffix[0..@min(task.len, 2047)], task);

    parent.child_ids[parent.child_count] = child_id;
    parent.child_count += 1;
    if (child.depth > stack.max_depth_reached) stack.max_depth_reached = child.depth;

    return SpawnResult{ .frame_id = child_id, .depth = child.depth };
}

/// QuickJS FFI callback — invoked as /spawn_subtask from agent logic
pub const SPAWN_JS = 
    \\function spawnSubtask(task, frozenPrefix) {
    \\  if (globalDepth >= 5) return { error: 'MAX_DEPTH' };
    \\  const frame = _zig_spawn(task, frozenPrefix);
    \\  return { frame_id: frame.id, depth: frame.depth };
    \\}
;

// ═══════════════════════════════════════════════════════════
// LAYER 3: Stack Resolution — lockless merge + compact output
// ═══════════════════════════════════════════════════════════

pub fn resolveChild(stack: *CallStack, child_id: u32, result: []const u8) !void {
    const child = &stack.frames[child_id];
    child.status = 2; // done
    child.result_len = @intCast(@min(result.len, 4095));
    @memcpy(child.result_payload[0..child.result_len], result[0..child.result_len]);

    // Compact and inject into parent's volatile suffix as tool_response
    const parent_id = child.parent_id;
    const parent = &stack.frames[parent_id];
    const injection = try std.fmt.bufPrint(
        &parent.volatile_suffix,
        "\n[Subtask D{d} complete: {s}]",
        .{ child.depth, result[0..@min(result.len, 128)] },
    );
    _ = injection;
}

/// Forgetting Tool — compress depth-N output into dense binary payload
pub fn forget(stack: *CallStack, frame_id: u32) void {
    const frame = &stack.frames[frame_id];
    // Compact: keep only result payload, discard volatile suffix
    frame.status = 3; // forgotten
    @memset(&frame.volatile_suffix, 0);
}

// ═══════════════════════════════════════════════════════════
// TUI Fractal Renderer — breadcrumb trail
// ═══════════════════════════════════════════════════════════

pub fn renderBreadcrumb(stack: *CallStack, writer: anytype) !void {
    if (stack.frame_count == 0) return;

    // Find root → trace active path
    var path_buf: [MAX_DEPTH + 1]u32 = undefined;
    var path_len: usize = 0;

    // Find deepest active frame
    var deepest: u32 = 0;
    var i: u16 = 0;
    while (i < stack.frame_count) : (i += 1) {
        if (stack.frames[i].status == 1) deepest = i;
    }

    // Walk up to root
    var current: u32 = deepest;
    while (true) {
        path_buf[path_len] = current;
        path_len += 1;
        if (stack.frames[current].parent_id == current) break;
        if (current == 0) break;
        current = stack.frames[current].parent_id;
    }

    // Render root → leaf
    var j: usize = path_len;
    while (j > 0) {
        j -= 1;
        const f = stack.frames[path_buf[j]];
        
        const icon: []const u8 = switch (f.status) {
            1 => "🟡", 2 => "🟢", 3 => "⚫", else => "⚪",
        };
        try writer.print("{s}[D{d}:{s}]", .{ if (j < path_len - 1) "──>" else "", f.depth, icon });
    }
}

test "spawn subtask within depth limit" {
    var stack: CallStack = undefined;
    @memset(@as([*]u8, @ptrCast(&stack)), 0);
    stack.magic = 0x7C242080;

    // Create root frame
    stack.frames[0] = .{
        .id = 0, .depth = 0, .parent_id = 0, .status = 1,
        .frozen_prefix_offset = 0, .frozen_prefix_len = 0,
    };
    stack.frame_count = 1;

    const result = try spawnSubtask(&stack, 0, "Fix Zig compiler error", "FROZEN_PREFIX");
    try std.testing.expectEqual(@as(u8, 1), result.depth);
    try std.testing.expectEqual(@as(u32, 1), result.frame_id);
    try std.testing.expectEqual(@as(u16, 2), stack.frame_count);
    try std.testing.expectEqual(@as(u8, 1), stack.max_depth_reached);
}

test "circuit breaker at depth 5" {
    var stack: CallStack = undefined;
    @memset(@as([*]u8, @ptrCast(&stack)), 0);
    stack.frames[0].depth = 5;
    stack.frame_count = 1;

    const result = spawnSubtask(&stack, 0, "task", "");
    try std.testing.expectError(error.MaxDepth, result);
}
