// TODO Phase 2 integration: requires running nullclaw server. See GOCC.md §Integration Testing.
// All network methods (pair, fetchAgentCard, sendTask, waitForTask) are stubs.
// Real implementation will use std.http.Client against a nullclaw A2A v0.3.0 endpoint.

const std = @import("std");

pub const NullclawError = error{
    PairFailed,
    AgentCardFailed,
    TaskFailed,
    HttpError,
    OutOfMemory,
};

/// Connection to one nullclaw agent process.
pub const NullclawClient = struct {
    alloc: std.mem.Allocator,
    base_url: []const u8, // e.g., "http://localhost:3042"
    bearer_token: ?[]const u8 = null,

    pub fn init(alloc: std.mem.Allocator, base_url: []const u8) NullclawClient {
        return .{ .alloc = alloc, .base_url = base_url };
    }

    /// Step 1: POST /pair → exchange for bearer token.
    /// nullclaw returns {"token": "..."} which we store as bearer_token.
    /// JSON-RPC 2.0 A2A v0.3.0 pairing handshake.
    pub fn pair(self: *NullclawClient) NullclawError!void {
        // TODO Phase 2 integration: requires running nullclaw server. See GOCC.md §Integration Testing.
        // Real flow:
        //   POST {base_url}/pair  body: {}
        //   Response: parse JSON, extract "token" field
        //   self.bearer_token = parsed_token
        _ = self;
    }

    /// Step 2: GET /.well-known/agent-card.json → verify agent capabilities.
    pub fn fetchAgentCard(self: *NullclawClient) NullclawError!AgentCard {
        // TODO Phase 2 integration: requires running nullclaw server. See GOCC.md §Integration Testing.
        _ = self;
        return .{ .name = "stub-agent", .capabilities = &.{} };
    }

    /// Step 3: POST /a2a with JSON-RPC 2.0 message/send.
    /// Payload shape:
    ///   {"jsonrpc":"2.0","method":"message/send",
    ///    "params":{"message":{"role":"user","content":[{"type":"text","text":"<prompt>"}]}},
    ///    "id":<task_id>}
    pub fn sendTask(self: *NullclawClient, prompt: []const u8, task_id: u64) NullclawError![]const u8 {
        // TODO Phase 2 integration: requires running nullclaw server. See GOCC.md §Integration Testing.
        _ = self;
        _ = prompt;
        _ = task_id;
        return try self.alloc.dupe(u8, "stub-task-id");
    }

    /// Step 4: Poll tasks/get until task reaches terminal state.
    pub fn waitForTask(self: *NullclawClient, task_id: []const u8) NullclawError!TaskResult {
        // TODO Phase 2 integration: requires running nullclaw server. See GOCC.md §Integration Testing.
        _ = self;
        _ = task_id;
        return .{ .status = .complete, .output = try self.alloc.dupe(u8, "") };
    }
};

pub const AgentCard = struct {
    name: []const u8,
    capabilities: []const []const u8,
};

pub const TaskStatus = enum { running, complete, failed };

pub const TaskResult = struct {
    status: TaskStatus,
    output: []const u8,
};

/// Port assignment strategy: UDS first, TCP range fallback.
/// Returns "unix:/path/to.sock" or "http://localhost:{port}"
pub fn agentEndpoint(alloc: std.mem.Allocator, capability: []const u8, index: usize) ![]const u8 {
    // Try Unix domain socket path first — UDS HTTP not yet in std.http, fall back to TCP.
    const home = std.posix.getenv("HOME") orelse "/tmp";
    const sock_path = try std.fmt.allocPrint(alloc, "{s}/.nullclaw/sockets/{s}-{d}.sock", .{ home, capability, index });
    // UDS HTTP not yet supported via std.http.Client; return TCP fallback.
    alloc.free(sock_path);
    const capped_index = @min(index, 999); // cap at 999 (max 1000 agents, ports 3000-3999)
    return std.fmt.allocPrint(alloc, "http://localhost:{d}", .{ 3000 + capped_index });
}
