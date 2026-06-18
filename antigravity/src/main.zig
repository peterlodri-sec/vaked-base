const std = @import("std");
const linux = std.os.linux;
const graph = @import("graph.zig");
const eexport = @import("export.zig");

const GENESIS = "7c242080";
const usage =
    \\ag init                      Initialize workspace
    \\ag declare node|edge|trust   Declare graph element  
    \\ag link <from> <to>          Connect nodes
    \\ag status                    Show graph
    \\ag push                      Emit .vaked
    \\ag seal                      Sign with Genesis
;

pub fn main(init: std.process.Init) !void {
    const a = init.arena.allocator();
    const args = try init.minimal.args.toSlice(a);
    if (args.len < 2) { std.debug.print("{s}", .{usage}); return; }

    var g = graph.Graph.init(a);
    g.loadFromFile(a) catch {};
    // Override "init" to not write empty if file already created
    // Load existing graph from .ag/graph.json

    const cmd = args[1];

    if (std.mem.eql(u8, cmd, "init")) {
        try initWorkspace(a);
        std.debug.print("[antigravity] initialized · genesis {s}\n", .{GENESIS});
    } else if (std.mem.eql(u8, cmd, "declare")) {
        if (args.len < 4) { std.debug.print("[antigravity] usage: declare node|edge|trust <name>\n", .{}); return; }
        try g.addNode(args[3], args[2]);
        try g.saveToFile(a);
        std.debug.print("[antigravity] declared {s} {s}\n", .{args[2], args[3]});
    } else if (std.mem.eql(u8, cmd, "link")) {
        if (args.len < 4) { std.debug.print("[antigravity] usage: link <from> <to>\n", .{}); return; }
        try g.addEdge(args[2], args[3], 0.95);
        try g.saveToFile(a);
        std.debug.print("[antigravity] linked {s} → {s}\n", .{args[2], args[3]});
    } else if (std.mem.eql(u8, cmd, "status")) {
        const json = try g.toJson(a);
        std.debug.print("{s}\n", .{json});
    } else if (std.mem.eql(u8, cmd, "push")) {
        const vaked = try eexport.toVaked(a, g);
        std.debug.print("{s}\n", .{vaked});
    } else if (std.mem.eql(u8, cmd, "seal")) {
        _ = try eexport.sealSignature(a);
        std.debug.print("[antigravity] sealed with genesis {s}\n", .{GENESIS});
    } else {
        std.debug.print("[antigravity] unknown: {s}\n", .{cmd});
        std.process.exit(1);
    }
}

fn initWorkspace(a: std.mem.Allocator) !void {
    const path = a.dupeZ(u8, ".ag") catch return;
    _ = linux.mkdir(path, 0o755);
    const fpath = a.dupeZ(u8, ".ag/graph.json") catch return;
    const fd = linux.open(fpath, @bitCast(@as(u32, 0x241)), 0o644);
    const fdi: i32 = @intCast(fd);
    defer _ = linux.close(fdi);
    const data = "{}";
    _ = linux.write(fdi, data.ptr, data.len);
}
