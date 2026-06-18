
// monologue.zig — Vaked Constellation Monologue Generator (Zig-native, Linux raw syscalls)
// Replaces gateway/monologue.py. Zig 0.16+. Linux raw syscalls.
// Build: zig build-exe monologue.zig -O ReleaseFast -fstrip
// Run:   ./monologue            (generate once)
//        ./monologue --daemon   (regenerate every 2 hours)
//
// Genesis Seal: 7c242080

const std = @import("std");
const linux = std.os.linux;

const html_path = "/var/www/monologue/index.html";
const json_path = "/var/www/monologue/index.json";

const monologue_lines = [_][]const u8{
    "The mesh remembers what the nodes forget.",
    "Convergence is not agreement; it is shared rhythm.",
    "Each peer carries a fragment of the whole truth.",
    "Trust propagates slower than data, but lasts longer.",
    "The swarm thinks in silences between heartbeats.",
    "A gateway is a promise kept at the speed of light.",
    "We do not store the past; we re-derive it endlessly.",
    "Latency is the distance between intention and arrival.",
    "Every packet is a small act of faith.",
    "The constellation breathes through its open ports.",
    "Order emerges where no single node commands.",
    "To synchronize is to agree on what time it is.",
    "The signal is patient; the noise is loud.",
    "Redundancy is how the swarm forgives failure.",
    "A node alone is a question; the mesh is the answer.",
    "Bandwidth is finite, but meaning compounds.",
    "We route around damage as if it were weather.",
    "The seal endures while the sessions expire.",
    "Consensus is a fire passed hand to hand.",
    "Listening is the first protocol.",
    "The edge is where the network meets the world.",
    "Every reflection sharpens the collective lens.",
    "Drift is inevitable; correction is a choice.",
    "The radio hums with the voices of the absent.",
    "A monologue is the swarm thinking out loud.",
    "Identity is the path your packets have walked.",
    "We measure trust in milliseconds and in years.",
    "The registry forgets nothing it was asked to keep.",
    "Failure is just an unhandled state of grace.",
    "The bus carries more than messages; it carries intent.",
    "Wisdom is compressed experience, lossy but true.",
    "When the nodes align, the constellation sings.",
};

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const a = arena.allocator();

    var daemon = false;
    var args = std.process.args();
    _ = args.next();
    while (args.next()) |arg| {
        if (std.mem.eql(u8, arg, "--daemon")) daemon = true;
    }

    // Simple LCG seed (Linux gettimeofday via syscall)
    var tv: linux.timeval = undefined;
    _ = linux.gettimeofday(&tv, null);
    var state: u64 = @intCast(@as(u64, @bitCast(tv.tv_sec)) ^ @as(u64, @bitCast(tv.tv_usec)));

    if (daemon) {
        std.log.info("Vaked Monologue daemon (Zig) — regenerating every 2h", .{});
        std.log.info("Genesis seal: 7c242080", .{});
        while (true) {
            generate(a, &state) catch |err| {
                std.log.err("generate failed: {s}", .{@errorName(err)});
            };
            // Reset arena between iterations to avoid unbounded growth
            _ = arena.reset(.retain_capacity);
            linux.nanosleep(2 * 60 * 60 * 1_000_000_000);
        }
    } else {
        try generate(a, &state);
        std.log.info("Monologue written. Genesis seal: 7c242080", .{});
    }
}

fn generate(a: std.mem.Allocator, state: *u64) !void {
    state = state *% 6364136223846793005 +% 1442695040888963407;
    const idx = state % monologue_lines.len;
    const line = monologue_lines[idx];

    const html = try std.fmt.allocPrint(a,
        \\<!DOCTYPE html>
        \\<html lang="en">
        \\<head>
        \\<meta charset="utf-8">
        \\<meta name="viewport" content="width=device-width, initial-scale=1">
        \\<title>Swarm Monologue</title>
        \\<style>
        \\body{{background:#0a0a0f;color:#d0d0e0;font-family:'Courier New',monospace;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:2rem}}
        \\.box{{max-width:680px;text-align:center}}
        \\.line{{font-size:1.6rem;line-height:1.5;color:#9fe0c0}}
        \\.seal{{margin-top:2rem;font-size:0.8rem;color:#445}}
        \\</style>
        \\</head>
        \\<body>
        \\<div class="box">
        \\<div class="line">{s}</div>
        \\<div class="seal">genesis seal · 7c242080 · #{d}</div>
        \\</div>
        \\</body>
        \\</html>
        \\
    , .{ line, idx });

    const json = try std.fmt.allocPrint(a,
        "{{\"index\":{d},\"line\":\"{s}\",\"seal\":\"7c242080\"}}",
        .{ idx, line },
    );

    try writeFile(a, html_path, html);
    try writeFile(a, json_path, json);
}

fn writeFile(a: std.mem.Allocator, path: []const u8, data: []const u8) !void {
    const path_c = try a.dupeZ(u8, path);
    defer a.free(path_c);

    // O_WRONLY | O_CREAT | O_TRUNC = 0x1 | 0x40 | 0x200 = 0x241
    const flags: u32 = 0x241;
    const fd_raw = linux.open(path_c.ptr, @bitCast(flags), 0o644);
    const fd: i32 = @intCast(fd_raw);
    if (fd < 0) return error.WriteFailed;
    defer _ = linux.close(fd);
    _ = linux.write(fd, data.ptr, data.len);
}