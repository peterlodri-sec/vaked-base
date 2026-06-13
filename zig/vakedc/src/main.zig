//! vakedc-zig (v0.x) — a native Zig front-end for Vaked.
//!
//! Status: v0.x runnable SUBSET. It lexes and parses the subset documented in
//! docs/compiler/ZIG_FRONTEND.md and parser.zig, enough to parse real examples
//! such as vaked/examples/swe-swarm-loadtest.vaked end to end. It does NOT yet
//! type-check or lower — that is the Python `vakedc`'s job today and the
//! follow-up tracked in the PR.
//!
//! Usage:
//!   vakedc-zig parse <file.vaked> [--json]
//!
//! Exit codes: 0 = parsed OK, 1 = parse/lex/usage error, 2 = I/O error.

const std = @import("std");
const lex = @import("lexer.zig");
const parser = @import("parser.zig");

const usage = "usage: vakedc-zig parse <file.vaked> [--json]\n";

pub fn main() u8 {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const a = arena.allocator();

    const args = std.process.argsAlloc(a) catch return 2;

    if (args.len < 3 or !std.mem.eql(u8, args[1], "parse")) {
        std.io.getStdErr().writeAll(usage) catch {};
        return 1;
    }
    const path = args[2];
    const json = args.len > 3 and std.mem.eql(u8, args[3], "--json");

    const src = std.fs.cwd().readFileAlloc(a, path, 64 * 1024 * 1024) catch |e| {
        std.debug.print("vakedc-zig: cannot read {s}: {s}\n", .{ path, @errorName(e) });
        return 2;
    };

    var toks = std.ArrayList(lex.Token).init(a);
    lex.tokenize(a, src, &toks) catch |e| {
        std.debug.print("vakedc-zig: {s}: lex error: {s}\n", .{ path, @errorName(e) });
        return 1;
    };

    var p = parser.Parser.init(a, toks.items);
    const file = p.parseFile() catch {
        std.debug.print("vakedc-zig: {s}:{d}:{d}: parse error: expected {s}\n", .{ path, p.err_line, p.err_col, p.err_msg });
        return 1;
    };

    const s = parser.summarize(file);
    const out = std.io.getStdOut().writer();
    if (json) {
        out.print(
            "{{\"file\":\"{s}\",\"ok\":true,\"imports\":{d},\"decls\":{d},\"edges\":{d},\"tokens\":{d}}}\n",
            .{ path, s.imports, s.decls, s.edges, toks.items.len },
        ) catch {};
    } else {
        out.print(
            "vakedc-zig: parsed {s} OK — {d} import(s), {d} declaration(s), {d} edge(s), {d} tokens\n",
            .{ path, s.imports, s.decls, s.edges, toks.items.len },
        ) catch {};
    }
    return 0;
}

test {
    // Pull in the lexer and parser unit tests so `zig build test` runs them.
    std.testing.refAllDecls(@This());
    _ = lex;
    _ = parser;
}
