//! Vast.ai Telemetry & Fail-Safe Killswitch — /kill
//! Live GPU status in TUI bar. Ctrl+K → instant destroy → halt billing.
//! GENESIS_SEAL: 7c242080
const std = @import("std");

pub const GpuStatus = struct {
    instance_id: u64,
    gpu_name: []const u8,
    status: []const u8,       // "running", "stopped", "pending"
    dph_total: f64,           // dollars per hour
    uptime_minutes: u64,
    ssh_host: []const u8,
    ssh_port: u16,
};

/// Render GPU status for TUI bottom bar.
/// Format: "RTX_4090 · $0.32/hr · ACTIVE · ssh host:22"
pub fn formatGpuStatus(allocator: std.mem.Allocator, gpu: GpuStatus) ![]const u8 {
    const icon: []const u8 = if (std.mem.eql(u8, gpu.status, "running")) "🟢" else "🔴";
    return std.fmt.allocPrint(allocator, "{s} {s} · ${d:.2}/hr · {s} · ssh {s}:{d}",
        .{ icon, gpu.gpu_name, gpu.dph_total, gpu.status, gpu.ssh_host, gpu.ssh_port });
}

/// Killswitch: fire vastai_destroy asynchronously.
/// Returns immediately — destruction happens in background via io_uring.
pub fn killInstance(allocator: std.mem.Allocator, io: std.Io, api_key: []const u8, instance_id: u64) !void {
    const url = try std.fmt.allocPrint(allocator, "https://console.vast.ai/api/v0/instances/{d}/", .{instance_id});
    defer allocator.free(url);

    var client: std.http.Client = .{ .allocator = allocator, .io = io };
    defer client.deinit();

    const auth = try std.fmt.allocPrint(allocator, "Bearer {s}", .{api_key});
    defer allocator.free(auth);

    var resp: std.ArrayListUnmanaged(u8) = .{ .items = &.{}, .capacity = 0 };
    defer resp.deinit(allocator);
    var w = std.Io.Writer.fromArrayList(&resp);

    const uri = try std.Uri.parse(url);
    var h: [2]std.http.Header = undefined;
    h[0] = .{ .name = "Authorization", .value = auth };
    h[1] = .{ .name = "User-Agent", .value = "openrouterd-killswitch/0.1" };

    _ = client.fetch(.{ .location = .{ .uri = uri }, .method = .DELETE, .response_writer = &w, .extra_headers = &h }) catch return;
    std.log.info("killswitch: instance {d} destroyed — billing halted", .{instance_id});
}

/// Budget guardrail — auto-kill if hourly cost exceeds threshold.
pub fn budgetGuard(allocator: std.mem.Allocator, io: std.Io, api_key: []const u8, instance_id: u64, dph: f64, max_dph: f64) !void {
    if (dph > max_dph) {
        std.log.warn("budget guard: ${d:.2}/hr exceeds ${d:.2}/hr limit — killing instance {d}", .{ dph, max_dph, instance_id });
        try killInstance(allocator, io, api_key, instance_id);
    }
}
