
const std = @import("std");
const linux = std.os.linux;
const Sha256 = std.crypto.hash.sha2.Sha256;

const Hash = [32]u8;

const Leaf = struct {
    key: []const u8,
    value: []const u8,
    hash: Hash,
};

fn hashKey(key: []const u8) Hash {
    var out: Hash = undefined;
    Sha256.hash(key, &out, .{});
    return out;
}

fn hashLeaf(key: []const u8, value: []const u8) Hash {
    var h = Sha256.init(.{});
    h.update(key);
    h.update(&[_]u8{0});
    h.update(value);
    var out: Hash = undefined;
    h.final(&out);
    return out;
}

fn hashNode(left: Hash, right: Hash) Hash {
    var h = Sha256.init(.{});
    h.update(&left);
    h.update(&right);
    var out: Hash = undefined;
    h.final(&out);
    return out;
}

fn cmpHash(a: Hash, b: Hash) std.math.Order {
    return std.mem.order(u8, &a, &b);
}

pub const CapabilityMerkleTree = struct {
    allocator: std.mem.Allocator,
    leaves: std.ArrayListUnmanaged(Leaf),

    pub fn init(allocator: std.mem.Allocator) CapabilityMerkleTree {
        return .{
            .allocator = allocator,
            .leaves = .{ .items = &.{}, .capacity = 0 },
        };
    }

    pub fn insert(self: *CapabilityMerkleTree, key: []const u8, value: []const u8) !void {
        const kh = hashKey(key);
        const lh = hashLeaf(key, value);
        const dup_key = try self.allocator.dupe(u8, key);
        const dup_val = try self.allocator.dupe(u8, value);

        // find insertion point (sorted by key hash)
        var idx: usize = 0;
        while (idx < self.leaves.items.len) : (idx += 1) {
            const existing_kh = hashKey(self.leaves.items[idx].key);
            const ord = cmpHash(existing_kh, kh);
            if (ord == .eq) {
                // replace existing
                self.leaves.items[idx].value = dup_val;
                self.leaves.items[idx].hash = lh;
                return;
            }
            if (ord == .gt) break;
        }

        try self.leaves.append(self.allocator, .{
            .key = dup_key,
            .value = dup_val,
            .hash = lh,
        });
        // shift to keep sorted
        var j: usize = self.leaves.items.len - 1;
        while (j > idx) : (j -= 1) {
            const tmp = self.leaves.items[j];
            self.leaves.items[j] = self.leaves.items[j - 1];
            self.leaves.items[j - 1] = tmp;
        }
    }

    pub fn get(self: *const CapabilityMerkleTree, key: []const u8) ?[]const u8 {
        const kh = hashKey(key);
        for (self.leaves.items) |leaf| {
            if (cmpHash(hashKey(leaf.key), kh) == .eq) return leaf.value;
        }
        return null;
    }

    pub fn root(self: *const CapabilityMerkleTree) !Hash {
        if (self.leaves.items.len == 0) {
            return hashKey("");
        }

        var level = std.ArrayListUnmanaged(Hash){ .items = &.{}, .capacity = 0 };
        defer level.deinit(self.allocator);

        for (self.leaves.items) |leaf| {
            try level.append(self.allocator, leaf.hash);
        }

        while (level.items.len > 1) {
            var next = std.ArrayListUnmanaged(Hash){ .items = &.{}, .capacity = 0 };
            var i: usize = 0;
            while (i < level.items.len) : (i += 2) {
                if (i + 1 < level.items.len) {
                    try next.append(self.allocator, hashNode(level.items[i], level.items[i + 1]));
                } else {
                    try next.append(self.allocator, hashNode(level.items[i], level.items[i]));
                }
            }
            level.deinit(self.allocator);
            level = next;
        }

        return level.items[0];
    }
};

pub const DeltaOp = enum { added, removed, modified };

pub const Delta = struct {
    op: DeltaOp,
    key: []const u8,
    old_value: ?[]const u8,
    new_value: ?[]const u8,
};

pub const DeltaSync = struct {
    allocator: std.mem.Allocator,
    deltas: std.ArrayListUnmanaged(Delta),

    pub fn init(allocator: std.mem.Allocator) DeltaSync {
        return .{
            .allocator = allocator,
            .deltas = .{ .items = &.{}, .capacity = 0 },
        };
    }

    pub fn compute(
        self: *DeltaSync,
        old_tree: *const CapabilityMerkleTree,
        new_tree: *const CapabilityMerkleTree,
    ) !void {
        // both leaf arrays are sorted by key hash; merge-walk
        var i: usize = 0;
        var j: usize = 0;
        const a = old_tree.leaves.items;
        const b = new_tree.leaves.items;

        while (i < a.len and j < b.len) {
            const ord = cmpHash(hashKey(a[i].key), hashKey(b[j].key));
            switch (ord) {
                .lt => {
                    try self.deltas.append(self.allocator, .{
                        .op = .removed,
                        .key = a[i].key,
                        .old_value = a[i].value,
                        .new_value = null,
                    });
                    i += 1;
                },
                .gt => {
                    try self.deltas.append(self.allocator, .{
                        .op = .added,
                        .key = b[j].key,
                        .old_value = null,
                        .new_value = b[j].value,
                    });
                    j += 1;
                },
                .eq => {
                    if (cmpHash(a[i].hash, b[j].hash) != .eq) {
                        try self.deltas.append(self.allocator, .{
                            .op = .modified,
                            .key = b[j].key,
                            .old_value = a[i].value,
                            .new_value = b[j].value,
                        });
                    }
                    i += 1;
                    j += 1;
                },
            }
        }
        while (i < a.len) : (i += 1) {
            try self.deltas.append(self.allocator, .{
                .op = .removed,
                .key = a[i].key,
                .old_value = a[i].value,
                .new_value = null,
            });
        }
        while (j < b.len) : (j += 1) {
            try self.deltas.append(self.allocator, .{
                .op = .added,
                .key = b[j].key,
                .old_value = null,
                .new_value = b[j].value,
            });
        }
    }
};

