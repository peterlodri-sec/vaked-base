// vaked-fm: pulse-gen.zig — telemetry sonification engine
// Converts swarm state into audio control signals
// Compile: zig build-exe pulse-gen.zig -O ReleaseFast
const std = @import("std");

const BPM_BASE: f64 = 60.0;    // 60 BPM — calm, deliberate
const BPM_DRIFT: f64 = 90.0;   // 90 BPM — drift detected, heightened
const BPM_PANIC: f64 = 140.0;  // 140 BPM — truth threshold breached

// Swarm telemetry structure
const Telemetry = struct {
    status: []const u8,        // "synced", "syncing", "divergence"
    convergence_ms: f64,
    trust_index: f64,
    nodes_online: u8,
    drift_detected: bool,
    genesis_seal_holds: bool,
};

// Audio control signal output
const ControlSignal = struct {
    bpm: f64,
    sub_bass_hz: f64,       // heartbeat frequency (20-60 Hz)
    harmonic_hz: f64,       // genesis seal harmonic (220 Hz base)
    chime_interval_ms: u64,  // capability-graph update chime spacing
    filter_resonance: f64,   // synth-filter intensity (0-1)
    alert_active: bool,      // integrity alert flag
};

fn compute_control_signal(t: Telemetry) ControlSignal {
    var sig = ControlSignal{
        .bpm = BPM_BASE,
        .sub_bass_hz = 41.2,  // E1 — low, grounded
        .harmonic_hz = 220.0,  // A3 — clean, resonant
        .chime_interval_ms = 5000,
        .filter_resonance = 0.1,
        .alert_active = false,
    };

    // Status → BPM mapping
    if (std.mem.eql(u8, t.status, "divergence")) {
        sig.bpm = BPM_DRIFT;
        sig.filter_resonance = 0.4;
    } else if (t.drift_detected) {
        sig.bpm = BPM_PANIC;
        sig.filter_resonance = 0.8;
        sig.alert_active = true;
    } else if (t.convergence_ms > 300) {
        sig.bpm = BPM_BASE + (t.convergence_ms / 100.0);
        sig.sub_bass_hz = 41.2 + (t.convergence_ms / 500.0);
        sig.filter_resonance = 0.2;
    }

    // Trust index → harmonic stability
    if (t.trust_index < 0.7) {
        sig.harmonic_hz = 220.0 + ((1.0 - t.trust_index) * 20.0); // slight detune
        sig.filter_resonance += 0.1;
    }

    // Node count → chime density
    sig.chime_interval_ms = @as(u64, @intFromFloat(10000.0 / @as(f64, @floatFromInt(t.nodes_online))));

    // Genesis seal holds → steady sub-bass
    if (!t.genesis_seal_holds) {
        sig.bpm = BPM_PANIC;
        sig.sub_bass_hz = 20.0;  // lowest audible — danger
        sig.alert_active = true;
    }

    return sig;
}

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();

    // Read telemetry from stdin (JSON)
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    const stdin = std.io.getStdIn().reader();
    const input = try stdin.readAllAlloc(allocator, 1024 * 1024);
    defer allocator.free(input);

    // Parse telemetry (simplified — production uses std.json)
    var t = Telemetry{
        .status = "synced",
        .convergence_ms = 27.3,
        .trust_index = 1.0,
        .nodes_online = 5,
        .drift_detected = false,
        .genesis_seal_holds = true,
    };

    if (std.mem.indexOf(u8, input, "divergence") != null) {
        t.status = "divergence";
    }
    if (std.mem.indexOf(u8, input, "\"drift\"") != null) {
        t.drift_detected = true;
    }

    const sig = compute_control_signal(t);

    // Output control signal as JSON for audio processor
    try stdout.print(
        \\{{"bpm":{d},"sub_bass_hz":{d},"harmonic_hz":{d},
        \\"chime_interval_ms":{d},"filter_resonance":{d},"alert_active":{d}}}
    , .{
        sig.bpm,
        sig.sub_bass_hz,
        sig.harmonic_hz,
        sig.chime_interval_ms,
        sig.filter_resonance,
        sig.alert_active,
    });
}
