//! Self-negation verifier — detects inverse recursive dependency lock loops
//! The grammar must catch paradoxes before lower emits to eBPF.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const DependencyRule = struct {
    actor_id: u16,
    depends_on_id: u16,
    is_inverted: bool,
};

pub const GraphValidationEngine = struct {
    rules_table: [32]DependencyRule,
    active_rules_count: usize,

    pub fn init() GraphValidationEngine {
        return .{ .rules_table = undefined, .active_rules_count = 0 };
    }

    pub fn verifySelfNegationInvariants(self: *const GraphValidationEngine) !void {
        var i: usize = 0;
        while (i < self.active_rules_count) : (i += 1) {
            var j: usize = 0;
            while (j < self.active_rules_count) : (j += 1) {
                const a = self.rules_table[i];
                const b = self.rules_table[j];
                if (a.actor_id == b.depends_on_id and b.actor_id == a.depends_on_id and a.is_inverted != b.is_inverted) {
                    return error.GraphSelfNegationDetected;
                }
            }
        }
    }
};

test "direct self-negation detected" {
    var engine = GraphValidationEngine.init();
    engine.rules_table[0] = .{ .actor_id = 101, .depends_on_id = 102, .is_inverted = false };
    engine.rules_table[1] = .{ .actor_id = 102, .depends_on_id = 101, .is_inverted = true };
    engine.active_rules_count = 2;
    try std.testing.expectError(error.GraphSelfNegationDetected, engine.verifySelfNegationInvariants());
}

test "no paradox passes" {
    var engine = GraphValidationEngine.init();
    engine.rules_table[0] = .{ .actor_id = 101, .depends_on_id = 102, .is_inverted = false };
    engine.active_rules_count = 1;
    try engine.verifySelfNegationInvariants();
}
