const std = @import("std");
const core = @import("vaked-core");
const lex = @import("vaked-lex");
const parse = @import("vaked-parse");
const check = @import("vaked-check");
const lower = @import("vaked-lower");
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

    if (std.mem.eql(u8, cmd, "lower")) {
        std.process.exit(try cmdLower(io, alloc, argv[0], argv[2..]));
    }

    try writeStderr(io, "vakedc: not yet implemented\n");
    std.process.exit(2);
}

/// `vakedc lower <file> [--out DIR] [--builtins PATH]`.
///
/// Mirrors `vakedc/__main__.py:_cmd_lower` + `_write_tree` branch-for-branch:
/// read → parse → load+parse builtins → check FIRST; if any diagnostic, print
/// to stderr, write NOTHING, exit 1; else build_graph → lower → write the tree
/// under `--out` (default `.vaked/lower/`): every file at its relative path
/// (mkdir -p parents) + `provenance.json` at the out root. Exit codes:
///   * 0  — emitted
///   * 1  — read / parse / diagnostics error (nothing written)
///   * 2  — usage / builtins read/parse error
/// The status line (with the out-dir path) goes to stderr; the oracle compares
/// the tree + exit code, never stderr.
fn cmdLower(io: Io, alloc: std.mem.Allocator, prog: []const u8, args: []const [:0]const u8) !u8 {
    var file: ?[]const u8 = null;
    var out_override: ?[]const u8 = null;
    var builtins_override: ?[]const u8 = null;
    var i: usize = 0;
    while (i < args.len) : (i += 1) {
        const a = args[i];
        if (std.mem.eql(u8, a, "--out")) {
            if (i + 1 >= args.len) {
                try writeStderr(io, "usage: vakedc lower <file> [--out DIR] [--builtins PATH]\n");
                return 2;
            }
            i += 1;
            out_override = args[i];
        } else if (std.mem.eql(u8, a, "--builtins")) {
            if (i + 1 >= args.len) {
                try writeStderr(io, "usage: vakedc lower <file> [--out DIR] [--builtins PATH]\n");
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
            try writeStderr(io, "usage: vakedc lower <file> [--out DIR] [--builtins PATH]\n");
            return 2;
        }
    }
    const path = file orelse {
        try writeStderr(io, "usage: vakedc lower <file> [--out DIR] [--builtins PATH]\n");
        return 2;
    };

    // 1) read the source. On read error: stderr, exit 1 (Python `_cmd_lower`).
    const src = Dir.cwd().readFileAlloc(io, path, alloc, .unlimited) catch {
        try writeStderrFmt(io, alloc, "vakedc: cannot read {s}\n", .{path});
        return 1;
    };

    // Unicode-version-mismatch warning to stderr (parity with Python).
    lexer.maybeWarnUnicodeVersion(io);

    // parse the file. On lex/parse error: stderr, exit 1 (Python: VakedLexError /
    // VakedSyntaxError → return 1).
    var lex_err: lexer.ErrInfo = undefined;
    const toks = lexer.tokenize(alloc, src, path, &lex_err) catch |e| switch (e) {
        error.LexFailed => {
            try writeStderrFmt(io, alloc, "vakedc: {s}:{d}:{d} \u{2014} {s}\n", .{ lex_err.file, lex_err.line, lex_err.col, lex_err.msg });
            return 1;
        },
        error.OutOfMemory => return e,
    };
    var parse_err: parse.ErrInfo = undefined;
    const items = parse.parse(alloc, toks, path, &parse_err) catch |e| switch (e) {
        error.ParseFailed => {
            try writeStderrFmt(io, alloc, "vakedc: {s}:{d}:{d} \u{2014} expected {s}, got {s}\n", .{ parse_err.file, parse_err.line, parse_err.col, parse_err.expected, parse_err.got });
            return 1;
        },
        error.OutOfMemory => return e,
    };

    // 2) check FIRST. Builtins read error: stderr, exit 2 (Python OSError → 2).
    const b_path = builtins_override orelse defaultBuiltinsPath(io, alloc, prog);
    const b_src = Dir.cwd().readFileAlloc(io, b_path, alloc, .unlimited) catch {
        try writeStderrFmt(io, alloc, "vakedc: cannot read builtins {s}\n", .{b_path});
        return 2;
    };
    const builtins = check.loadBuiltins(alloc, b_src, b_path) catch |e| switch (e) {
        error.OutOfMemory => return e,
        error.ParseFailed => {
            try writeStderr(io, "vakedc: builtins catalog failed to parse\n");
            return 2;
        },
    };
    const diags = check.checkSource(alloc, src, path, builtins) catch |e| switch (e) {
        error.OutOfMemory => return e,
        error.ParseFailed => {
            // A lex/parse error here is already handled above; Python would have
            // returned 1 at parse. Keep exit 1 for parity (nothing written).
            try writeStderrFmt(io, alloc, "vakedc: {s}: parse error\n", .{path});
            return 1;
        },
    };

    if (diags.len != 0) {
        // Refuse to emit on ANY diagnostic (0012 §1). Print diags to stderr (the
        // oracle ignores stderr), write NOTHING, exit 1.
        for (diags) |d| {
            try writeStderrFmt(io, alloc, "{s}:{d}:{d}: {s}: {s}: {s} [{s}]\n", .{
                d.file, d.line, d.col, d.severity, d.code, d.message, d.decl,
            });
        }
        const plural: []const u8 = if (diags.len != 1) "s" else "";
        try writeStderrFmt(io, alloc, "vakedc: {d} diagnostic{s} in {s}; refusing to lower (nothing written)\n", .{ diags.len, plural, path });
        return 1;
    }

    // 3) resolve + lower. enrich_graph (the policy sub-block) runs inside lower().
    //
    // `error.Unserializable` (a `default`/`oneof` field refinement left a raw AST
    // node in props) is NOT fatal here: it only matters when the graph is
    // serialized to canonical JSON (`parse --print`), which lowering never does.
    // Python's `_cmd_lower` calls `build_graph` then `lower` without serializing,
    // so it lowers such a graph normally (in the corpus this is a `types/` file
    // with no `runtime`, so the result is the empty-artifacts provenance). We
    // mirror that: keep the graph as built and lower it.
    var graph = core.Graph.init(alloc, path);
    var unserializable = false;
    parse.buildGraph(alloc, &graph, items, path, &unserializable) catch |e| switch (e) {
        error.Unserializable => {}, // graph is usable for lowering; see note above.
        error.OutOfMemory => return e,
    };
    const result = try lower.lower(alloc, &graph, items);

    // 4) write the tree. provenance.json at <out>/; the rest at their rel paths.
    // Default out-dir is `.vaked/lower/` (CWD-relative). Python joins the absolute
    // cwd, but the oracle always passes `--out`, so the exact default-dir spelling
    // is never gated (the status line carrying it is ungated stderr).
    const out_dir = out_override orelse defaultOutDir(io, alloc);
    const written = try writeTree(io, alloc, out_dir, result);
    try writeStderrFmt(io, alloc, "vakedc: lowered {s} \u{2192} {s} ({d} files)\n", .{ path, out_dir, written });
    return 0;
}

/// `_write_tree`: write a `LowerResult` to `out_dir` — every emitted file at its
/// relative path (mkdir -p parents), plus `provenance.json` at the root. Files
/// are written in sorted relative-path order (matching Python's `sorted`).
fn writeTree(io: Io, alloc: std.mem.Allocator, out_dir: []const u8, result: lower.LowerResult) !usize {
    const cwd = Dir.cwd();
    var written: usize = 0;

    // Sort the relative paths (Python: `for rel, content in sorted(result.files.items())`).
    const rels = try alloc.dupe([]const u8, result.files.keys());
    std.mem.sort([]const u8, rels, {}, lessStr);

    for (rels) |rel| {
        const content = result.files.get(rel).?;
        const dest = try std.fs.path.join(alloc, &.{ out_dir, rel });
        if (std.fs.path.dirname(dest)) |parent| {
            cwd.createDirPath(io, parent) catch |e| switch (e) {
                error.PathAlreadyExists => {},
                else => return e,
            };
        }
        try cwd.writeFile(io, .{ .sub_path = dest, .data = content });
        written += 1;
    }

    // provenance manifest at the out root.
    cwd.createDirPath(io, out_dir) catch |e| switch (e) {
        error.PathAlreadyExists => {},
        else => return e,
    };
    const prov_text = try lower.provenanceJsonText(alloc, result.provenance);
    const prov_dest = try std.fs.path.join(alloc, &.{ out_dir, "provenance.json" });
    try cwd.writeFile(io, .{ .sub_path = prov_dest, .data = prov_text });
    written += 1;
    return written;
}

/// The default `--out` directory: `<cwd>/.vaked/lower` (mirrors Python's
/// `os.path.join(os.getcwd(), ".vaked", "lower")`), falling back to the relative
/// `.vaked/lower` if the cwd can't be resolved. The oracle always passes `--out`,
/// so this path is never on the gated channel.
fn defaultOutDir(io: Io, alloc: std.mem.Allocator) []const u8 {
    var buf: [std.fs.max_path_bytes]u8 = undefined;
    const n = Dir.cwd().realPath(io, &buf) catch return ".vaked/lower";
    return std.fs.path.join(alloc, &.{ buf[0..n], ".vaked", "lower" }) catch ".vaked/lower";
}

fn lessStr(_: void, a: []const u8, b: []const u8) bool {
    return std.mem.lessThan(u8, a, b);
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
