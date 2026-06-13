// vakedc-zig parser — tokens → AST
const std = @import("std");
const lexer = @import("lexer.zig");

pub const Parser = struct {
    allocator: std.mem.Allocator,
    tokens: []const lexer.Token,
    pos: usize,

    pub fn init(allocator: std.mem.Allocator, lex: *const lexer.Lexer) !Parser {
        return Parser{
            .allocator = allocator,
            .tokens = lex.tokens.items,
            .pos = 0,
        };
    }

    pub fn deinit(self: *Parser) void {
        _ = self;
        // Cleanup if needed
    }

    pub fn parseFile(self: *Parser) ![]const u8 {
        // TODO: Parse declarations
        return "";
    }
};
