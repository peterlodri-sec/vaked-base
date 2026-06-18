const std = @import("std");
const linux = std.os.linux;
pub const Workspace = struct {
    path: []const u8,
    data: []align(std.mem.page_size) u8,
    size: usize,
    pub fn map(allocator: std.mem.Allocator, file_path: []const u8) !Workspace {
        const fd = linux.open(@ptrCast(file_path.ptr), linux.O.RDWR, 0);
        if (fd < 0) return error.FileError;
        const stat = linux.fstat(@intCast(fd));
        const size: usize = @intCast(stat.size);
        const ptr = linux.mmap(null, size, linux.PROT.READ | linux.PROT.WRITE, linux.MAP.SHARED, @intCast(fd), 0);
        if (ptr == linux.MAP.FAILED) return error.MmapError;
        _ = linux.close(@intCast(fd));
        return Workspace{ .path = try allocator.dupe(u8, file_path), .data = @as([*]align(std.mem.page_size) u8, @ptrCast(@alignCast(ptr)))[0..size], .size = size };
    }
    pub fn asArrayBuffer(self: *Workspace) []u8 { return self.data; }
};
pub const MemoryPlane = extern struct {
    magic: u32 align(64),              // 0x7C242080
    budget_remaining: f64,             // $5.87
    budget_cap: f64,                   // $6.00
    total_tokens: u64,                 // 1,250,000
    active_requests: u32,              // 3
    conductor_model: [64]u8,           // "deepseek-v4-pro"
    context7_enabled: u8,
    file_count: u16,
    gpu_dph: f64,                      // $0.32/hr
    gpu_status: [16]u8,               // "running"
    last_build_status: u8,            // 0=pass, 1=fail
    last_build_errors: [512]u8,       // compiler output
    _pad: [40]u8,
    pub fn init() MemoryPlane {
        var plane = std.mem.zeroes(MemoryPlane);
        plane.magic = 0x7C242080;
        plane.budget_remaining = 6.00;
        plane.budget_cap = 6.00;
        return plane;
    }
    pub fn ptr(self: *MemoryPlane) *MemoryPlane { return self; }
    pub fn getBudget(self: *const MemoryPlane) f64 { return self.budget_remaining; }
    pub fn getTokens(self: *const MemoryPlane) u64 { return self.total_tokens; }
    pub fn getModel(self: *const MemoryPlane) []const u8 { return std.mem.sliceTo(&self.conductor_model, 0); }
    pub fn getGpuStatus(self: *const MemoryPlane) []const u8 { return std.mem.sliceTo(&self.gpu_status, 0); }
    pub fn buildPassed(self: *const MemoryPlane) bool { return self.last_build_status == 0; }
    pub fn updateBudget(self: *MemoryPlane, amount: f64) void { self.budget_remaining = amount; }
    pub fn updateTokens(self: *MemoryPlane, tokens: u64) void { self.total_tokens = tokens; }
    pub fn updateBuildResult(self: *MemoryPlane, passed: bool, errors: []const u8) void {
        self.last_build_status = if (passed) @as(u8, 0) else @as(u8, 1);
        @memcpy(self.last_build_errors[0..@min(errors.len, 511)], errors);
    }
};
pub const TelemetryPipe = struct {
    socket_path: []const u8,
    fd: i32,
    pub fn create(allocator: std.mem.Allocator, path: []const u8) !TelemetryPipe {
        const fd = linux.socket(linux.AF.UNIX, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0);
        if (fd < 0) return error.SocketError;
        var addr = std.mem.zeroes(linux.sockaddr.un);
        addr.family = linux.AF.UNIX;
        @memcpy(addr.path[0..@min(path.len, 107)], path);
        _ = linux.bind(@intCast(fd), @ptrCast(&addr), @sizeOf(linux.sockaddr.un));
        _ = linux.listen(@intCast(fd), 8);
        return TelemetryPipe{ .socket_path = try allocator.dupe(u8, path), .fd = @intCast(fd) };
    }
    pub fn push(self: *TelemetryPipe, event: []const u8) void {
        const cfd = linux.accept(self.fd, null, null);
        if (cfd < 0) return;
        _ = linux.write(@intCast(cfd), @ptrCast(event.ptr), event.len);
        _ = linux.close(@intCast(cfd));
    }
    pub fn pushMemoryPlane(self: *TelemetryPipe, plane: *const MemoryPlane) void {
        const bytes: [*]const u8 = @ptrCast(plane);
        self.push(bytes[0..@sizeOf(MemoryPlane)]);
    }
};
pub const FlatRuntime = struct {
    workspace: Workspace,
    plane: *MemoryPlane,
    pipe: TelemetryPipe,
    allocator: std.mem.Allocator,
    pub fn init(allocator: std.mem.Allocator, workspace_path: []const u8, socket_path: []const u8) !FlatRuntime {
        const ws = try Workspace.map(allocator, workspace_path);
        const plane = @as(*MemoryPlane, @ptrCast(@alignCast(ws.data.ptr)));
        plane.* = MemoryPlane.init();
        const tp = try TelemetryPipe.create(allocator, socket_path);
        return FlatRuntime{ .workspace = ws, .plane = plane, .pipe = tp, .allocator = allocator };
    }
    pub fn tick(self: *FlatRuntime, build_errors: []const u8, gpu_dph: f64) void {
        self.plane.updateBuildResult(build_errors.len == 0, build_errors);
        self.plane.updateBudget(self.plane.budget_remaining - (gpu_dph / 3600.0));
        self.pipe.pushMemoryPlane(self.plane);
    }
};