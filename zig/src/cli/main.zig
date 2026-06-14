const std = @import("std");
const core = @import("vaked-core");
const lex = @import("vaked-lex");
const parse = @import("vaked-parse");
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

    if (std.mem.eql(u8, cmd, "parse")) {
        std.process.exit(try cmdParse(io, alloc, argv[2..]));
    }

    // Other subcommands (check/lower) land in later phases.
    try writeStderr(io, "vakedc: not yet implemented\n");
    std.process.exit(2);
}

/// `vakedc parse <file> [--json PATH] [--sqlite PATH] [--print]`.
///
/// Mirrors `vakedc/__main__.py:_cmd_parse` for the oracle-gated path: lex →
/// parse → build_graph → canonical JSON. With `--print` the canonical JSON is
/// written to stdout. Exit codes: 0 ok; 1 on read/lex/parse error (message to
/// stderr, stdout stays empty) — matching Python (the Unicode-version warning
/// also goes to stderr so stdout is clean). The default `.vaked/` file writes
/// and `--sqlite` emit are NOT oracle-gated and are out of scope here; we accept
/// the flags so arg parsing doesn't break, but only `--print` produces output.
fn cmdParse(io: Io, alloc: std.mem.Allocator, args: []const [:0]const u8) !u8 {
    var file: ?[]const u8 = null;
    var print_: bool = false;
    var i: usize = 0;
    while (i < args.len) : (i += 1) {
        const a = args[i];
        if (std.mem.eql(u8, a, "--print")) {
            print_ = true;
        } else if (std.mem.eql(u8, a, "--json") or std.mem.eql(u8, a, "--sqlite")) {
            // flag takes a PATH value; skip it (not gated, not emitted here).
            i += 1;
        } else if (a.len >= 1 and a[0] == '-') {
            try writeStderrFmt(io, alloc, "vakedc: unknown option {s}\n", .{a});
            return 2;
        } else if (file == null) {
            file = a;
        } else {
            try writeStderr(io, "usage: vakedc parse <file> [--json PATH] [--sqlite PATH] [--print]\n");
            return 2;
        }
    }
    const path = file orelse {
        try writeStderr(io, "usage: vakedc parse <file> [--json PATH] [--sqlite PATH] [--print]\n");
        return 2;
    };

    // Read the file. On read error, match Python: message to stderr, exit 1.
    const src = Dir.cwd().readFileAlloc(io, path, alloc, .unlimited) catch {
        try writeStderrFmt(io, alloc, "vakedc: cannot read {s}\n", .{path});
        return 1;
    };

    // Unicode-version-mismatch warning to stderr (parity; stderr is ungated).
    lexer.maybeWarnUnicodeVersion(io);

    // lex
    var lex_err: lexer.ErrInfo = undefined;
    const toks = lexer.tokenize(alloc, src, path, &lex_err) catch |e| switch (e) {
        error.LexFailed => {
            try writeStderrFmt(io, alloc, "vakedc: {s}:{d}:{d} \u{2014} {s}\n", .{
                lex_err.file, lex_err.line, lex_err.col, lex_err.msg,
            });
            return 1;
        },
        error.OutOfMemory => return e,
    };

    // parse
    var parse_err: parse.ErrInfo = undefined;
    const items = parse.parse(alloc, toks, path, &parse_err) catch |e| switch (e) {
        error.ParseFailed => {
            try writeStderrFmt(io, alloc, "vakedc: {s}:{d}:{d} \u{2014} expected {s}, got {s}\n", .{
                parse_err.file, parse_err.line, parse_err.col, parse_err.expected, parse_err.got,
            });
            return 1;
        },
        error.OutOfMemory => return e,
    };

    // resolve -> Graph (source_file = the path as given, matching Python).
    var graph = core.Graph.init(alloc, path);
    var unserializable = false;
    parse.buildGraph(alloc, &graph, items, path, &unserializable) catch |e| switch (e) {
        error.Unserializable => {
            // Python builds the graph but crashes in json.dumps on a non-
            // serializable Literal/ListLit left by a `default`/`oneof` field
            // refinement: empty stdout, exit 1. Reproduce that exactly.
            return 1;
        },
        error.OutOfMemory => return e,
    };

    const canonical = try json_canon.graphToCanonical(alloc, &graph);

    if (print_) {
        try File.stdout().writeStreamingAll(io, canonical);
    }
    // The default `.vaked/` file writes (when no flags given) are a Python side
    // effect the oracle does not read; we intentionally omit them (and SQLite).
    return 0;
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