fn hexHash(allocator: std.mem.Allocator, h: Hash) ![]u8 {
    const hexchars = "0123456789abcdef";
    var out = try allocator.alloc(u8, 64);
    for (h, 0..) |byte, idx| {
        out[idx * 2] = hexchars[byte >> 4];
        out[idx * 2 + 1] = hexchars[byte & 0x0f];
    }
    return out;
}

fn appendJsonString(
    list: *std.ArrayListUnmanaged(u8),
    allocator: std.mem.Allocator,
    s: []const u8,
) !void {
    try list.append(allocator, '"');
    for (s) |c| {
        switch (c) {
            '"' => try list.appendSlice(allocator, "\\\""),
            '\\' => try list.appendSlice(allocator, "\\\\"),
            '\n' => try list.appendSlice(allocator, "\\n"),
            '\r' => try list.appendSlice(allocator, "\\r"),
            '\t' => try list.appendSlice(allocator, "\\t"),
            else => try list.append(allocator, c),
        }
    }
    try list.append(allocator, '"');
}

pub fn toJson(tree: *const CapabilityMerkleTree, allocator: std.mem.Allocator) ![]u8 {
    var buf = std.ArrayListUnmanaged(u8){ .items = &.{}, .capacity = 0 };

    try buf.appendSlice(allocator, "{\"root\":");
    const r = try tree.root();
    const rhex = try hexHash(allocator, r);
    try appendJsonString(&buf, allocator, rhex);

    try buf.appendSlice(allocator, ",\"leaves\":[");
    for (tree.leaves.items, 0..) |leaf, idx| {
        if (idx != 0) try buf.append(allocator, ',');
        try buf.appendSlice(allocator, "{\"key\":");
        try appendJsonString(&buf, allocator, leaf.key);
        try buf.appendSlice(allocator, ",\"value\":");
        try appendJsonString(&buf, allocator, leaf.value);
        try buf.appendSlice(allocator, ",\"hash\":");
        const lhex = try hexHash(allocator, leaf.hash);
        try appendJsonString(&buf, allocator, lhex);
        try buf.append(allocator, '}');
    }
    try buf.appendSlice(allocator, "]}");

    return buf.items;
}

pub fn deltaToJson(ds: *const DeltaSync, allocator: std.mem.Allocator) ![]u8 {
    var buf = std.ArrayListUnmanaged(u8){ .items = &.{}, .capacity = 0 };

    try buf.appendSlice(allocator, "{\"deltas\":[");
    for (ds.deltas.items, 0..) |d, idx| {
        if (idx != 0) try buf.append(allocator, ',');
        try buf.appendSlice(allocator, "{\"op\":");
        const op_str = switch (d.op) {
            .added => "added",
            .removed => "removed",
            .modified => "modified",
        };
        try appendJsonString(&buf, allocator, op_str);
        try buf.appendSlice(allocator, ",\"key\":");
        try appendJsonString(&buf, allocator, d.key);
        try buf.appendSlice(allocator, ",\"old\":");
        if (d.old_value) |v| {
            try appendJsonString(&buf, allocator, v);
        } else {
            try buf.appendSlice(allocator, "null");
        }
        try buf.appendSlice(allocator, ",\"new\":");
        if (d.new_value) |v| {
            try appendJsonString(&buf, allocator, v);
        } else {
            try buf.appendSlice(allocator, "null");
        }
        try buf.append(allocator, '}');
    }
    try buf.appendSlice(allocator, "]}");

    return buf.items;
}

pub fn main(init: std.process.Init) !void {
    const a = init.arena.allocator();

    var t1 = CapabilityMerkleTree.init(a);
    try t1.insert("read", "allow");
    try t1.insert("write", "deny");
    try t1.insert("exec", "allow");

    var t2 = CapabilityMerkleTree.init(a);
    try t2.insert("read", "allow");
    try t2.insert("write", "allow");
    try t2.insert("admin", "deny");

    const j1 = try toJson(&t1, a);
    std.log.info("tree1: {s}", .{j1});

    var ds = DeltaSync.init(a);
    try ds.compute(&t1, &t2);
    const dj = try deltaToJson(&ds, a);
    std.log.info("delta: {s}", .{dj});
}

