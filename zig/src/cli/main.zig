const std = @import("std");
const core = @import("vaked-core");
const lex = @import("vaked-lex");
const lexer = lex.lexer;
const json_canon = core.json_canon;
const Io = std.Io;
const File = std.Io.File;
const Dir = std.Io.Dir;

/// Exit code convention mirrors `vakedc/__main__.py`: 0 ok, 1 read/lex error,
/// 2 usage error.
///
/// Zig 0.16 passes args/env/io via the `process.Init` parameter (the old
/// `std.process.argsAlloc` + `std.io.getStdOut` are gone). We take `Init` so we
/// get a ready arena allocator and an `Io` for stdout/stderr and file reads.
pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const alloc = init.arena.allocator();

    const argv = try init.minimal.args.toSlice(alloc);
    // argv[0] = program; argv[1] = subcommand; argv[2..] = args.
    if (argv.len < 2) {
        try writeStderr(io, "vakedc: missing subcommand\n");
        std.process.exit(2);
    }
    const cmd = argv[1];

    if (std.mem.eql(u8, cmd, "lex")) {
        if (argv.len != 3) {
            try writeStderr(io, "usage: vakedc lex <file>\n");
            std.process.exit(2);
        }
        std.process.exit(try cmdLex(io, alloc, argv[2]));
    }

    // Other subcommands (parse/check/lower) land in later phases.
    try writeStderr(io, "vakedc: not yet implemented\n");
    std.process.exit(2);
}

fn cmdLex(io: Io, alloc: std.mem.Allocator, file: []const u8) !u8 {
    // Read the whole file. On read error, match Python: message to stderr, exit 1.
    const src = Dir.cwd().readFileAlloc(io, file, alloc, .unlimited) catch {
        try writeStderrFmt(io, alloc, "vakedc: cannot read {s}\n", .{file});
        return 1;
    };

    // Emit the pinned-Unicode-version-mismatch warning to stderr (parity with
    // Python; stderr is ungated). Mirrors `tokenize`'s first action in Python.
    lexer.maybeWarnUnicodeVersion(io);

    var err_info: lexer.ErrInfo = undefined;
    const toks = lexer.tokenize(alloc, src, file, &err_info) catch |e| switch (e) {
        error.LexFailed => {
            // Match VakedLexError formatting: "vakedc: file:line:col — msg".
            try writeStderrFmt(io, alloc, "vakedc: {s}:{d}:{d} \u{2014} {s}\n", .{
                err_info.file, err_info.line, err_info.col, err_info.msg,
            });
            return 1;
        },
        error.OutOfMemory => return e,
    };

    // Build the TAB-separated token dump into a buffer, then write it to stdout.
    var buf: std.ArrayList(u8) = .empty;
    defer buf.deinit(alloc);
    for (toks) |t| {
        try buf.appendSlice(alloc, t.kind.name());
        try buf.append(alloc, '\t');
        try appendInt(&buf, alloc, t.byteStart);
        try buf.append(alloc, '\t');
        try appendInt(&buf, alloc, t.byteEnd);
        try buf.append(alloc, '\t');
        try appendInt(&buf, alloc, t.line);
        try buf.append(alloc, '\t');
        try appendInt(&buf, alloc, t.col);
        try buf.append(alloc, '\t');
        try json_canon.writeJsonStringRaw(&buf, alloc, t.value);
        try buf.append(alloc, '\n');
    }

    try File.stdout().writeStreamingAll(io, buf.items);
    return 0;
}

fn appendInt(buf: *std.ArrayList(u8), alloc: std.mem.Allocator, n: usize) !void {
    var tmp: [24]u8 = undefined;
    try buf.appendSlice(alloc, try std.fmt.bufPrint(&tmp, "{d}", .{n}));
}

fn writeStderr(io: Io, bytes: []const u8) !void {
    try File.stderr().writeStreamingAll(io, bytes);
}

fn writeStderrFmt(io: Io, alloc: std.mem.Allocator, comptime fmt: []const u8, args: anytype) !void {
    const s = try std.fmt.allocPrint(alloc, fmt, args);
    try writeStderr(io, s);
}

comptime {
    std.debug.assert(@hasDecl(core, "Span"));
}
