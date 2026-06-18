//! Synapsed P2P Mesh Protocol — Multi-Node Distributed Swarm
//! Merkle Tree + UDP Gossip + Raft-Lite Consensus
//! GENESIS_SEAL: 7c242080
const std = @import("std");
pub const PeerID = [32]u8;
pub const MerkleHash = [32]u8;
pub const NodeState = enum(u8) { Active = 0, Degraded = 1, Partitioned = 2 };
pub const LedgerSlot = extern struct { slot_id: u64, agent_id: u16, depth: u8, reserved: u8, term: u32, prev_hash: MerkleHash, payload_hash: MerkleHash, timestamp: i64 };
pub const PacketType = enum(u16) { GossipPulse = 0, MerkleRequest = 1, MerkleResponse = 2, ConsensusVote = 3 };
pub const GossipPacket = extern struct { magic: u32 = 0x594E4150, version: u16 = 1, packet_type: PacketType, sender_id: PeerID, current_term: u32, merkle_root: MerkleHash, state: NodeState, _pad: [16]u8 };

pub const SynapsedMesh = struct {
    allocator: std.mem.Allocator,
    peers: std.AutoHashMap(PeerID, u32), // address placeholder
    ledger_ptr: []LedgerSlot,
    current_term: u32,
    node_id: PeerID,

    pub fn init(a: std.mem.Allocator, mmap_plane: []u8, node_id: PeerID) !SynapsedMesh {
        const slots = @as([*]LedgerSlot, @ptrCast(@alignCast(mmap_plane.ptr)))[0..(mmap_plane.len / @sizeOf(LedgerSlot))];
        return SynapsedMesh{ .allocator = a, .peers = std.AutoHashMap(PeerID, u32).init(a), .ledger_ptr = slots, .current_term = 0, .node_id = node_id };
    }

    pub fn deinit(self: *SynapsedMesh) void { self.peers.deinit(); }

    pub fn merkleRoot(self: *const SynapsedMesh) MerkleHash {
        var h = std.crypto.hash.sha2.Sha256.init(.{});
        for (self.ledger_ptr) |slot| { if (slot.slot_id == 0) break; h.update(std.mem.asBytes(&slot.prev_hash)); h.update(std.mem.asBytes(&slot.payload_hash)); }
        var out: MerkleHash = undefined; h.final(&out); return out;
    }

    pub fn handlePulse(self: *SynapsedMesh, pkt: *const GossipPacket) bool {
        if (pkt.current_term > self.current_term) self.current_term = pkt.current_term;
        return std.mem.eql(u8, &self.merkleRoot(), &pkt.merkle_root);
    }

    pub fn writeSlot(self: *SynapsedMesh, idx: usize, slot: LedgerSlot) void { self.ledger_ptr[idx] = slot; }
};

test "init and merkle" {
    var buf: [4096]u8 = undefined; @memset(&buf, 0);
    const id = [_]u8{1} ** 32;
    var m = try SynapsedMesh.init(std.testing.allocator, &buf, id);
    defer m.deinit();
    const root = m.merkleRoot();
    try std.testing.expect(!std.mem.eql(u8, &root, &[_]u8{0} ** 32));
}

test "partition detection" {
    var buf_a: [4096]u8 = undefined; @memset(&buf_a, 0);
    var buf_b: [4096]u8 = undefined; @memset(&buf_b, 0);
    const id_a = [_]u8{1} ** 32; const id_b = [_]u8{2} ** 32;
    var ma = try SynapsedMesh.init(std.testing.allocator, &buf_a, id_a); defer ma.deinit();
    var mb = try SynapsedMesh.init(std.testing.allocator, &buf_b, id_b); defer mb.deinit();

    const root_a = ma.merkleRoot(); const root_b = mb.merkleRoot();
    try std.testing.expectEqualSlices(u8, &root_a, &root_b);

    ma.writeSlot(0, LedgerSlot{ .slot_id = 1, .agent_id = 42, .depth = 2, .payload_hash = [_]u8{0xAA} ** 32, .timestamp = 1672531199, .term = 1, .prev_hash = [_]u8{0} ** 32, .reserved = 0 });
    const mutated = ma.merkleRoot();
    try std.testing.expect(!std.mem.eql(u8, &mutated, &root_b));

    const pulse = GossipPacket{ .sender_id = id_a, .current_term = 1, .merkle_root = mutated, .state = .Active, .packet_type = .GossipPulse, ._pad = [_]u8{0} ** 16 };
    try std.testing.expect(!mb.handlePulse(&pulse));
}
