//! Sovereignty topology — local-first, WAN kill-switch, autonomous mesh
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const SovereigntyMode = enum { cloud_dependent, local_sovereign };

pub const TopologyConfig = struct {
    mode: SovereigntyMode = .local_sovereign,
    upstream_wan_allowed: bool = false,

    pub fn assertApertureSecurity(self: TopologyConfig) bool {
        if (self.mode == .local_sovereign and self.upstream_wan_allowed) return false;
        return true;
    }
};

test "local sovereign rejects WAN" {
    const cfg = TopologyConfig{ .mode = .local_sovereign, .upstream_wan_allowed = true };
    try std.testing.expect(!cfg.assertApertureSecurity());
}

test "cloud mode allows WAN" {
    const cfg = TopologyConfig{ .mode = .cloud_dependent, .upstream_wan_allowed = true };
    try std.testing.expect(cfg.assertApertureSecurity());
}
