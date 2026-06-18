const std = @import("std");
const tables = @import("../../daemons/synapsed/viewport_tables.zig");
pub const MatrixCompactor = struct {
    pub fn purgeGraveyardInPlace(table: *tables.MeshViewportTable) usize {
        var r: usize = 0; var w: usize = 0;
        while (r < table.active_count) : (r += 1) {
            if (table.agents[r].status != .panic) { if (w != r) table.agents[w] = table.agents[r]; w += 1; }
        }
        const shredded = table.active_count - w;
        table.active_count = w;
        table.reindex();
        return shredded;
    }
};
test "purge" { var t = tables.MeshViewportTable.init(); _ = MatrixCompactor.purgeGraveyardInPlace(&t); }
