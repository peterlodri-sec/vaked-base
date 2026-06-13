const std = @import("std");
const ast = @import("ast.zig");
const lexer = @import("lexer.zig");
const parser = @import("parser.zig");
const cache_mod = @import("cache.zig");
const build_options = @import("build_options");

const Sha256 = std.crypto.hash.sha2.Sha256;

// ---- Usage ------------------------------------------------------------------
// vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>

fn printUsage(stderr: anytype) !void {
    try stderr.writeAll("usage: vakedc-zig parse [--cache-dir DIR] [--no-cache] <file.vaked>\n");
}

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    const stderr = std.io.getStdErr().writer();
    var bw = std.io.bufferedWriter(std.io.getStdOut().writer());
    const stdout = bw.writer();

    var args_iter = try std.process.argsWithAllocator(alloc);
    defer args_iter.deinit();
    _ = args_iter.next(); // skip argv[0]

    // Parse subcommand: only "parse" is supported in v0.1.0
    const subcmd = args_iter.next() orelse {
        try printUsage(stderr);
        std.process.exit(2);
    };
    if (std.mem.eql(u8, subcmd, "--version")) {
        try stdout.print("vakedc-zig {s}\n", .{build_options.version});
        try bw.flush();
        return;
    }
    if (!std.mem.eql(u8, subcmd, "parse")) {
        try stderr.print("vakedc-zig: unknown subcommand '{s}'\n", .{subcmd});
        try printUsage(stderr);
        std.process.exit(2);
    }

    var cache_dir_arg: ?[]const u8 = null;
    var no_cache = false;
    var file_arg: ?[]const u8 = null;

    while (args_iter.next()) |arg| {
        if (std.mem.eql(u8, arg, "--no-cache")) {
            no_cache = true;
        } else if (std.mem.eql(u8, arg, "--cache-dir")) {
            cache_dir_arg = args_iter.next() orelse {
                try stderr.writeAll("vakedc-zig: --cache-dir requires an argument\n");
                std.process.exit(2);
            };
        } else if (std.mem.startsWith(u8, arg, "--cache-dir=")) {
            cache_dir_arg = arg["--cache-dir=".len..];
        } else if (std.mem.startsWith(u8, arg, "--")) {
            try stderr.print("vakedc-zig: unknown option '{s}'\n", .{arg});
            std.process.exit(2);
        } else {
            file_arg = arg;
        }
    }

    const file_path = file_arg orelse {
        try printUsage(stderr);
        std.process.exit(2);
    };

    // 1. Read source file.
    const src = std.fs.cwd().readFileAlloc(alloc, file_path, 100 * 1024 * 1024) catch |err| {
        try stderr.print("{s}: cannot read file: {s}\n", .{ file_path, @errorName(err) });
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
            try stdout.writeAll(cached_bytes);
            try bw.flush();
            return;
        }
    }

    // 5. Lex.
    const tokens = lexer.tokenize(alloc, src, file_path) catch |err| {
        try stderr.print("{s}: lexer error: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };

    // 6. Parse.
    const parsed_file = parser.parse(alloc, tokens, file_path) catch |err| {
        try stderr.print("{s}: parse error: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };

    // 7. Serialize AST to JSON bytes.
    var json_buf = std.ArrayList(u8).init(alloc);
    ast.writeJson(parsed_file, json_buf.writer(), alloc) catch |err| {
        try stderr.print("{s}: JSON serialization error: {s}\n", .{ file_path, @errorName(err) });
        std.process.exit(1);
    };
    const json_bytes = try json_buf.toOwnedSlice();

    // 8. Store in cache.
    if (cache_dir) |cd| {
        var c = cache_mod.Cache.init(alloc, cd);
        defer c.deinit();
        c.put(src_digest, json_bytes) catch |err| {
            // Cache write failure is non-fatal: warn on stderr, continue.
            try stderr.print("{s}: warning: cache write failed: {s}\n", .{ file_path, @errorName(err) });
        };
    }

    // 9. Write JSON to stdout (buffered).
    try stdout.writeAll(json_bytes);
    try bw.flush();
}

test "main module imports" {
    _ = ast;
    _ = lexer;
    _ = parser;
    _ = cache_mod;
}
