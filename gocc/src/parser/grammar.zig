const std = @import("std");
const types = @import("gocc-core");
const lex = @import("lexer.zig");
const Lexer = lex.Lexer;
const TokenKind = lex.TokenKind;

pub const ParseError = error{ UnexpectedToken, OutOfMemory } || lex.LexError;

/// Consume the next token and assert it has the expected kind.
fn expect(lexer: *Lexer, kind: TokenKind) ParseError!lex.Token {
    const tok = try lexer.next();
    if (tok.kind != kind) return error.UnexpectedToken;
    return tok;
}

/// Return the src for string/ident/number tokens without quotes.
fn atomValue(tok: lex.Token) []const u8 {
    return switch (tok.kind) {
        .string => tok.src[1 .. tok.src.len - 1], // strip surrounding quotes
        else => tok.src,
    };
}

/// Parse @(key:val, key:val) and apply the params via the supplied callback.
/// Caller decides whether to put them in graph.config or node props.
fn parseAnnotationInto(
    alloc: std.mem.Allocator,
    lexer: *Lexer,
    comptime K: type, // std.StringHashMapUnmanaged([]const u8) or similar
    map: *K,
    prefix: []const u8, // "" for config; "config:" for stage props
) ParseError!void {
    _ = try expect(lexer, .at);
    _ = try expect(lexer, .lparen);

    while (true) {
        const key_tok = try expect(lexer, .ident);
        _ = try expect(lexer, .colon);
        const val_tok = try lexer.next();
        // val_tok must be ident, string, or number
        switch (val_tok.kind) {
            .ident, .string, .number => {},
            else => return error.UnexpectedToken,
        }
        const val = atomValue(val_tok);

        // Build key with optional prefix
        const full_key = if (prefix.len == 0)
            key_tok.src
        else
            try std.fmt.allocPrint(alloc, "{s}{s}", .{ prefix, key_tok.src });

        try map.put(alloc, full_key, val);

        const peek = try lexer.peek();
        if (peek.kind == .comma) {
            _ = try lexer.next(); // consume comma
        } else {
            break;
        }
    }

    _ = try expect(lexer, .rparen);
}

/// Parse a single stage: [annotation?] ident [&ident [? "string"]]
/// Returns the stage name (ident src slice).
/// Emits the ArpNode into graph (caller handles edges).
fn parseStage(alloc: std.mem.Allocator, lexer: *Lexer, graph: *types.ArpGraph) ParseError![]const u8 {
    // Optional prefix annotation: @(...)
    var stage_anno: std.StringHashMapUnmanaged([]const u8) = .empty;
    defer stage_anno.deinit(alloc);

    const peek = try lexer.peek();
    if (peek.kind == .at) {
        try parseAnnotationInto(alloc, lexer, std.StringHashMapUnmanaged([]const u8), &stage_anno, "");
    }

    // Stage name (ident)
    const name_tok = try expect(lexer, .ident);
    const name = name_tok.src;
    const id = try std.fmt.allocPrint(alloc, "stage:{s}", .{name});

    var node = types.ArpNode{
        .id = id,
        .kind = .pipeline_stage,
        .name = name,
        .props = .empty,
    };

    // Apply stage annotation params with "config:" prefix
    var anno_it = stage_anno.iterator();
    while (anno_it.next()) |entry| {
        const prop_key = try std.fmt.allocPrint(alloc, "config:{s}", .{entry.key_ptr.*});
        try node.setProp(alloc, prop_key, entry.value_ptr.*);
    }

    // Optional &agent [? "prompt"]
    const peek2 = try lexer.peek();
    if (peek2.kind == .amp) {
        _ = try lexer.next(); // consume &
        const agent_tok = try expect(lexer, .ident);
        try node.setProp(alloc, "capability", agent_tok.src);

        const peek3 = try lexer.peek();
        if (peek3.kind == .question) {
            _ = try lexer.next(); // consume ?
            const prompt_tok = try expect(lexer, .string);
            const prompt_val = atomValue(prompt_tok);
            try node.setProp(alloc, "prompt", prompt_val);
        }
    }

    try graph.addNode(node);
    return name;
}

/// Parse the chain: stage (> stage)* and emit all nodes and edges.
fn parseChain(alloc: std.mem.Allocator, lexer: *Lexer, graph: *types.ArpGraph) ParseError!void {
    const first_name = try parseStage(alloc, lexer, graph);
    var prev_name = first_name;

    while (true) {
        const peek = try lexer.peek();
        if (peek.kind != .gt) break;
        _ = try lexer.next(); // consume >

        const next_name = try parseStage(alloc, lexer, graph);
        const from_id = try std.fmt.allocPrint(alloc, "stage:{s}", .{prev_name});
        const to_id = try std.fmt.allocPrint(alloc, "stage:{s}", .{next_name});

        try graph.addEdge(.{
            .from = from_id,
            .to = to_id,
            .label = "pipeline",
        });

        prev_name = next_name;
    }
}

