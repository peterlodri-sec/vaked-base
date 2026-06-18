//! Zero-Syscall Live Telemetry — shared memory header.
//! TUI reads budget/tokens/files directly from mmap'd arena.
//! Zero CPU overhead. No polling. No syscalls.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

/// Telemetry header — mapped directly into shared memory.
/// TUI reads this struct via pointer map. Updated by daemon atomically.
pub const TelemetryHeader = extern struct {
    magic: u32 align(64),        // 0x7C242080 — genesis validation
    budget_remaining: f64,       // $X.XXXX
    budget_cap: f64,             // $X.XX
    total_tokens: u64,           // running total
    active_requests: u32,        // in-flight API calls
    context7_enabled: u8,        // bool
    conductor_model: [64]u8,     // current model ID
    file_count: u16,             // files in context
    last_update_ms: u64,         // monotonic timestamp
    _padding: [40]u8,            // cache-line aligned to 128 bytes
};

/// Initialize the telemetry header in shared memory.
pub fn initHeader(mmap: []align(std.mem.page_size) u8) *TelemetryHeader {
    const header: *TelemetryHeader = @ptrCast(@alignCast(mmap.ptr));
    header.magic = 0x7C242080;
    header.budget_remaining = 6.00;
    header.budget_cap = 6.00;
    header.total_tokens = 0;
    header.active_requests = 0;
    header.context7_enabled = 1;
    @memset(&header.conductor_model, 0);
    header.file_count = 0;
    header.last_update_ms = 0;
    return header;
}

/// Read telemetry from shared memory — zero syscalls.
/// The TUI calls this to render the header bar.
pub fn readHeader(mmap: []align(std.mem.page_size) u8) TelemetryHeader {
    const header: *const TelemetryHeader = @ptrCast(@alignCast(mmap.ptr));
    if (header.magic != 0x7C242080) {
        // Uninitialized — return defaults
        return .{
            .magic = 0,
            .budget_remaining = 0,
            .budget_cap = 0,
            .total_tokens = 0,
            .active_requests = 0,
            .context7_enabled = 0,
            .conductor_model = .{0} ** 64,
            .file_count = 0,
            .last_update_ms = 0,
            ._padding = .{0} ** 40,
        };
    }
    return header.*;
}

/// Update telemetry — called by the daemon after each agent cycle.
/// Atomic store on x86-64 (aligned 64-bit write).
pub fn updateHeader(header: *TelemetryHeader, budget: f64, tokens: u64, active: u32, ctx7: bool, model: []const u8, files: u16) void {
    @atomicStore(f64, &header.budget_remaining, budget, .monotonic);
    @atomicStore(u64, &header.total_tokens, tokens, .monotonic);
    @atomicStore(u32, &header.active_requests, active, .monotonic);
    header.context7_enabled = @intFromBool(ctx7);
    @memcpy(header.conductor_model[0..@min(model.len, 63)], model);
    header.file_count = files;
    header.last_update_ms = @intCast(std.time.milliTimestamp());
}
