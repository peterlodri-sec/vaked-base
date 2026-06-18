

const std = @import("std");
const posix = std.posix;
const net = std.net;
const Ed25519 = std.crypto.sign.Ed25519;

pub const GossipError = error{
    SocketCreateFailed,
    BindFailed,
    SendFailed,
    ReceiveFailed,
    PacketTooLarge,
    PacketTooSmall,
    InvalidSignature,
    InvalidPacket,
};

pub const MAX_PACKET_SIZE = 65507;
pub const SIG_LEN = Ed25519.Signature.encoded_length;
pub const PUB_LEN = Ed25519.PublicKey.encoded_length;

pub const GossipPacket = struct {
    sender_pubkey: [PUB_LEN]u8,
    signature: [SIG_LEN]u8,
    payload: []const u8,

    pub const HEADER_LEN = PUB_LEN + SIG_LEN;

    pub fn encode(self: *const GossipPacket, buf: []u8) ![]u8 {
        const total = HEADER_LEN + self.payload.len;
        if (total > buf.len) return GossipError.PacketTooLarge;
        @memcpy(buf[0..PUB_LEN], &self.sender_pubkey);
        @memcpy(buf[PUB_LEN .. PUB_LEN + SIG_LEN], &self.signature);
        @memcpy(buf[HEADER_LEN..total], self.payload);
        return buf[0..total];
    }

    pub fn decode(data: []const u8) !GossipPacket {
        if (data.len < HEADER_LEN) return GossipError.PacketTooSmall;
        var pk: [PUB_LEN]u8 = undefined;
        var sig: [SIG_LEN]u8 = undefined;
        @memcpy(&pk, data[0..PUB_LEN]);
        @memcpy(&sig, data[PUB_LEN .. PUB_LEN + SIG_LEN]);
        return .{
            .sender_pubkey = pk,
            .signature = sig,
            .payload = data[HEADER_LEN..],
        };
    }

    pub fn verify(self: *const GossipPacket) !void {
        const pubkey = try Ed25519.PublicKey.fromBytes(self.sender_pubkey);
        const sig = Ed25519.Signature.fromBytes(self.signature);
        sig.verify(self.payload, pubkey) catch return GossipError.InvalidSignature;
    }
};

pub const MerkleDelta = struct {
    root_hash: [32]u8,
    entries: []const Entry,

    pub const Entry = struct {
        key_hash: [32]u8,
        value_hash: [32]u8,
    };

    pub fn serialize(self: *const MerkleDelta, allocator: std.mem.Allocator) ![]u8 {
        const entry_size = 64;
        const total = 32 + 4 + self.entries.len * entry_size;
        var buf = try allocator.alloc(u8, total);
        errdefer allocator.free(buf);
        @memcpy(buf[0..32], &self.root_hash);
        std.mem.writeInt(u32, buf[32..36], @intCast(self.entries.len), .little);
        var off: usize = 36;
        for (self.entries) |e| {
            @memcpy(buf[off .. off + 32], &e.key_hash);
            @memcpy(buf[off + 32 .. off + 64], &e.value_hash);
            off += entry_size;
        }
        return buf;
    }

    pub fn deserialize(allocator: std.mem.Allocator, data: []const u8) !MerkleDelta {
        if (data.len < 36) return GossipError.InvalidPacket;
        var root: [32]u8 = undefined;
        @memcpy(&root, data[0..32]);
        const count = std.mem.readInt(u32, data[32..36], .little);
        const expected = 36 + @as(usize, count) * 64;
        if (data.len < expected) return GossipError.InvalidPacket;
        var entries = try allocator.alloc(Entry, count);
        errdefer allocator.free(entries);
        var off: usize = 36;
        for (0..count) |i| {
            @memcpy(&entries[i].key_hash, data[off .. off + 32]);
            @memcpy(&entries[i].value_hash, data[off + 32 .. off + 64]);
            off += 64;
        }
        return .{ .root_hash = root, .entries = entries };
    }
};

