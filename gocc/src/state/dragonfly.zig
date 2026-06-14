pub const DragonflyClient = struct {
    pub fn init() DragonflyClient { return .{}; }
    pub fn hset(self: *DragonflyClient, key: []const u8, field: []const u8, value: []const u8) !void { _ = self; _ = key; _ = field; _ = value; }
};
