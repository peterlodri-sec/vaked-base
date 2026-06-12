//! Position-independent SHM arena primitives for shared-graph grafting (#16).
//!
//! Design (the reframe in #16, not the naive raw-pointer proposal):
//!   * TWO segments. The DATA arena is mapped READ-ONLY and is fully
//!     position-independent: it stores NO absolute pointers — only `Offset`
//!     (u64 byte-offset from the arena base) and `NodeId` (u64 content hash).
//!     Any process mmap'ing it at any base address reads it correctly.
//!   * The REFCOUNT table is a SEPARATE, writable segment: a parallel array of
//!     atomic u32 indexed by a node's `ordinal`. Graft/drop touch only this, so
//!     the data plane stays immutable + shareable (no CoW faults on reads).
//!   * "Graft" = resolve a `NodeId` and atomically bump its refcount, gated by a
//!     capability. No pointer ever crosses an address space.
//!
//! Open questions this draft takes a position on (see #16):
//!   Q1 wire format: flat tightly-packed `extern struct`s (below). Native endian
//!      (same-host SHM); cross-arch is the mesh wire path, not this.
//!   Q2 offset addressing: `NodeId` is a content hash; lookups go id -> sorted
//!      index -> `Offset`. Edges store `NodeId` (content-addressed), never raw
//!      offsets, so a node is self-describing regardless of arena placement.
//!   Q4 cap-mediated graft: `graft` takes a `GraftCap`; the daemon re-checks the
//!      node is in the cap's allowed set before bumping the refcount.

const std = @import("std");

pub const Offset = u64;
pub const NodeId = u64; // low 64 bits of the node's content hash

/// Offset 0 is the arena header, so it doubles as the null sentinel.
pub const null_offset: Offset = 0;

pub const MAGIC: [8]u8 = .{ 'V', 'K', 'D', 'S', 'H', 'M', '0', '1' };
pub const FORMAT_VERSION: u32 = 1;

/// A position-independent reference to a `[len]T` living inside the arena.
/// Resolved against the caller's mmap base — stores an offset, never a pointer.
pub fn RelSlice(comptime T: type) type {
    return extern struct {
        off: Offset = null_offset,
        len: u64 = 0,

        pub fn get(self: @This(), base: [*]const u8) []const T {
            if (self.off == null_offset or self.len == 0) return &[_]T{};
            const p: [*]const T = @ptrCast(@alignCast(base + self.off));
            return p[0..self.len];
        }
    };
}

/// Arena header at offset 0. Flat, tightly packed, native endian.
pub const Header = extern struct {
    magic: [8]u8 = MAGIC,
    format_version: u32 = FORMAT_VERSION,
    flags: u32 = 0,
    arena_len: u64 = 0,
    node_count: u64 = 0,
    /// Offset to the sorted `[node_count]IndexEntry` (id -> node offset).
    index_off: Offset = null_offset,

    pub fn valid(self: *const Header) bool {
        return std.mem.eql(u8, &self.magic, &MAGIC) and
            self.format_version == FORMAT_VERSION;
    }
};

/// One row of the id index. The index is sorted by `id` for binary search.
pub const IndexEntry = extern struct {
    id: NodeId,
    node_off: Offset,
};

/// An immutable graph node. Lives in the read-only data arena. Every reference
/// out of it is an `Offset` (blob) or a `NodeId` (edge) — never a pointer.
pub const Node = extern struct {
    id: NodeId, // content hash; matches the index key
    type_sig_hash: u64, // 0011 type signature, content-hashed
    kind: u32, // Vaked kind tag (runtime/fiber/index/...)
    _pad: u32 = 0,
    /// Index into the refcount table (the writable segment). Stable per node.
    ordinal: u64,
    /// The node's payload bytes (e.g. serialized props) inside the arena.
    data: RelSlice(u8) = .{},
    /// Outgoing edges, as content-addressed `NodeId`s (resolve via the index).
    children: RelSlice(NodeId) = .{},
};

/// A capability token the OTP control plane hands the daemon. The daemon trusts
/// the token's authenticity (validated upstream) but still re-checks that the
/// requested node is inside the granted set before grafting (defense in depth).
pub const GraftCap = struct {
    /// Sorted allowed ids; empty `allowed` with `all = true` = whole-arena grant.
    allowed: []const NodeId = &[_]NodeId{},
    all: bool = false,

    pub fn permits(self: GraftCap, id: NodeId) bool {
        if (self.all) return true;
        return std.sort.binarySearch(NodeId, self.allowed, id, cmpId) != null;
    }
};

