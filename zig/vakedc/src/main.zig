const std = @import("std");
const ast = @import("ast.zig");
const lexer = @import("lexer.zig");
const parser = @import("parser.zig");
const cache_mod = @import("cache.zig");
const build_options = @import("build_options");
const Io = std.Io;

const Sha256 = std.crypto.hash.sha2.Sha256;

// ---- Usage ------------------------------------------------------------------
// vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>

pub fn main(init: std.process.Init) !void {
    const alloc = init.arena.allocator();
    const io = init.io;

    const argv_z = try init.minimal.args.toSlice(alloc);
    const argv = try alloc.alloc([]const u8, argv_z.len);
    for (argv_z, 0..) |s, i| argv[i] = s;

    // argv[0] = program name; argv[1] = subcommand; argv[2..] = flags/args
    if (argv.len < 2) {
        std.debug.print("usage: vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>\n", .{});
        std.process.exit(2);
    }

    const subcmd = argv[1];

    if (std.mem.eql(u8, subcmd, "--version")) {
        var ver_buf: [64]u8 = undefined;
        const ver = try std.fmt.bufPrint(&ver_buf, "vakedc-zig {s}\n", .{build_options.version});
        try stdoutWrite(io, ver);
        return;
    }
    if (!std.mem.eql(u8, subcmd, "parse")) {
        std.debug.print("vakedc-zig: unknown subcommand '{s}'\n", .{subcmd});
        std.debug.print("usage: vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>\n", .{});
        std.process.exit(2);
    }

    var cache_dir_arg: ?[]const u8 = null;
    var no_cache = false;
    var file_arg: ?[]const u8 = null;

    var idx: usize = 2;
    while (idx < argv.len) : (idx += 1) {
        const arg = argv[idx];
        if (std.mem.eql(u8, arg, "--no-cache")) {
            no_cache = true;
        } else if (std.mem.eql(u8, arg, "--cache-dir")) {
            idx += 1;
            if (idx >= argv.len) {
                std.debug.print("vakedc-zig: --cache-dir requires an argument\n", .{});
                std.process.exit(2);
            }
            cache_dir_arg = argv[idx];
        } else if (std.mem.startsWith(u8, arg, "--cache-dir=")) {
            cache_dir_arg = arg["--cache-dir=".len..];
        } else if (std.mem.startsWith(u8, arg, "--")) {
            std.debug.print("vakedc-zig: unknown option '{s}'\n", .{arg});
            std.process.exit(2);
        } else {
            file_arg = arg;
        }
    }

    const file_path = file_arg orelse {
        std.debug.print("usage: vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>\n", .{});
        std.process.exit(2);
    };

    // 1. Read source file.
    const src = Io.Dir.cwd().readFileAlloc(io, file_path, alloc, .unlimited) catch |err| {
        std.debug.print("{s}: cannot read file: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };

    // 2. Compute SHA-256 of source.
    var src_h = Sha256.init(.{});
    src_h.update(src);
    var src_digest: [32]u8 = undefined;
    src_h.final(&src_digest);

    // 3. Determine cache directory.
    const cache_dir: ?[]const u8 = blk: {
        if (no_cache) break :blk null;
        if (cache_dir_arg) |d| break :blk d;
        // Default: .vaked/cache/ relative to the source file's directory.
        const dir = std.fs.path.dirname(file_path) orelse ".";
        break :blk try std.mem.concat(alloc, u8, &.{ dir, "/.vaked/cache" });
    };

    // 4. Cache lookup.
    if (cache_dir) |cd| {
        var c = cache_mod.Cache.init(alloc, cd);
        defer c.deinit();
        if (c.get(src_digest) catch null) |cached_bytes| {
            try stdoutWrite(io, cached_bytes);
            return;
        }
    }

    // 5. Lex.
    const tokens = lexer.tokenize(alloc, src, file_path) catch |err| {
        std.debug.print("{s}: lexer error: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };

    // 6. Parse.
    const parsed_file = parser.parse(alloc, tokens, file_path) catch |err| {
        std.debug.print("{s}: parse error: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };

    // 7. Serialize AST to JSON bytes.
    var json_buf = std.ArrayList(u8).init(alloc);
    ast.writeJson(parsed_file, json_buf.writer(), alloc) catch |err| {
        std.debug.print("{s}: JSON serialization error: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };
    const json_bytes = try json_buf.toOwnedSlice();

    // 8. Store in cache.
    if (cache_dir) |cd| {
        var c = cache_mod.Cache.init(alloc, cd);
        defer c.deinit();
        c.put(src_digest, json_bytes) catch |err| {
            // Cache write failure is non-fatal: warn on stderr, continue.
            std.debug.print("{s}: warning: cache write failed: {s}\n", .{ file_path, @errorName(err) });
        };
    }

    // 9. Write JSON to stdout.
    try stdoutWrite(io, json_bytes);
}

fn stdoutWrite(io: Io, bytes: []const u8) !void {
    var buf: [4096]u8 = undefined;
    var fw = Io.File.stdout().writer(io, &buf);
    try fw.interface.writeAll(bytes);
    try fw.interface.flush();
}

test "main module imports" {
    _ = ast;
    _ = lexer;
    _ = parser;
    _ = cache_mod;
}

test "alloc safety: GPA no leaks through parse pipeline" {
    var gpa = std.heap.GeneralPurposeAllocator(.{ .safety = true }){};
    {
        var arena = std.heap.ArenaAllocator.init(gpa.allocator());
        defer arena.deinit();
        const alloc = arena.allocator();
        const src = "runtime myRuntime { version = \"1.0\" }";
        const toks = try lexer.tokenize(alloc, src, "<gpa-test>");
        const file = try parser.parse(alloc, toks, "<gpa-test>");
        _ = file;
    }
    // After arena.deinit() all memory is returned to the GPA — expect no leaks.
    try std.testing.expect(gpa.deinit() == .ok);
}
