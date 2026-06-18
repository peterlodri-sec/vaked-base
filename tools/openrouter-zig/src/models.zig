//! Type definitions — 1:1 with @vaked/openrouter-ts/src/types.ts
const std = @import("std");

// ── Model catalog ───────────────────────────────────────────────────────────

pub const ModelEntry = struct {
    id: []const u8,
    label: []const u8,
    prompt_cost: f64,       // USD per 1M tokens
    completion_cost: f64,   // USD per 1M tokens
};

pub const MODELS = [_]ModelEntry{
    .{ .id = "deepseek/deepseek-v4-pro",        .label = "DeepSeek V4 Pro",     .prompt_cost = 0.27,  .completion_cost = 0.27  },
    .{ .id = "anthropic/claude-opus-4-8-fast",  .label = "Claude Opus 4.8",     .prompt_cost = 15.00, .completion_cost = 75.00 },
    .{ .id = "google/gemini-2.5-flash",          .label = "Gemini 2.5 Flash",    .prompt_cost = 0.15,  .completion_cost = 0.60  },
    .{ .id = "qwen/qwen3-235b-a22b-thinking",   .label = "Qwen3 235B Thinking", .prompt_cost = 2.50,  .completion_cost = 5.00  },
    .{ .id = "meta-llama/llama-4-maverick",      .label = "Llama 4 Maverick",    .prompt_cost = 0.20,  .completion_cost = 0.60  },
    .{ .id = "anthropic/claude-haiku-4-5",       .label = "Claude Haiku 4.5",    .prompt_cost = 0.25,  .completion_cost = 1.25  },
    .{ .id = "deepseek/deepseek-v4-flash",       .label = "DeepSeek V4 Flash",   .prompt_cost = 0.14,  .completion_cost = 0.14  },
};

pub fn resolveModel(alias: []const u8) ?ModelEntry {
    // Check aliases
    if (std.mem.eql(u8, alias, "deepseek")) return MODELS[0];
    if (std.mem.eql(u8, alias, "claude"))   return MODELS[1];
    if (std.mem.eql(u8, alias, "gemini"))   return MODELS[2];
    if (std.mem.eql(u8, alias, "qwen"))     return MODELS[3];
    if (std.mem.eql(u8, alias, "llama"))    return MODELS[4];
    if (std.mem.eql(u8, alias, "haiku"))    return MODELS[5];
    if (std.mem.eql(u8, alias, "deepseek-flash")) return MODELS[6];
    // Also check exact ID match
    for (MODELS) |m| {
        if (std.mem.eql(u8, alias, m.id)) return m;
    }
    return null;
}

// ── API types ───────────────────────────────────────────────────────────────

pub const Message = struct {
    role: []const u8,
    content: []const u8,
};

pub const RequestPayload = struct {
    model: []const u8,
    messages: []const Message,
    max_tokens: ?u32 = null,
    stream: bool = false,
};

pub const ResponseMessage = struct {
    role: ?[]const u8 = null,
    content: ?[]const u8 = null,
    reasoning_content: ?[]const u8 = null,
};

pub const Choice = struct {
    message: ResponseMessage,
};

pub const Usage = struct {
    prompt_tokens: u32 = 0,
    completion_tokens: u32 = 0,
    total_tokens: u32 = 0,
};

pub const ResponsePayload = struct {
    choices: []Choice,
    model: ?[]const u8 = null,
    usage: ?Usage = null,
};

pub const ErrorDetail = struct {
    message: ?[]const u8 = null,
    @"type": ?[]const u8 = null,
};

pub const ErrorPayload = struct {
    @"error": ErrorDetail,
};

// ── Context7 types ──────────────────────────────────────────────────────────

pub const CodeExample = struct {
    language: []const u8 = "",
    code: []const u8 = "",
};

pub const CodeSnippet = struct {
    codeTitle: ?[]const u8 = null,
    codeDescription: ?[]const u8 = null,
    codeLanguage: ?[]const u8 = null,
    codeListCodeExample: ?[]const CodeExample = null,
};

pub const InfoSnippet = struct {
    content: []const u8 = "",
    breadcrumb: ?[]const u8 = null,
};

pub const ContextResponse = struct {
    codeSnippets: []CodeSnippet,
    infoSnippets: []InfoSnippet,
};

pub const Library = struct {
    id: []const u8 = "",
    title: ?[]const u8 = null,
    description: ?[]const u8 = null,
    trustScore: ?f64 = null,
    stars: ?u64 = null,
    versions: [][]const u8 = &.{},
};

pub const SearchResponse = struct {
    results: []Library,
};

// ── Budget ──────────────────────────────────────────────────────────────────

pub const BudgetState = struct {
    remaining: f64,
    cap: f64,
};

// ── Agent config ────────────────────────────────────────────────────────────

pub const VakedAgentConfig = struct {
    api_key: ?[]const u8 = null,
    default_model: []const u8 = "deepseek/deepseek-v4-pro",
    context7: bool = true,
    max_tokens: u32 = 2000,
    langfuse: bool = true,
};

// ── Deliberation panel ──────────────────────────────────────────────────────

pub const PanelModel = struct {
    id: []const u8,
    name: []const u8,
    prompt_cost: f64,
    completion_cost: f64,
};

