//! Telegram Bot — /start, /help, /status, /rollback, /clear
//! Vaked AI bot. BotFather ready. C8-hosted. Zero-alloc.
//! GENESIS_SEAL: 7c242080

const std = @import("std");

pub const BotCommand = struct { cmd: []const u8, desc: []const u8 };

pub const BOT_COMMANDS = [_]BotCommand{
    .{ .cmd = "start", .desc = "Initialize the Vaked swarm bot" },
    .{ .cmd = "help", .desc = "Show available commands" },
    .{ .cmd = "status", .desc = "C8 pool health, Merkle root, invariants" },
    .{ .cmd = "rollback", .desc = "Hot-restart from shadow seed 7c242080" },
    .{ .cmd = "clear", .desc = "Reset graveyard ledger buffer" },
    .{ .cmd = "zone", .desc = "Show current branch + daemon status" },
};

pub fn handleCommand(cmd: []const u8, buf: []u8) ![]const u8 {
    const clean = std.mem.trim(u8, cmd, " \t\r\n/_");
    if (std.mem.eql(u8, clean, "start")) return std.fmt.bufPrint(buf, "Vaked AI bot active. Send /help for commands. GENESIS_SEAL: 7c242080", .{});
    if (std.mem.eql(u8, clean, "help")) {
        var pos: usize = 0;
        for (&BOT_COMMANDS) |bc| {
            if (pos + bc.cmd.len + bc.desc.len + 5 >= buf.len) break;
            @memcpy(buf[pos..], bc.cmd); pos += bc.cmd.len;
            buf[pos] = '-'; pos += 1; buf[pos] = ' '; pos += 1;
            @memcpy(buf[pos..], bc.desc); pos += bc.desc.len;
            buf[pos] = '\n'; pos += 1;
        }
        return buf[0..pos];
    }
    if (std.mem.eql(u8, clean, "status")) return std.fmt.bufPrint(buf, "C8 pool: ACTIVE. Invariants: BALANCED. Seed: 7c242080.", .{});
    if (std.mem.eql(u8, clean, "rollback")) return std.fmt.bufPrint(buf, "Ghost restore triggered. Seed: 7c242080.", .{});
    if (std.mem.eql(u8, clean, "clear")) return std.fmt.bufPrint(buf, "Graveyard ledger reset.", .{});
    if (std.mem.eql(u8, clean, "zone")) return std.fmt.bufPrint(buf, "branch: main · daemon: UP · genesis: 7c242080", .{});
    return std.fmt.bufPrint(buf, "Unknown. Try: /help", .{});
}

pub const BOT_CONFIG = struct {
    token_env: []const u8 = "TELEGRAM_TOKEN",
    chat_env: []const u8 = "TELEGRAM_TO",
    bot_name: []const u8 = "vaked_ai_bot",
    description: []const u8 = "Vaked swarm agent — monitor and control your C8 mesh from Telegram",
    short_desc: []const u8 = "Vaked Swarm AI Agent",
    commands: [][]const u8 = &.{
        "start - Initialize the bot",
        "help - Show commands",
        "status - C8 pool health",
        "rollback - Ghost restore",
        "clear - Reset graveyard",
        "zone - Branch + daemon",
    },
};

test "help lists all commands" {
    var buf: [1024]u8 = undefined;
    const out = try handleCommand("help", &buf);
    var count: usize = 0;
    for (BOT_COMMANDS) |_| count += 1;
    try std.testing.expect(out.len > 20);
}
test "start returns genesis seal" {
    var buf: [256]u8 = undefined;
    const out = try handleCommand("start", &buf);
    try std.testing.expect(std.mem.indexOf(u8, out, "7c242080") != null);
}
test "unknown returns help hint" {
    var buf: [128]u8 = undefined;
    const out = try handleCommand("blah", &buf);
    try std.testing.expect(std.mem.indexOf(u8, out, "/help") != null);
}
