const std = @import("std");
const tables = @import("../../daemons/synapsed/viewport_tables.zig");
pub const WorkerHealthMonitor = struct {
    pub fn inspectHealthBitmask(bitmask: u64, workers: []tables.SubAgentState) void {
        for (workers, 0..) |*w, i| {
            const shift: u6 = @intCast(i & 0x3F);
            if ((bitmask >> shift) & 1 == 1) { w.status = .panic; w.workload_weight = 0; }
        }
    }
};
test "health" { var w: [4]tables.SubAgentState = undefined; WorkerHealthMonitor.inspectHealthBitmask(0, &w); }