pub const PANEL_MODELS = [_]PanelModel{
    .{ .id = "anthropic/claude-opus-4-8-fast",  .name = "Claude Opus 4.8",     .prompt_cost = 15.00, .completion_cost = 75.00 },
    .{ .id = "google/gemini-2.5-pro",           .name = "Gemini 2.5 Pro",      .prompt_cost = 1.25,  .completion_cost = 5.00  },
    .{ .id = "anthropic/claude-sonnet-4-6",     .name = "Claude Sonnet 4.6",   .prompt_cost = 3.00,  .completion_cost = 15.00 },
    .{ .id = "google/gemini-2.5-flash",          .name = "Gemini 2.5 Flash",    .prompt_cost = 0.15,  .completion_cost = 0.60  },
    .{ .id = "deepseek/deepseek-v4-pro",        .name = "DeepSeek V4",          .prompt_cost = 0.27,  .completion_cost = 0.27  },
    .{ .id = "qwen/qwen3-235b-a22b-thinking",   .name = "Qwen3 235B",          .prompt_cost = 2.50,  .completion_cost = 5.00  },
    .{ .id = "meta-llama/llama-4-maverick",      .name = "Llama 4 Maverick",    .prompt_cost = 0.20,  .completion_cost = 0.60  },
    .{ .id = "anthropic/claude-haiku-4-5",       .name = "Claude Haiku 4.5",    .prompt_cost = 0.25,  .completion_cost = 1.25  },
    .{ .id = "google/gemini-2.0-flash",          .name = "Gemini 2.0 Flash",    .prompt_cost = 0.15,  .completion_cost = 0.60  },
    .{ .id = "mistralai/mistral-large",          .name = "Mistral Large",       .prompt_cost = 2.00,  .completion_cost = 6.00  },
    .{ .id = "cohere/command-r-plus",            .name = "Command R+",          .prompt_cost = 2.50,  .completion_cost = 10.00 },
    .{ .id = "deepseek/deepseek-chat",           .name = "DeepSeek Chat",       .prompt_cost = 0.14,  .completion_cost = 0.28  },
    .{ .id = "google/gemma-3-27b",               .name = "Gemma 3 27B",         .prompt_cost = 0.15,  .completion_cost = 0.15  },
    .{ .id = "meta-llama/llama-4-scout",         .name = "Llama 4 Scout",       .prompt_cost = 0.10,  .completion_cost = 0.30  },
    .{ .id = "qwen/qwen-2.5-72b",                .name = "Qwen 2.5 72B",        .prompt_cost = 0.35,  .completion_cost = 0.40  },
    .{ .id = "mistralai/mistral-small",           .name = "Mistral Small",       .prompt_cost = 1.00,  .completion_cost = 3.00  },
    .{ .id = "anthropic/claude-haiku-3-5",       .name = "Claude Haiku 3.5",    .prompt_cost = 0.80,  .completion_cost = 4.00  },
    .{ .id = "openai/gpt-4.1-mini",              .name = "GPT-4.1 Mini",        .prompt_cost = 0.15,  .completion_cost = 0.60  },
    .{ .id = "google/gemini-flash-1.5",           .name = "Gemini Flash 1.5",    .prompt_cost = 0.075, .completion_cost = 0.30  },
};

pub const JUDGE_MODEL = "anthropic/claude-opus-4-8-fast";

// ── Langfuse ────────────────────────────────────────────────────────────────

pub const LangfuseTrace = struct {
    name: []const u8,
    input: []const u8,
    output: []const u8,
    model: []const u8,
    prompt_tokens: u32,
    completion_tokens: u32,
    cost: ?f64 = null,
    latency_ms: ?u64 = null,
    agent_name: []const u8 = "vaked-openrouter-zig",
};


/// Conductor — route a prompt to the best model based on task keywords.
/// "auto" strategy — models choose their own.
pub fn routeModel(prompt: []const u8, cheap_id: []const u8, quality_id: []const u8, creative_id: []const u8) []const u8 {
    if (prompt.len == 0) return cheap_id;
    // code/review/debug → quality model (case-insensitive via std.ascii)
    const code_kw = [_][]const u8{ "code", "review", "write", "implement", "fix", "debug", "test", "optimize", "refactor" };
    for (code_kw) |kw| { if (std.ascii.indexOfIgnoreCase(prompt, kw) != null) return quality_id; }
    // creative/design → creative model
    const creative_kw = [_][]const u8{ "creative", "brainstorm", "design" };
    for (creative_kw) |kw| { if (std.ascii.indexOfIgnoreCase(prompt, kw) != null) return creative_id; }
    return cheap_id;
}

/// Build model fallback chain for OpenRouter's models[] parameter.
pub fn modelFallbackChain(allocator: std.mem.Allocator, primary: []const u8) ![][]const u8 {
    var chain: std.ArrayListUnmanaged([]const u8) = .{ .items = &.{}, .capacity = 0 };
    errdefer chain.deinit(allocator);
    try chain.append(allocator, primary);
    if (std.mem.indexOf(u8, primary, "claude") != null) {
        try chain.append(allocator, "deepseek/deepseek-v4-pro");
        try chain.append(allocator, "google/gemini-2.5-flash");
    } else {
        try chain.append(allocator, "google/gemini-2.5-flash");
        try chain.append(allocator, "anthropic/claude-haiku-4-5");
    }
    return chain.items;
}