pub const GraftError = error{ NodeNotFound, CapabilityDenied, MalformedArena };

/// A mapped arena: the read-only data segment + the writable refcount segment.
/// `base` is wherever THIS process mmap'd the data segment; nothing in the arena
/// depends on its value.
pub const Arena = struct {
    base: [*]const u8,
    len: usize,
    header: *const Header,
    /// Parallel to nodes by `ordinal`; len == header.node_count. Writable.
    refcounts: []std.atomic.Value(u32),

    pub fn init(bytes: []const u8, refcounts: []std.atomic.Value(u32)) GraftError!Arena {
        if (bytes.len < @sizeOf(Header)) return error.MalformedArena;
        const base: [*]const u8 = bytes.ptr;
        const header: *const Header = @ptrCast(@alignCast(base));
        if (!header.valid()) return error.MalformedArena;
        if (header.arena_len > bytes.len) return error.MalformedArena;
        if (refcounts.len != header.node_count) return error.MalformedArena;
        return .{ .base = base, .len = bytes.len, .header = header, .refcounts = refcounts };
    }

    fn index(self: Arena) []const IndexEntry {
        if (self.header.index_off == null_offset) return &[_]IndexEntry{};
        const p: [*]const IndexEntry = @ptrCast(@alignCast(self.base + self.header.index_off));
        return p[0..self.header.node_count];
    }

    /// O(log n) id -> node, position-independent (binary search the sorted index).
    pub fn lookup(self: Arena, id: NodeId) ?*const Node {
        const idx = self.index();
        const hit = std.sort.binarySearch(IndexEntry, idx, id, cmpEntry) orelse return null;
        return self.nodeAt(idx[hit].node_off);
    }

    pub fn nodeAt(self: Arena, off: Offset) *const Node {
        return @ptrCast(@alignCast(self.base + off));
    }

    pub fn data(self: Arena, node: *const Node) []const u8 {
        return node.data.get(self.base);
    }

    pub fn children(self: Arena, node: *const Node) []const NodeId {
        return node.children.get(self.base);
    }

    /// Capability-gated zero-copy graft: validate, then atomically bump the
    /// refcount in the writable table. Returns the read-only node view. No
    /// pointer crosses any address space — the caller already has the arena.
    pub fn graft(self: Arena, id: NodeId, cap: GraftCap) GraftError!*const Node {
        if (!cap.permits(id)) return error.CapabilityDenied;
        const node = self.lookup(id) orelse return error.NodeNotFound;
        _ = self.refcounts[node.ordinal].fetchAdd(1, .monotonic);
        return node;
    }

    /// Release a prior graft. The arena region is collectable once its refcount
    /// hits 0 (GC of the data segment is a separate pass, not done here).
    pub fn drop(self: Arena, id: NodeId) GraftError!u32 {
        const node = self.lookup(id) orelse return error.NodeNotFound;
        const prev = self.refcounts[node.ordinal].fetchSub(1, .monotonic);
        return prev - 1;
    }

    pub fn refcount(self: Arena, id: NodeId) GraftError!u32 {
        const node = self.lookup(id) orelse return error.NodeNotFound;
        return self.refcounts[node.ordinal].load(.monotonic);
    }

    // ----- snapshots / checkpoints (time-travel: Track D #20, eventd #18) ----- #
    // A snapshot pins the reachable closure of its roots so the data survives GC
    // while a runtime can rewind/jump to it. Because the arena is immutable +
    // content-addressed, a node reachable from two snapshots is pinned by BOTH
    // (refcount == 2) via structural sharing — so releasing one snapshot leaves
    // the other's view fully intact. That is the rewind-doesn't-fracture-siblings
    // guarantee #16/#20 depend on.

    /// A captured graph state: its live roots at sequence `seq`. `roots` is
    /// caller-owned (typically the runtime's live root set folded from eventd).
    pub const Snapshot = struct {
        seq: u64,
        roots: []const NodeId,
    };

    fn _walkClosure(self: Arena, id: NodeId, visited: *std.AutoHashMap(NodeId, void),
                    delta: i64) (std.mem.Allocator.Error)!void {
        if (visited.contains(id)) return;
        try visited.put(id, {});
        const node = self.lookup(id) orelse return; // dangling edge: skip (checker forbids these)
        if (delta > 0) {
            _ = self.refcounts[node.ordinal].fetchAdd(1, .monotonic);
        } else {
            _ = self.refcounts[node.ordinal].fetchSub(1, .monotonic);
        }
        for (self.children(node)) |child| {
            try self._walkClosure(child, visited, delta);
        }
    }

    /// Pin the reachable closure of `root` (refcount +1 per distinct node).
    pub fn pinClosure(self: Arena, gpa: std.mem.Allocator, root: NodeId) !void {
        var visited = std.AutoHashMap(NodeId, void).init(gpa);
        defer visited.deinit();
        try self._walkClosure(root, &visited, 1);
    }

    /// Release the reachable closure of `root` (refcount -1 per distinct node).
    pub fn unpinClosure(self: Arena, gpa: std.mem.Allocator, root: NodeId) !void {
        var visited = std.AutoHashMap(NodeId, void).init(gpa);
        defer visited.deinit();
        try self._walkClosure(root, &visited, -1);
    }

    /// Capture a snapshot: pin every root's closure, return the Snapshot.
    pub fn snapshot(self: Arena, gpa: std.mem.Allocator, seq: u64,
                    roots: []const NodeId) !Snapshot {
        for (roots) |r| try self.pinClosure(gpa, r);
        return .{ .seq = seq, .roots = roots };
    }

    /// Release a snapshot: unpin every root's closure.
    pub fn release(self: Arena, gpa: std.mem.Allocator, snap: Snapshot) !void {
        for (snap.roots) |r| try self.unpinClosure(gpa, r);
    }
};

