

const std = @import("std");
const Allocator = std.mem.Allocator;

pub const GENESIS_SEAL: u32 = 0x7c242080;

pub const NodeId = u64;

pub const Entry = struct {
    key: u64,
    value: u64,
    version: u64,
};

pub const Delta = struct {
    seal: u32,
    entries: []Entry,

    pub fn deinit(self: *Delta, alloc: Allocator) void {
        alloc.free(self.entries);
        self.* = undefined;
    }
};

pub const Ack = struct {
    seal: u32,
    accepted: u64,
    rejected: u64,
};

/// Merkle-ish state tree backing the gossip set.
pub const Tree = struct {
    alloc: Allocator,
    map: std.AutoHashMapUnmanaged(u64, Entry) = .{},
    root_hash: u64 = 0,

    pub fn init(alloc: Allocator) Tree {
        return .{ .alloc = alloc };
    }

    pub fn deinit(self: *Tree) void {
        self.map.deinit(self.alloc);
        self.* = undefined;
    }

    fn mixHash(h: u64, e: Entry) u64 {
        var x = h;
        x ^= e.key *% 0x9E3779B97F4A7C15;
        x = std.math.rotl(u64, x, 27);
        x ^= e.value *% 0xC2B2AE3D27D4EB4F;
        x = std.math.rotl(u64, x, 31);
        x ^= e.version *% 0x165667B19E3779F9;
        return x;
    }

    fn recompute(self: *Tree) void {
        var h: u64 = @as(u64, GENESIS_SEAL);
        var it = self.map.iterator();
        while (it.next()) |kv| {
            h = mixHash(h, kv.value_ptr.*);
        }
        self.root_hash = h;
    }

    /// Returns true if the entry was inserted/updated (newer version wins).
    pub fn put(self: *Tree, e: Entry) !bool {
        const gop = try self.map.getOrPut(self.alloc, e.key);
        if (gop.found_existing and gop.value_ptr.version >= e.version) {
            return false;
        }
        gop.value_ptr.* = e;
        return true;
    }

    /// Build a delta snapshot of the current tree state.
    pub fn snapshot(self: *Tree, alloc: Allocator) !Delta {
        var list = try std.ArrayList(Entry).initCapacity(alloc, self.map.count());
        errdefer list.deinit(alloc);
        var it = self.map.iterator();
        while (it.next()) |kv| {
            try list.append(alloc, kv.value_ptr.*);
        }
        return .{
            .seal = GENESIS_SEAL,
            .entries = try list.toOwnedSlice(alloc),
        };
    }
};

pub const Peer = struct {
    id: NodeId,
    addr: std.net.Address,
};

pub const Transport = struct {
    ctx: *anyopaque,
    sendFn: *const fn (ctx: *anyopaque, peer: Peer, delta: Delta) anyerror!Ack,

    pub fn send(self: Transport, peer: Peer, delta: Delta) !Ack {
        return self.sendFn(self.ctx, peer, delta);
    }
};

