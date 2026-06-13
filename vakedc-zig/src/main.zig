const std = @import("std");
const lexer = @import("lexer.zig");
const parser = @import("parser.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    const argv = try std.process.argsAlloc(allocator);
    defer std.process.argsFree(allocator, argv);

    if (argv.len < 2) {
        try std.io.getStdErr().writeAll(
            "usage: vakedc-zig <command> <file> [--print]\n" ++
            "  parse    - parse a .vaked file into LPG (JSON)\n" ++
            "  lex      - emit token stream (debug)\n" ++
            "  parse-ast - emit AST (debug)\n"
        );
        return;
    }

    const command = argv[1];

    if (std.mem.eql(u8, command, "parse")) {
        if (argv.len < 3) {
            try std.io.getStdErr().writeAll("vakedc-zig: parse requires a filename\n");
            return;
        }
        try cmdParse(allocator, argv[2], argv);
    } else if (std.mem.eql(u8, command, "lex")) {
        if (argv.len < 3) {
            try std.io.getStdErr().writeAll("vakedc-zig: lex requires a filename\n");
            return;
        }
        try cmdLex(allocator, argv[2]);
    } else if (std.mem.eql(u8, command, "parse-ast")) {
        if (argv.len < 3) {
            try std.io.getStdErr().writeAll("vakedc-zig: parse-ast requires a filename\n");
            return;
        }
        try cmdParseAst(allocator, argv[2]);
    } else {
        try std.io.getStdErr().writeAll("vakedc-zig: unknown command\n");
        return;
    }
}

fn cmdParse(allocator: std.mem.Allocator, filename: []const u8, argv: [][]const u8) !void {
    // Check for --print flag
    var print_to_stdout = false;
    for (argv[3..]) |arg| {
        if (std.mem.eql(u8, arg, "--print")) {
            print_to_stdout = true;
            break;
        }
    }

    // Read source file
    const file = try std.fs.cwd().openFile(filename, .{});
    defer file.close();
    const source = try file.readToEndAlloc(allocator, 1024 * 1024);
    defer allocator.free(source);

    // Lex
    var lex = try lexer.Lexer.init(allocator, source);
    defer lex.deinit();
    try lex.tokenize();

    // Parse
    var p = try parser.Parser.init(allocator, &lex);
    defer p.deinit();
    const items = try p.parseFile();

    // For now, just emit a placeholder JSON
    const stderr = std.io.getStdErr().writer();
    try stderr.print("vakedc-zig: parsed {d} items from {s}\n", .{ items.len, filename });

    if (print_to_stdout) {
        const stdout = std.io.getStdOut().writer();
        try stdout.writeAll("{}\n");
    }
}

fn cmdLex(allocator: std.mem.Allocator, filename: []const u8) !void {
    const file = try std.fs.cwd().openFile(filename, .{});
    defer file.close();
    const source = try file.readToEndAlloc(allocator, 1024 * 1024);
    defer allocator.free(source);

    var lex = try lexer.Lexer.init(allocator, source);
    defer lex.deinit();
    try lex.tokenize();

    const stdout = std.io.getStdOut().writer();
    try stdout.print("Tokens: {d}\n", .{lex.tokens.items.len});
    for (lex.tokens.items) |token| {
        try stdout.print("  {s}: {s}\n", .{ @tagName(token.kind), token.value });
    }
}

fn cmdParseAst(allocator: std.mem.Allocator, filename: []const u8) !void {
    const file = try std.fs.cwd().openFile(filename, .{});
    defer file.close();
    const source = try file.readToEndAlloc(allocator, 1024 * 1024);
    defer allocator.free(source);

    var lex = try lexer.Lexer.init(allocator, source);
    defer lex.deinit();
    try lex.tokenize();

    var p = try parser.Parser.init(allocator, &lex);
    defer p.deinit();
    const items = try p.parseFile();

    const stdout = std.io.getStdOut().writer();
    try stdout.print("AST: {d} top-level items\n", .{items.len});
}