pub const UdpGossipTransport = struct {
    allocator: std.mem.Allocator,
    sock: posix.socket_t,
    bind_addr: net.Address,
    keypair: Ed25519.KeyPair,

    const Self = @This();

    pub fn init(
        allocator: std.mem.Allocator,
        bind_addr: net.Address,
        keypair: Ed25519.KeyPair,
    ) !Self {
        const sock = posix.socket(
            bind_addr.any.family,
            posix.SOCK.DGRAM | posix.SOCK.CLOEXEC,
            posix.IPPROTO.UDP,
        ) catch return GossipError.SocketCreateFailed;
        errdefer posix.close(sock);

        try posix.setsockopt(
            sock,
            posix.SOL.SOCKET,
            posix.SO.REUSEADDR,
            &std.mem.toBytes(@as(c_int, 1)),
        );

        posix.bind(sock, &bind_addr.any, bind_addr.getOsSockLen()) catch
            return GossipError.BindFailed;

        return .{
            .allocator = allocator,
            .sock = sock,
            .bind_addr = bind_addr,
            .keypair = keypair,
        };
    }

    pub fn deinit(self: *Self) void {
        posix.close(self.sock);
    }

    pub fn publicKey(self: *const Self) [PUB_LEN]u8 {
        return self.keypair.public_key.toBytes();
    }

    pub fn gossipOnce(
        self: *Self,
        peer: net.Address,
        delta: *const MerkleDelta,
    ) !usize {
        const payload = try delta.serialize(self.allocator);
        defer self.allocator.free(payload);

        const sig = try self.keypair.sign(payload, null);

        const packet = GossipPacket{
            .sender_pubkey = self.keypair.public_key.toBytes(),
            .signature = sig.toBytes(),
            .payload = payload,
        };

        var buf: [MAX_PACKET_SIZE]u8 = undefined;
        const encoded = try packet.encode(&buf);

        const sent = posix.sendto(
            self.sock,
            encoded,
            0,
            &peer.any,
            peer.getOsSockLen(),
        ) catch return GossipError.SendFailed;

        return sent;
    }

    pub const Received = struct {
        from: net.Address,
        sender_pubkey: [PUB_LEN]u8,
        delta: MerkleDelta,
        allocator: std.mem.Allocator,

        pub fn deinit(self: *Received) void {
            self.allocator.free(self.delta.entries);
        }
    };

    pub fn receive(self: *Self) !Received {
        var buf: [MAX_PACKET_SIZE]u8 = undefined;
        var src: posix.sockaddr.storage = undefined;
        var src_len: posix.socklen_t = @sizeOf(posix.sockaddr.storage);

        const n = posix.recvfrom(
            self.sock,
            &buf,
            0,
            @ptrCast(&src),
            &src_len,
        ) catch return GossipError.ReceiveFailed;

        const packet = try GossipPacket.decode(buf[0..n]);
        try packet.verify();

        const delta = try MerkleDelta.deserialize(self.allocator, packet.payload);
        errdefer self.allocator.free(delta.entries);

        const from = net.Address.initPosix(@ptrCast(&src));

        return .{
            .from = from,
            .sender_pubkey = packet.sender_pubkey,
            .delta = delta,
            .allocator = self.allocator,
        };
    }

    pub fn setNonBlocking(self: *Self, nonblock: bool) !void {
        const flags = try posix.fcntl(self.sock, posix.F.GETFL, 0);
        var new_flags = flags;
        if (nonblock) {
            new_flags |= @as(usize, 1) << @bitOffsetOf(posix.O, "NONBLOCK");
        } else {
            new_flags &= ~(@as(usize, 1) << @bitOffsetOf(posix.O, "NONBLOCK"));
        }
        _ = try posix.fcntl(self.sock, posix.F.SETFL, new_flags);
    }
};

pub fn main() !void {}
