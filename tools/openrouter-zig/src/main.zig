//! orcli — OpenRouter CLI in Zig. 1:1 with @vaked/openrouter-ts/src/cli.ts.
//! GENESIS_SEAL: 7c242080
const std = @import("std");
const root = @import("root.zig");
const models = @import("models.zig");
const budget = @import("budget.zig");

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const allocator = init.arena.allocator();
    const args = try init.minimal.args.toSlice(allocator);

    var model_alias: ?[]const u8 = null;
    var prompt_text: ?[]const u8 = null;
    var file_path: ?[]const u8 = null;
    var system_prompt: ?[]const u8 = null;
    var list_mode = false;
    var status_mode = false;
    var stream_mode = false;
    var help_mode = false;
    var max_tokens: u32 = 1000;

    var i: usize = 1;
    while (i < args.len) : (i += 1) {
        const arg = args[i];
        if (std.mem.eql(u8, arg, "-m") or std.mem.eql(u8, arg, "--model")) {
            i += 1; if (i < args.len) model_alias = args[i];
        } else if (std.mem.eql(u8, arg, "-f") or std.mem.eql(u8, arg, "--file")) {
            i += 1; if (i < args.len) file_path = args[i];
        } else if (std.mem.eql(u8, arg, "-p") or std.mem.eql(u8, arg, "--prompt")) {
            i += 1; if (i < args.len) system_prompt = args[i];
        } else if (std.mem.eql(u8, arg, "-t") or std.mem.eql(u8, arg, "--max-tokens")) {
            i += 1; if (i < args.len) max_tokens = try std.fmt.parseInt(u32, args[i], 10);
        } else if (std.mem.eql(u8, arg, "-s") or std.mem.eql(u8, arg, "--stream")) {
            stream_mode = true;
        } else if (std.mem.eql(u8, arg, "-l") or std.mem.eql(u8, arg, "--list")) {
            list_mode = true;
        } else if (std.mem.eql(u8, arg, "--status")) {
            status_mode = true;
        } else if (std.mem.eql(u8, arg, "-h") or std.mem.eql(u8, arg, "--help")) {
            help_mode = true;
        } else if (!std.mem.startsWith(u8, arg, "-")) {
            if (prompt_text == null) prompt_text = arg;
        }
    }

    if (help_mode) {
        std.debug.print(
            \\orcli — OpenRouter CLI (Zig). Supersedes @vaked/openrouter-ts.
            \\
            \\USAGE  orcli "prompt" | orcli -m claude -f file.txt "prompt"
            \\  -m, --model <alias>   deepseek, claude, gemini, qwen, llama, haiku
            \\  -f, --file <path>     Include file as context
            \\  -p, --prompt <text>   System prompt
            \\  -t, --max-tokens <n>  Max output tokens (default: 1000)
            \\  -s, --stream          Stream output
            \\  -l, --list            List models
            \\  --status              Budget status
            \\  -h, --help            This help
            \\
            \\GENESIS_SEAL: 7c242080
            \\
        , .{});
        return;
    }

    if (list_mode) {
        std.debug.print("Models:\n", .{});
        for (models.MODELS) |m| {
            std.debug.print("  {s}\n    {s}  ${d:.2}/${d:.2}/1M tok\n\n", .{ m.label, m.id, m.prompt_cost, m.completion_cost });
        }
        return;
    }

    if (status_mode) {
        const b = try budget.readBudget(io, allocator);
        const f = try budget.formatBudget(allocator, b);
        defer allocator.free(f);
        std.debug.print("{s}\n", .{f});
        return;
    }

    var user_prompt: []const u8 = "";
    if (file_path) |fp| {
        const fc = std.Io.Dir.cwd().readFileAlloc(io, fp, allocator, @enumFromInt(1024 * 1024)) catch {
            std.debug.print("Error: cannot read '{s}'\n", .{fp});
            return;
        };
        defer allocator.free(fc);
        user_prompt = try std.fmt.allocPrint(allocator, "File: {s}\n```\n{s}\n```\n\n{s}", .{ fp, fc, prompt_text orelse "" });
        defer allocator.free(user_prompt);
    } else if (prompt_text) |pt| {
        user_prompt = pt;
    } else {
        std.debug.print("Error: no prompt. Use positional arg or --file.\n", .{});
        return;
    }

    const model_id = if (model_alias) |alias|
        (models.resolveModel(alias) orelse models.ModelEntry{
            .id = alias, .label = alias, .prompt_cost = 0, .completion_cost = 0,
        }).id
    else
        "deepseek/deepseek-v4-pro";

    var agent = root.VakedAgent.init(allocator, io, .{ .default_model = model_id, .context7 = false, .langfuse = false }) catch {
        std.debug.print("Error: OPENROUTER_API_KEY not set\n", .{});
        return;
    };
    defer agent.deinit();

    const result = agent.askWithModel(user_prompt, model_id, max_tokens) catch {
        std.debug.print("Error: API call failed\n", .{});
        return;
    };
    std.debug.print("{s}\n", .{result});

    const b = try budget.readBudget(io, allocator);
    const f = try budget.formatBudget(allocator, b);
    defer allocator.free(f);
    std.debug.print("\n── {s} · {s}\n", .{ model_id, f });
}
