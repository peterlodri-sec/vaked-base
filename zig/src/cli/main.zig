const std = @import("std");
const core = @import("vaked-core");
const lex = @import("vaked-lex");
const parse = @import("vaked-parse");
const check = @import("vaked-check");
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

    if (std.mem.eql(u8, cmd, "check")) {
        std.process.exit(try cmdCheck(io, alloc, argv[0], argv[2..]));
    }

    // Other subcommands (lower) land in later phases.
    try writeStderr(io, "vakedc: not yet implemented\n");
    std.process.exit(2);
}

/// `vakedc check <file> [--json] [--builtins PATH]`.
///
/// Mirrors `vakedc/__main__.py:_cmd_check` branch-for-branch. Exit codes:
///   * 0  — no diagnostics
///   * 1  — diagnostics present
///   * 2  — usage / read / builtins / lex / parse error
/// With `--json` the canonical diagnostics doc goes to stdout (the oracle gate).
/// The non-`--json` human path writes only to stderr (stdout stays empty).
fn cmdCheck(io: Io, alloc: std.mem.Allocator, prog: []const u8, args: []const [:0]const u8) !u8 {
    var file: ?[]const u8 = null;
    var json: bool = false;
    var builtins_override: ?[]const u8 = null;
    var i: usize = 0;
    while (i < args.len) : (i += 1) {
        const a = args[i];
        if (std.mem.eql(u8, a, "--json")) {
            json = true;
        } else if (std.mem.eql(u8, a, "--builtins")) {
            if (i + 1 >= args.len) {
                try writeStderr(io, "usage: vakedc check <file> [--json] [--builtins PATH]\n");
                return 2;
            }
            i += 1;
            builtins_override = args[i];
        } else if (a.len >= 1 and a[0] == '-') {
            try writeStderrFmt(io, alloc, "vakedc: unknown option {s}\n", .{a});
            return 2;
        } else if (file == null) {
            file = a;
        } else {
            try writeStderr(io, "usage: vakedc check <file> [--json] [--builtins PATH]\n");
            return 2;
        }
    }
    const path = file orelse {
        try writeStderr(io, "usage: vakedc check <file> [--json] [--builtins PATH]\n");
        return 2;
    };

    // 1) read the source under check. On read error: stderr message, exit 2
    //    (Python: `except OSError: return 2`).
    const src = Dir.cwd().readFileAlloc(io, path, alloc, .unlimited) catch {
        try writeStderrFmt(io, alloc, "vakedc: cannot read {s}\n", .{path});
        return 2;
    };

    // 2) resolve + read the builtins catalog. Read error: stderr, exit 2
    //    (Python: `except OSError: return 2`).
    const b_path = builtins_override orelse defaultBuiltinsPath(io, alloc, prog);
    const b_src = Dir.cwd().readFileAlloc(io, b_path, alloc, .unlimited) catch {
        try writeStderrFmt(io, alloc, "vakedc: cannot read builtins {s}\n", .{b_path});
        return 2;
    };

    // 3) parse the builtins catalog. Parse failure: exit 2 (Python:
    //    `except (VakedLexError, VakedSyntaxError): return 2`).
    const builtins = check.loadBuiltins(alloc, b_src, b_path) catch |e| switch (e) {
        error.OutOfMemory => return e,
        error.ParseFailed => {
            try writeStderr(io, "vakedc: builtins catalog failed to parse\n");
            return 2;
        },
    };

    // 4) check. A lex/parse error on the file under check: exit 2 (Python:
    //    `except (VakedLexError, VakedSyntaxError): return 2`).
    const diags = check.checkSource(alloc, src, path, builtins) catch |e| switch (e) {
        error.OutOfMemory => return e,
        error.ParseFailed => {
            try writeStderrFmt(io, alloc, "vakedc: {s}: parse error\n", .{path});
            return 2;
        },
    };

    if (json) {
        const out = try core.diagnosticsDocToCanonical(alloc, diags);
        try File.stdout().writeStreamingAll(io, out);
    } else {
        // Human path: stderr only (stdout stays empty so it never pollutes the
        // gated channel). Minimal per the task brief.
        if (diags.len == 0) {
            try writeStderrFmt(io, alloc, "vakedc: {s} — no diagnostics\n", .{path});
        } else {
            try writeStderrFmt(io, alloc, "vakedc: {d} diagnostic(s) in {s}\n", .{ diags.len, path });
        }
    }

    return if (diags.len != 0) 1 else 0;
}

/// `default_builtins_path` — resolve the catalog. Prefer exe-relative
/// (`<exe_dir>/../../../vaked/schema/builtins.vaked`, mirroring the layout
/// `zig/zig-out/bin/vakedc` → repo root), falling back to CWD-relative
/// `vaked/schema/builtins.vaked` (the oracle runs from repo root, so this
/// fallback is what matches Python's package-relative resolution byte-for-byte).
fn defaultBuiltinsPath(io: Io, alloc: std.mem.Allocator, prog: []const u8) []const u8 {
    const cwd_rel = "vaked/schema/builtins.vaked";
    // Try exe-relative first: <dir(prog)>/../../../vaked/schema/builtins.vaked.
    if (std.fs.path.dirname(prog)) |bin_dir| {
        const cand = std.fs.path.join(alloc, &.{ bin_dir, "..", "..", "..", "vaked", "schema", "builtins.vaked" }) catch return cwd_rel;
        // existence check via a stat-like open; if it reads, use it.
        if (Dir.cwd().readFileAlloc(io, cand, alloc, .unlimited)) |_| {
            return cand;
        } else |_| {}
    }
    return cwd_rel;
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