// 0.16 binarySearch(T, items, context, compareFn): the key is the `context`,
// compareFn is fn(@TypeOf(context), T) Order.
fn cmpId(key: NodeId, elem: NodeId) std.math.Order {
    return std.math.order(key, elem);
}

fn cmpEntry(key: NodeId, e: IndexEntry) std.math.Order {
    return std.math.order(key, e.id);
}

// --------------------------------------------------------------------------- //
// Round-trip test: hand-build a 2-node arena in a buffer, then read + graft it.
// Proves the layout is position-independent (resolved purely from base+offset).
// --------------------------------------------------------------------------- //

test "arena round-trip: lookup, data, edges, capability-gated graft" {
    const t = std.testing;
    var buf: [4096]u8 = undefined;
    @memset(&buf, 0);

    // Layout: [Header][Node A][Node B][A.data][index]
    const hdr_off: Offset = 0;
    const a_off: Offset = @sizeOf(Header);
    const b_off: Offset = a_off + @sizeOf(Node);
    const adata_off: Offset = b_off + @sizeOf(Node);
    const adata = "props-of-A";
    // IndexEntry has u64 fields → 8-align the index (the real builder does this).
    const index_off: Offset = std.mem.alignForward(u64, adata_off + adata.len, 8);

    const id_a: NodeId = 0x1111;
    const id_b: NodeId = 0x2222;

    const hdr: *Header = @ptrCast(@alignCast(&buf[hdr_off]));
    hdr.* = .{ .arena_len = index_off + 2 * @sizeOf(IndexEntry), .node_count = 2, .index_off = index_off };

    const a: *Node = @ptrCast(@alignCast(&buf[a_off]));
    a.* = .{ .id = id_a, .type_sig_hash = 0xAA, .kind = 1, .ordinal = 0,
        .data = .{ .off = adata_off, .len = adata.len },
        .children = .{ .off = b_off, .len = 0 } }; // children stored as NodeIds below if len>0
    @memcpy(buf[adata_off .. adata_off + adata.len], adata);

    const b: *Node = @ptrCast(@alignCast(&buf[b_off]));
    b.* = .{ .id = id_b, .type_sig_hash = 0xBB, .kind = 2, .ordinal = 1 };

    // sorted index (id_a < id_b)
    const idx: [*]IndexEntry = @ptrCast(@alignCast(&buf[index_off]));
    idx[0] = .{ .id = id_a, .node_off = a_off };
    idx[1] = .{ .id = id_b, .node_off = b_off };

    var refs = [_]std.atomic.Value(u32){ .init(0), .init(0) };
    const arena = try Arena.init(buf[0..hdr.arena_len], refs[0..]);

    const got_a = arena.lookup(id_a) orelse return error.TestUnexpectedResult;
    try t.expectEqual(@as(u64, 0xAA), got_a.type_sig_hash);
    try t.expectEqualStrings("props-of-A", arena.data(got_a));
    try t.expect(arena.lookup(0xDEAD) == null);

    // capability-gated graft
    const cap_b_only = GraftCap{ .allowed = &[_]NodeId{id_b} };
    try t.expectError(error.CapabilityDenied, arena.graft(id_a, cap_b_only));

    const cap_all = GraftCap{ .all = true };
    _ = try arena.graft(id_a, cap_all);
    _ = try arena.graft(id_a, cap_all);
    try t.expectEqual(@as(u32, 2), try arena.refcount(id_a));
    try t.expectEqual(@as(u32, 1), try arena.drop(id_a));
}