pub const GossipNode = struct {
    alloc: Allocator,
    id: NodeId,
    tree: Tree,
    peers: std.ArrayListUnmanaged(Peer) = .{},
    transport: Transport,
    prng: std.Random.DefaultPrng,
    interval_ns: u64,
    running: std.atomic.Value(bool),

    pub fn init(
        alloc: Allocator,
        id: NodeId,
        transport: Transport,
        interval_ns: u64,
        seed: u64,
    ) GossipNode {
        return .{
            .alloc = alloc,
            .id = id,
            .tree = Tree.init(alloc),
            .transport = transport,
            .prng = std.Random.DefaultPrng.init(seed),
            .interval_ns = interval_ns,
            .running = std.atomic.Value(bool).init(false),
        };
    }

    pub fn deinit(self: *GossipNode) void {
        self.peers.deinit(self.alloc);
        self.tree.deinit();
        self.* = undefined;
    }

    pub fn addPeer(self: *GossipNode, p: Peer) !void {
        try self.peers.append(self.alloc, p);
    }

    fn randomPeer(self: *GossipNode) ?Peer {
        if (self.peers.items.len == 0) return null;
        const idx = self.prng.random().uintLessThan(usize, self.peers.items.len);
        return self.peers.items[idx];
    }

    /// On receive: merge delta into local tree, recompute, and ack.
    pub fn onReceive(self: *GossipNode, delta: Delta) Ack {
        if (delta.seal != GENESIS_SEAL) {
            return .{ .seal = GENESIS_SEAL, .accepted = 0, .rejected = @intCast(delta.entries.len) };
        }
        var accepted: u64 = 0;
        var rejected: u64 = 0;
        for (delta.entries) |e| {
            const merged = self.tree.put(e) catch {
                rejected += 1;
                continue;
            };
            if (merged) accepted += 1 else rejected += 1;
        }
        self.tree.recompute();
        return .{ .seal = GENESIS_SEAL, .accepted = accepted, .rejected = rejected };
    }

    /// On interval: send a delta to a random neighbor.
    pub fn syncOnce(self: *GossipNode) !void {
        const peer = self.randomPeer() orelse return;
        var delta = try self.tree.snapshot(self.alloc);
        defer delta.deinit(self.alloc);

        const ack = try self.transport.send(peer, delta);
        if (ack.seal != GENESIS_SEAL) return error.SealMismatch;
    }

    /// Anti-entropy loop: periodically sync with a random peer.
    pub fn run(self: *GossipNode) !void {
        self.running.store(true, .seq_cst);
        while (self.running.load(.seq_cst)) {
            self.syncOnce() catch |err| {
                std.log.warn("gossip sync failed: {s}", .{@errorName(err)});
            };
            std.Thread.sleep(self.interval_ns);
        }
    }

    pub fn stop(self: *GossipNode) void {
        self.running.store(false, .seq_cst);
    }

    pub fn set(self: *GossipNode, key: u64, value: u64, version: u64) !void {
        _ = try self.tree.put(.{ .key = key, .value = value, .version = version });
        self.tree.recompute();
    }
};

test "merge delta and ack" {
    const alloc = std.testing.allocator;

    const Dummy = struct {
        fn send(ctx: *anyopaque, peer: Peer, delta: Delta) anyerror!Ack {
            _ = ctx;
            _ = peer;
            return .{ .seal = GENESIS_SEAL, .accepted = @intCast(delta.entries.len), .rejected = 0 };
        }
    };

    var node = GossipNode.init(alloc, 1, .{ .ctx = undefined, .sendFn = Dummy.send }, 1, 42);
    defer node.deinit();

    try node.set(10, 100, 1);
    try node.set(11, 200, 1);

    var incoming = [_]Entry{
        .{ .key = 11, .value = 999, .version = 2 },
        .{ .key = 12, .value = 300, .version = 1 },
    };
    const delta = Delta{ .seal = GENESIS_SEAL, .entries = &incoming };

    const ack = node.onReceive(delta);
    try std.testing.expectEqual(GENESIS_SEAL, ack.seal);
    try std.testing.expectEqual(@as(u64, 2), ack.accepted);
    try std.testing.expectEqual(@as(u64, 3), node.tree.map.count());
    try std.testing.expectEqual(@as(u64, 999), node.tree.map.get(11).?.value);
}

test "stale version rejected" {
    const alloc = std.testing.allocator;
    var node = GossipNode.init(alloc, 2, .{ .ctx = undefined, .sendFn = undefined }, 1, 7);
    defer node.deinit();

    try node.set(5, 50, 5);
    var stale = [_]Entry{.{ .key = 5, .value = 1, .version = 3 }};
    const ack = node.onReceive(.{ .seal = GENESIS_SEAL, .entries = &stale });
    try std.testing.expectEqual(@as(u64, 0), ack.accepted);
    try std.testing.expectEqual(@as(u64, 1), ack.rejected);
}
pub fn main() !void {}
