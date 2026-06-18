//! Edge Compute Arbiter — local compilation blocked by default
//! M3 and iPhone are pure canvas terminals. Compute stays in C8 cloud.
//! :::sudo:::cabotage@pm.me::: to override.
//! GENESIS_SEAL: 0c3b8f2d

const std = @import("std");

pub const AuthState = enum { unauthorized, cloud_override_granted };
pub const EdgeComputeArbiter = struct {
    current_auth: AuthState = .unauthorized,
    auth_email: []const u8 = "cabotage@pm.me",

    pub fn verifyExecutionDomain(self: *const EdgeComputeArbiter, command_intent: []const u8) !void {
        if (std.mem.eql(u8, command_intent, "compile") or std.mem.eql(u8, command_intent, "build_binary")) {
            if (self.current_auth == .unauthorized) {
                @panic("DENIED: EDGE COMPILATION BLOCKED. FORWARD TO C8 CLOUD POOL.");
            }
        }
    }
};

test "edge compilation blocked by default" {
    const arbiter = EdgeComputeArbiter{};
    try std.testing.expectError(error.Panic, arbiter.verifyExecutionDomain("compile"));
}
test "edge compilation allowed with override" {
    var arbiter = EdgeComputeArbiter{ .current_auth = .cloud_override_granted };
    arbiter.verifyExecutionDomain("compile") catch |e| {
        try std.testing.expect(error.Panic != e);
    };
}
