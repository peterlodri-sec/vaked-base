pub const UringLogger = struct {
    pub fn init() UringLogger { return .{}; }
    pub fn appendFrame(self: *UringLogger, data: []const u8) void { _ = self; _ = data; }
};
