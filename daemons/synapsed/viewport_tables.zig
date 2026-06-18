//! Flat state buffer matrix — 256 agents, contiguous, DOD layout
//! No OOP. No recursive layout objects. Just flat index tables.
//! GENESIS_SEAL: c4b8f9e0

const std = @import("std");

pub const AgentStatus = enum(u2) { idle = 0, executing = 1, resolving = 2, panic = 3 };
pub const TaskCluster = enum(u3) { compiler_lexer = 0, memory_ebpf = 1, openrouter_bus = 2, mcp_tooling = 3, test_fuzz = 4 };

pub const SubAgentState = packed struct {
    id: u16,
    status: AgentStatus,
    cluster: TaskCluster,
    recursion_depth: u8,
    workload_weight: u8,
    proof_fingerprint: [8]u8,
};

pub const MeshViewportTable = struct {
    agents: [256]SubAgentState,
    active_count: usize,
    cluster_offsets: [5][256]u8,
    cluster_counts: [5]u8,

    pub fn init() MeshViewportTable {
        return .{ .agents = undefined, .active_count = 0, .cluster_offsets = undefined, .cluster_counts = .{0} ** 5 };
    }

    pub fn reindex(self: *MeshViewportTable) void {
        @memset(&self.cluster_counts, 0);
        var i: usize = 0;
        while (i < self.active_count) : (i += 1) {
            const c = @intFromEnum(self.agents[i].cluster);
            const slot = self.cluster_counts[c];
            self.cluster_offsets[c][slot] = @intCast(i);
            self.cluster_counts[c] += 1;
            if (self.cluster_counts[c] >= 256) break;
        }
    }

    pub fn lookup(self: *MeshViewportTable, cluster: TaskCluster) []const u8 {
        const c = @intFromEnum(cluster);
        return self.cluster_offsets[c][0..self.cluster_counts[c]];
    }
};

test "init and reindex" {
    var table = MeshViewportTable.init();
    var i: usize = 0;
    while (i < 10) : (i += 1) {
        table.agents[i] = .{
            .id = @intCast(i), .status = .idle, .cluster = @enumFromInt(@mod(i, 5)),
            .recursion_depth = 1, .workload_weight = 50, .proof_fingerprint = .{0} ** 8,
        };
        table.active_count = i + 1;
    }
    table.reindex();
    try std.testing.expect(table.cluster_counts[0] >= 2);
    try std.testing.expect(table.cluster_counts[1] >= 1);
}