test "snapshot closure: shared child survives releasing a sibling snapshot" {
    const t = std.testing;
    var buf: [4096]u8 = undefined;
    @memset(&buf, 0);

    // Layout: [Header][A][B][C][childcell:NodeId=C][index(3)]
    const a_off: Offset = @sizeOf(Header);
    const b_off: Offset = a_off + @sizeOf(Node);
    const c_off: Offset = b_off + @sizeOf(Node);
    const child_off: Offset = c_off + @sizeOf(Node); // 8-aligned (Node is)
    const index_off: Offset = std.mem.alignForward(u64, child_off + @sizeOf(NodeId), 8);

    const id_a: NodeId = 0x10;
    const id_b: NodeId = 0x20;
    const id_c: NodeId = 0x30;

    const hdr: *Header = @ptrCast(@alignCast(&buf[0]));
    hdr.* = .{ .arena_len = index_off + 3 * @sizeOf(IndexEntry), .node_count = 3, .index_off = index_off };

    // shared child cell: a single NodeId = C, referenced by both A and B.
    const cell: *NodeId = @ptrCast(@alignCast(&buf[child_off]));
    cell.* = id_c;
    const child_slice = RelSlice(NodeId){ .off = child_off, .len = 1 };

    const a: *Node = @ptrCast(@alignCast(&buf[a_off]));
    a.* = .{ .id = id_a, .type_sig_hash = 0, .kind = 1, .ordinal = 0, .children = child_slice };
    const b: *Node = @ptrCast(@alignCast(&buf[b_off]));
    b.* = .{ .id = id_b, .type_sig_hash = 0, .kind = 1, .ordinal = 1, .children = child_slice };
    const c: *Node = @ptrCast(@alignCast(&buf[c_off]));
    c.* = .{ .id = id_c, .type_sig_hash = 0, .kind = 2, .ordinal = 2 };

    const idx: [*]IndexEntry = @ptrCast(@alignCast(&buf[index_off]));
    idx[0] = .{ .id = id_a, .node_off = a_off };
    idx[1] = .{ .id = id_b, .node_off = b_off };
    idx[2] = .{ .id = id_c, .node_off = c_off };

    var refs = [_]std.atomic.Value(u32){ .init(0), .init(0), .init(0) };
    const arena = try Arena.init(buf[0..hdr.arena_len], refs[0..]);
    const gpa = t.allocator;

    const s_a = try arena.snapshot(gpa, 1, &[_]NodeId{id_a});
    try t.expectEqual(@as(u32, 1), try arena.refcount(id_a));
    try t.expectEqual(@as(u32, 1), try arena.refcount(id_c)); // closure pinned the child

    const s_b = try arena.snapshot(gpa, 2, &[_]NodeId{id_b});
    try t.expectEqual(@as(u32, 2), try arena.refcount(id_c)); // shared → both snapshots pin it

    try arena.release(gpa, s_a);
    try t.expectEqual(@as(u32, 0), try arena.refcount(id_a)); // A's branch released
    try t.expectEqual(@as(u32, 1), try arena.refcount(id_b)); // B untouched
    try t.expectEqual(@as(u32, 1), try arena.refcount(id_c)); // shared child SURVIVES for B

    try arena.release(gpa, s_b);
    try t.expectEqual(@as(u32, 0), try arena.refcount(id_b));
    try t.expectEqual(@as(u32, 0), try arena.refcount(id_c)); // last holder gone → collectable
}
