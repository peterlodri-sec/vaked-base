pub const NullclawClient = struct {
    endpoint: []const u8,
    pub fn init(endpoint: []const u8) NullclawClient { return .{ .endpoint = endpoint }; }
};