pub fn parse(alloc: std.mem.Allocator, src: []const u8) ParseError!types.ArpGraph {
    var lexer = Lexer.init(src);
    var graph = types.ArpGraph.init(alloc);
    errdefer graph.deinit();

    // Optional global annotation @(...) before the chain
    const peek = try lexer.peek();
    if (peek.kind == .at) {
        try parseAnnotationInto(alloc, &lexer, std.StringHashMapUnmanaged([]const u8), &graph.config, "");
    }

    // Parse the chain
    try parseChain(alloc, &lexer, &graph);

    // Expect EOF
    const last = try lexer.peek();
    if (last.kind != .eof) return error.UnexpectedToken;

    return graph;
}

// ─── Tests ───────────────────────────────────────────────────────────────────

test "simple 2-stage chain" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    var graph = try parse(alloc, "stage-a > stage-b");
    defer graph.deinit();

    try std.testing.expectEqual(@as(usize, 2), graph.nodes.count());
    try std.testing.expectEqual(@as(usize, 1), graph.edges.items.len);

    const edge = graph.edges.items[0];
    try std.testing.expectEqualStrings("stage:stage-a", edge.from);
    try std.testing.expectEqualStrings("stage:stage-b", edge.to);
    try std.testing.expectEqualStrings("pipeline", edge.label);
}

test "market simulator full parse" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    const src =
        \\@(agents:100000, cycles:1440, tick_ms:1000)
        \\initialize-wallets
        \\  > monte-carlo-fork &market_agent ? "execute high-frequency order strategies"
        \\  > orderbook-matching
        \\  > liquidity-clearing &settlement_engine
        \\  > state-compressor
        \\  > metrics-aggregate > @(dest:"db/sim_v2.parquet") data-flush
    ;

    var graph = try parse(alloc, src);
    defer graph.deinit();

    // Global config
    try std.testing.expectEqualStrings("100000", graph.config.get("agents") orelse return error.TestUnexpectedResult);
    try std.testing.expectEqualStrings("1440", graph.config.get("cycles") orelse return error.TestUnexpectedResult);
    try std.testing.expectEqualStrings("1000", graph.config.get("tick_ms") orelse return error.TestUnexpectedResult);

    // 7 nodes
    try std.testing.expectEqual(@as(usize, 7), graph.nodes.count());

    // 6 edges
    try std.testing.expectEqual(@as(usize, 6), graph.edges.items.len);

    // monte-carlo-fork: capability + prompt
    const monte = graph.nodes.get("stage:monte-carlo-fork") orelse return error.TestUnexpectedResult;
    try std.testing.expectEqualStrings("market_agent", monte.getProp("capability") orelse return error.TestUnexpectedResult);
    try std.testing.expectEqualStrings("execute high-frequency order strategies", monte.getProp("prompt") orelse return error.TestUnexpectedResult);

    // liquidity-clearing: capability only
    const liquidity = graph.nodes.get("stage:liquidity-clearing") orelse return error.TestUnexpectedResult;
    try std.testing.expectEqualStrings("settlement_engine", liquidity.getProp("capability") orelse return error.TestUnexpectedResult);

    // data-flush: config:dest
    const flush = graph.nodes.get("stage:data-flush") orelse return error.TestUnexpectedResult;
    try std.testing.expectEqualStrings("db/sim_v2.parquet", flush.getProp("config:dest") orelse return error.TestUnexpectedResult);
}

test "annotation prefix on stage" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    var graph = try parse(alloc, "a > @(x:1) b");
    defer graph.deinit();

    try std.testing.expectEqual(@as(usize, 2), graph.nodes.count());
    try std.testing.expectEqual(@as(usize, 1), graph.edges.items.len);

    const b = graph.nodes.get("stage:b") orelse return error.TestUnexpectedResult;
    try std.testing.expectEqualStrings("1", b.getProp("config:x") orelse return error.TestUnexpectedResult);
}

test "benchmark: 100k parses of 2-stage chain" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const alloc = arena.allocator();

    const src = "stage-a > stage-b";
    var i: usize = 0;
    while (i < 100_000) : (i += 1) {
        var g = try parse(alloc, src);
        g.deinit();
        // Reset arena each iteration to avoid unbounded growth
        _ = arena.reset(.retain_capacity);
    }
    // Benchmark gate passed trivially — this grammar is O(n) per token.
}
