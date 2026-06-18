
const std = @import("std");
const SelfOptimizer = struct {
    count: usize,
    max_rounds: u32,
    pub fn init(max: u32) SelfOptimizer { return .{ .count = 0, .max_rounds = max }; }
    pub fn executeLoop(self: *SelfOptimizer, _: []const u8) !void {
        var r: u32 = 0;
        while (r < self.max_rounds) : (r += 1) { self.count += 1; }
    }
};
test "1M rounds" {
    var o = SelfOptimizer.init(1000000);
    try o.executeLoop("7c242080");
    try std.testing.expectEqual(@as(usize, 1000000), o.count);
}
