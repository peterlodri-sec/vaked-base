//! arena.zig — Deterministic offset-handle shared-memory arena.
//! Fixes boundary issue #16: no raw pointer ever crosses the JS<->Zig boundary.
//!
//! ASSUMPTIONS (stated explicitly, per spec):
//!   1. Backing store is a regular file (openat+write+mmap) so create()/attach()
//!      use only syscalls already in the 22-syscall seccomp allowlist.
//!      No memfd_create, no ftruncate, no shm_open.
//!   2. File extension is done by sequential write() of zero pages; this is O(n)
//!      in arena size but correct and seccomp-safe. For large arenas, pre-create
//!      the backing file with dd before calling attach().
//!   3. Single-writer discipline is enforced by the seqlock, not by an OS mutex.
//!      Multiple concurrent writers will corrupt the arena. Multiple readers are
//!      safe and lock-free.
//!   4. The arena is page-aligned and page-sized multiple (rounded up at create).
//!   5. No `@intFromPtr` or `@ptrFromInt` value is ever handed to JS. The ONLY
//!      bridge is copyOut(), which returns a fresh heap-allocated copy.
//!   6. Zig 0.16, stdlib only, x86_64-linux. No external dependencies.

const std = @import("std");
const linux = std.os.linux;
const builtin = @import("builtin");

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

/// Magic value burned into every arena header. "VKDA" = 0x41444B56 in little-endian.
pub const ARENA_MAGIC: u32 = 0x41444B56;

/// Current arena layout version. Bump when header or entry layout changes.
pub const ARENA_VERSION: u16 = 1;

/// Size of the header in bytes (exactly one cache line on x86_64).
pub const HEADER_SIZE: u32 = 64;

/// Size of one handle-table entry in bytes.
pub const HANDLE_ENTRY_SIZE: u32 = 16;

/// Allocation kind tags.
pub const Kind = enum(u8) {
    /// Free slot — never returned by resolve().
    free = 0,
    /// Control-block allocation (e.g. MemoryPlane).
    control_block = 1,
    /// Generic opaque allocation.
    generic = 2,
    _,
};

/// Handle flags (bitmask in HandleEntry.flags).
pub const HandleFlags = packed struct(u8) {
    /// Slot is free / available for reuse.
    free: bool = true,
    /// Reserved for future use.
    _pad: u7 = 0,
};

// ═══════════════════════════════════════════════════════════════════════════════
// Shared-memory layout (extern structs — must match across processes)
// ═══════════════════════════════════════════════════════════════════════════════

/// Arena header — exactly 64 bytes (one cache line).
/// Lives at offset 0 of the mmap'd region.
pub const Header = extern struct {
    /// Magic: ARENA_MAGIC. Validates the region is an arena.
    magic: u32,
    /// Layout version.
    version: u16,
    /// Padding to keep seq at offset 8.
    _pad0: u16,
    /// Total arena size in bytes (the mmap region size).
    arena_size: u32,
    /// Seqlock counter. Even = stable, odd = write in progress.
    seq: u64,
    /// Number of currently-live handles.
    handle_count: u32,
    /// Maximum number of handle slots.
    handle_cap: u32,
    /// Current heap allocation frontier (offset from arena base).
    heap_head: u32,
    /// PID of the creating process (diagnostic only, not a security check).
    owner_pid: u32,
    /// Fill to 64 bytes.
    _pad1: [28]u8,

    comptime {
        if (@sizeOf(Header) != 64) @compileError("Header must be exactly 64 bytes");
    }
};

/// One handle-table entry — 16 bytes.
pub const HandleEntry = extern struct {
    /// Offset of the allocation from the arena base.
    offset: u32,
    /// Length of the allocation in bytes.
    len: u32,
    /// Generation counter — incremented on every free() of this slot.
    generation: u32,
    /// Allocation kind (see Kind enum).
    kind: u8,
    /// Flags byte (see HandleFlags).
    flags: u8,
    /// Padding to 16 bytes.
    _pad: [2]u8,

    comptime {
        if (@sizeOf(HandleEntry) != 16) @compileError("HandleEntry must be exactly 16 bytes");
    }
};

/// An opaque handle to an arena allocation. This is the ONLY value that may
/// cross actor boundaries — it contains no pointers, only an index and a
/// generation counter.
pub const Handle = packed struct(u64) {
    /// Index into the handle table.
    index: u32,
    /// Generation counter — must match the slot's current generation.
    generation: u32,

    /// Returns an invalid/sentinel handle.
    pub fn invalid() Handle {
        return .{ .index = std.math.maxInt(u32), .generation = 0 };
    }

    /// True if this is the sentinel invalid handle.
    pub fn isInvalid(self: Handle) bool {
        return self.index == std.math.maxInt(u32);
    }
};

// ═══════════════════════════════════════════════════════════════════════════════
// Arena
// ═══════════════════════════════════════════════════════════════════════════════

pub const Arena = struct {
    /// The full mmap'd region, page-aligned.
    data: []align(std.mem.page_size) u8,
    /// File descriptor for the backing file (kept open for potential fsync).
    fd: i32,
    /// Copy of the backing path (caller-owned allocator).
    path: []const u8,

    /// Create a new file-backed arena.
    ///
    /// Uses only openat(2), write(2), mmap(2), close(2) — all in the
    /// 22-syscall seccomp allowlist. No ftruncate/memfd_create/shm_open.
    /// No fstat(5) / getpid(39) — the owner_pid is caller-supplied.
    ///
    /// total_size is rounded up to the next page boundary.
    /// max_handles determines the size of the handle table.
    /// Returns error if total_size is too small for header + handle table.
    pub fn create(
        allocator: std.mem.Allocator,
        path: []const u8,
        total_size: u32,
        max_handles: u32,
        owner_pid: u32,
    ) !Arena {
        // Round total_size up to page boundary.
        const page_size: u32 = @intCast(std.mem.page_size);
        const arena_size = std.mem.alignForward(u32, total_size, page_size);

        // Verify minimum size: header + handle table + at least 1 page of heap.
        const min_size = HEADER_SIZE + max_handles * HANDLE_ENTRY_SIZE + page_size;
        if (arena_size < min_size) return error.ArenaTooSmall;

        // Verify handle cap is reasonable.
        if (max_handles == 0) return error.ZeroHandleCap;
        if (max_handles > 1_048_576) return error.HandleCapTooLarge;

        // Open backing file with O_CREAT.
        const fd = linux.open(
            @ptrCast(path.ptr),
            linux.O.CREAT | linux.O.RDWR | linux.O.CLOEXEC,
            0o600,
        );
        if (fd < 0) return error.FileOpenFailed;

        // Extend file to arena_size by writing zero pages sequentially.
        // write(2) is the only extension mechanism available under seccomp.
        extendFile(fd, arena_size) catch |err| {
            _ = linux.close(fd);
            return err;
        };

        // mmap the file MAP_SHARED.
        const ptr = linux.mmap(
            null,
            arena_size,
            linux.PROT.READ | linux.PROT.WRITE,
            linux.MAP.SHARED,
            fd,
            0,
        );
        if (ptr == linux.MAP.FAILED) {
            _ = linux.close(fd);
            return error.MmapFailed;
        }

        const data: []align(std.mem.page_size) u8 =
            @as([*]align(std.mem.page_size) u8, @ptrCast(@alignCast(ptr)))[0..arena_size];

        // Initialize header.
        const hdr: *Header = @ptrCast(@alignCast(data.ptr));
        hdr.* = Header{
            .magic = ARENA_MAGIC,
            .version = ARENA_VERSION,
            ._pad0 = 0,
            .arena_size = arena_size,
            .seq = 0,
            .handle_count = 0,
            .handle_cap = max_handles,
            .heap_head = HEADER_SIZE + max_handles * HANDLE_ENTRY_SIZE,
            .owner_pid = owner_pid,
            ._pad1 = [_]u8{0} ** 28,
        };

        // Zero-initialize the handle table.
        const ht_start: usize = HEADER_SIZE;
        const ht_end: usize = ht_start + max_handles * HANDLE_ENTRY_SIZE;
        @memset(data[ht_start..ht_end], 0);

        const path_copy = try allocator.dupe(u8, path);

        return Arena{
            .data = data,
            .fd = @intCast(fd),
            .path = path_copy,
        };
    }

    /// Attach to an existing file-backed arena.
    ///
    /// Uses only openat(2), read(2), mmap(2), close(2) — all in the
    /// seccomp allowlist. No fstat(5) — we read the header first to
    /// discover arena_size, then mmap the full region.
    pub fn attach(allocator: std.mem.Allocator, path: []const u8) !Arena {
        const fd = linux.open(
            @ptrCast(path.ptr),
            linux.O.RDWR | linux.O.CLOEXEC,
            0,
        );
        if (fd < 0) return error.FileOpenFailed;

        // Read the header to discover arena_size.
        // Uses read(2) instead of fstat(5) to stay within the seccomp allowlist.
        var hdr_buf: [HEADER_SIZE]u8 = undefined;
        const nread = linux.read(fd, &hdr_buf, HEADER_SIZE);
        if (nread < HEADER_SIZE) {
            _ = linux.close(fd);
            return error.ArenaTooSmall;
        }
        const probe_header: *const Header = @ptrCast(@alignCast(&hdr_buf));
        if (probe_header.magic != ARENA_MAGIC) {
            _ = linux.close(fd);
            return error.InvalidMagic;
        }
        if (probe_header.version != ARENA_VERSION) {
            _ = linux.close(fd);
            return error.VersionMismatch;
        }
        const arena_size = probe_header.arena_size;
        if (arena_size < HEADER_SIZE) {
            _ = linux.close(fd);
            return error.ArenaTooSmall;
        }

        const ptr = linux.mmap(
            null,
            arena_size,
            linux.PROT.READ | linux.PROT.WRITE,
            linux.MAP.SHARED,
            fd,
            0,
        );
        if (ptr == linux.MAP.FAILED) {
            _ = linux.close(fd);
            return error.MmapFailed;
        }

        const data: []align(std.mem.page_size) u8 =
            @as([*]align(std.mem.page_size) u8, @ptrCast(@alignCast(ptr)))[0..arena_size];

        // Header already validated from the pre-mmap probe read above.
        const path_copy = try allocator.dupe(u8, path);

        return Arena{
            .data = data,
            .fd = @intCast(fd),
            .path = path_copy,
        };
    }

    /// Tear down the arena: munmap and close the backing fd.
    /// Does NOT unlink the backing file (unlink(87) is not in the seccomp allowlist).
    /// Caller is responsible for file cleanup if desired.
    pub fn deinit(self: *Arena, allocator: std.mem.Allocator) void {
        _ = linux.munmap(@ptrCast(self.data.ptr), self.data.len);
        _ = linux.close(self.fd);
        allocator.free(self.path);
        self.data = &.{};
        self.fd = -1;
        self.path = &.{};
    }

    /// Return a pointer to the shared header.
    pub fn header(self: *Arena) *Header {
        return @ptrCast(@alignCast(self.data.ptr));
    }

    /// Return a const pointer to the shared header.
    pub fn headerConst(self: *const Arena) *const Header {
        return @ptrCast(@alignCast(self.data.ptr));
    }

    /// Compute the heap origin — the byte offset where heap allocations begin.
    /// This is a fixed value: HEADER_SIZE + handle_cap * HANDLE_ENTRY_SIZE.
    pub fn heapOrigin(self: *const Arena) u32 {
        const hdr = self.headerConst();
        return HEADER_SIZE + hdr.handle_cap * HANDLE_ENTRY_SIZE;
    }

    // ── Seqlock ───────────────────────────────────────────────────────────

    /// Begin a write transaction. Returns the header pointer for mutation.
    /// Caller MUST call endWrite() after finishing writes.
    pub fn beginWrite(self: *Arena) *Header {
        const hdr = self.header();
        const current = @atomicLoad(u64, &hdr.seq, .acquire);
        if (current & 1 != 0) @panic("arena: concurrent writer detected");
        @atomicStore(u64, &hdr.seq, current + 1, .release);
        return hdr;
    }

    /// End a write transaction. Releases the seqlock.
    pub fn endWrite(self: *Arena) void {
        const hdr = self.header();
        const current = @atomicLoad(u64, &hdr.seq, .acquire);
        std.debug.assert(current & 1 == 1);
        @atomicStore(u64, &hdr.seq, current + 1, .release);
    }

    /// Begin a read transaction. Returns the sequence number at start.
    /// Caller MUST pass the returned seq to endRead().
    pub fn beginRead(self: *const Arena) u64 {
        const hdr = self.headerConst();
        var seq = @atomicLoad(u64, &hdr.seq, .acquire);
        while (seq & 1 != 0) {
            std.atomic.spinLoopHint();
            seq = @atomicLoad(u64, &hdr.seq, .acquire);
        }
        return seq;
    }

    /// End a read transaction. Returns true if the read was consistent.
    pub fn endRead(self: *const Arena, start_seq: u64) bool {
        const hdr = self.headerConst();
        const end_seq = @atomicLoad(u64, &hdr.seq, .acquire);
        return end_seq == start_seq;
    }

    // ── Allocation ────────────────────────────────────────────────────────

    /// Allocate bytes of the given kind from the bump heap.
    /// Returns a Handle (never a pointer).
    /// Uses write-lock (seqlock) — single-writer discipline.
    /// Alignment defaults to 8 bytes; use allocAligned for custom alignment.
    pub fn alloc(self: *Arena, kind: Kind, len: u32) !Handle {
        return self.allocAligned(kind, len, 8);
    }

    /// Allocate with a specific alignment.
    /// Alignment must be a power of 2.
    pub fn allocAligned(self: *Arena, kind: Kind, len: u32, alignment: u32) !Handle {
        if (len == 0) return error.ZeroLengthAlloc;
        if (alignment == 0 or !std.math.isPowerOfTwo(alignment)) return error.InvalidAlignment;

        const hdr = self.beginWrite();
        defer self.endWrite();

        // Find a free handle slot (reuse).
        var slot_index: ?u32 = null;
        const entries = self.handleTable();
        for (entries, 0..) |*entry, i| {
            const flags: HandleFlags = @bitCast(entry.flags);
            if (flags.free) {
                slot_index = @intCast(i);
                break;
            }
        }

        const idx = slot_index orelse blk: {
            if (hdr.handle_count >= hdr.handle_cap) return error.HandleTableFull;
            const i = hdr.handle_count;
            hdr.handle_count += 1;
            break :blk i;
        };

        // Align heap_head to the requested alignment.
        const offset = std.mem.alignForward(u32, hdr.heap_head, alignment);
        // Integer overflow guard.
        const new_heap_head = std.math.add(u32, offset, len) catch return error.IntegerOverflow;
        if (new_heap_head > hdr.arena_size) return error.OutOfMemory;
        hdr.heap_head = new_heap_head;

        // Write handle entry.
        const entry = &entries[idx];
        const gen = entry.generation;
        entry.* = HandleEntry{
            .offset = offset,
            .len = len,
            .generation = gen,
            .kind = @intFromEnum(kind),
            .flags = @bitCast(HandleFlags{ .free = false }),
            ._pad = [_]u8{0} ** 2,
        };

        return Handle{ .index = idx, .generation = gen };
    }

    /// Allocate and initialize a typed struct in the arena.
    /// Alignment is derived from the type's @alignOf.
    pub fn allocTyped(
        self: *Arena,
        kind: Kind,
        comptime T: type,
        init_fn: ?*const fn (*T) void,
    ) !Handle {
        const alignment: u32 = @intCast(@alignOf(T));
        const handle = try self.allocAligned(kind, @sizeOf(T), alignment);
        if (init_fn) |init| {
            const ptr = try self.resolve(handle, T);
            init(ptr);
        }
        return handle;
    }

    /// Free an allocation. Bumps generation so stale handles fail resolve().
    /// Marks the slot as free for reuse. Does NOT reclaim heap space.
    pub fn free(self: *Arena, handle: Handle) !void {
        const hdr = self.beginWrite();
        defer self.endWrite();

        const idx = handle.index;
        if (idx >= hdr.handle_cap) return error.InvalidHandle;

        const entries = self.handleTable();
        const entry = &entries[idx];

        const flags: HandleFlags = @bitCast(entry.flags);
        if (flags.free) return error.DoubleFree;
        if (entry.generation != handle.generation) return error.StaleHandle;

        // Bump generation with overflow guard.
        const new_gen = std.math.add(u32, entry.generation, 1) catch return error.GenerationOverflow;
        entry.generation = new_gen;
        entry.flags = @bitCast(HandleFlags{ .free = true });
    }

    // ── Resolution ────────────────────────────────────────────────────────

    /// Resolve a handle to a typed pointer. All safety checks applied.
    /// The returned pointer is valid ONLY within this process's address space
    /// and MUST NOT be handed to JS — use copyOut() for that.
    pub fn resolve(self: *const Arena, handle: Handle, comptime T: type) !*T {
        const bytes = try self.resolveBytes(handle);
        if (bytes.len < @sizeOf(T)) return error.SizeMismatch;
        return @ptrCast(@alignCast(bytes.ptr));
    }

    /// Core resolution: handle → byte slice with all safety checks.
    pub fn resolveBytes(self: *const Arena, handle: Handle) ![]u8 {
        const hdr = self.headerConst();

        // 1. Index bounds.
        if (handle.index >= hdr.handle_cap) return error.InvalidHandle;

        const entries = self.handleTableConst();
        const entry = &entries[handle.index];

        // 2. Generation match (use-after-free guard).
        if (entry.generation != handle.generation) return error.StaleHandle;

        // 3. Slot not free.
        const flags: HandleFlags = @bitCast(entry.flags);
        if (flags.free) return error.StaleHandle;

        // 4. Integer overflow: offset + len must not overflow u32.
        const end = std.math.add(u32, entry.offset, entry.len) catch return error.IntegerOverflow;

        // 5. Bounds: offset+len must be <= arena_size.
        if (end > hdr.arena_size) return error.OutOfBounds;

        // 6. Offset must be at or after the heap origin (guard against
        //    handles that point into the header or handle table).
        const heap_origin = self.heapOrigin();
        if (entry.offset < heap_origin) return error.OutOfBounds;

        // All checks passed. Compute pointer from base + offset.
        const base_ptr: [*]u8 = @ptrCast(self.data.ptr);
        return base_ptr[entry.offset..end];
    }

    // ── Copy-out (JS bridge) ──────────────────────────────────────────────

    /// Copy allocation contents into a fresh heap buffer.
    /// This is the ONLY function whose result may be handed to JS (as an
    /// ArrayBuffer). The returned slice is a new allocation completely
    /// disconnected from the arena's shared memory.
    pub fn copyOut(self: *const Arena, handle: Handle, allocator: std.mem.Allocator) ![]u8 {
        while (true) {
            const seq = self.beginRead();
            const bytes = self.resolveBytes(handle) catch |err| return err;
            const copy = try allocator.alloc(u8, bytes.len);
            @memcpy(copy, bytes);
            if (self.endRead(seq)) return copy;
            allocator.free(copy);
        }
    }

    /// Copy allocation contents into a caller-provided buffer.
    /// Returns the number of bytes copied. Returns error.BufferTooSmall if
    /// the buffer is too small (no partial copy).
    pub fn copyOutInto(self: *const Arena, handle: Handle, buf: []u8) !u32 {
        while (true) {
            const seq = self.beginRead();
            const bytes = self.resolveBytes(handle) catch |err| return err;
            if (buf.len < bytes.len) return error.BufferTooSmall;
            @memcpy(buf[0..bytes.len], bytes);
            if (self.endRead(seq)) return @intCast(bytes.len);
        }
    }

    // ── Handle table access (internal) ────────────────────────────────────

    fn handleTable(self: *Arena) []HandleEntry {
        const start: usize = HEADER_SIZE;
        const count = self.header().handle_cap;
        const ptr: [*]HandleEntry = @ptrCast(@alignCast(self.data[start..].ptr));
        return ptr[0..count];
    }

    fn handleTableConst(self: *const Arena) []const HandleEntry {
        const start: usize = HEADER_SIZE;
        const count = self.headerConst().handle_cap;
        const ptr: [*]const HandleEntry = @ptrCast(@alignCast(self.data[start..].ptr));
        return ptr[0..count];
    }

    // ── MemoryPlane integration ───────────────────────────────────────────

    /// Return a MemoryPlaneAccessor for a control_block handle.
    /// Caller must ensure the handle is valid and of kind .control_block.
    pub fn memoryPlane(self: *const Arena, handle: Handle) MemoryPlaneAccessor {
        return MemoryPlaneAccessor{ .arena = self, .handle = handle };
    }
};

// ═══════════════════════════════════════════════════════════════════════════════
// MemoryPlane accessor — preserves the existing layer_collapse.MemoryPlane API
// ═══════════════════════════════════════════════════════════════════════════════

/// Wraps an Arena + Handle to provide the same getter/setter methods as the
/// existing `layer_collapse.MemoryPlane` extern struct.
///
/// The underlying struct definition remains in layer_collapse.zig.
/// Reads use the arena seqlock for consistency; writes acquire the write lock.
pub const MemoryPlaneAccessor = struct {
    arena: *const Arena,
    handle: Handle,

    fn plane(self: MemoryPlaneAccessor) !*const layer_collapse.MemoryPlane {
        return self.arena.resolve(self.handle, layer_collapse.MemoryPlane);
    }

    fn planeMut(self: MemoryPlaneAccessor) !*layer_collapse.MemoryPlane {
        return self.arena.resolve(self.handle, layer_collapse.MemoryPlane);
    }

    pub fn getBudget(self: MemoryPlaneAccessor) !f64 {
        while (true) {
            const seq = self.arena.beginRead();
            const p = try self.plane();
            const val = p.budget_remaining;
            if (self.arena.endRead(seq)) return val;
        }
    }

    pub fn getTokens(self: MemoryPlaneAccessor) !u64 {
        while (true) {
            const seq = self.arena.beginRead();
            const p = try self.plane();
            const val = p.total_tokens;
            if (self.arena.endRead(seq)) return val;
        }
    }

    pub fn getModel(self: MemoryPlaneAccessor, buf: []u8) ![]const u8 {
        while (true) {
            const seq = self.arena.beginRead();
            const p = try self.plane();
            const model = std.mem.sliceTo(&p.conductor_model, 0);
            if (self.arena.endRead(seq)) {
                if (buf.len < model.len) return error.BufferTooSmall;
                @memcpy(buf[0..model.len], model);
                return buf[0..model.len];
            }
        }
    }

    pub fn getGpuStatus(self: MemoryPlaneAccessor, buf: []u8) ![]const u8 {
        while (true) {
            const seq = self.arena.beginRead();
            const p = try self.plane();
            const status = std.mem.sliceTo(&p.gpu_status, 0);
            if (self.arena.endRead(seq)) {
                if (buf.len < status.len) return error.BufferTooSmall;
                @memcpy(buf[0..status.len], status);
                return buf[0..status.len];
            }
        }
    }

    pub fn buildPassed(self: MemoryPlaneAccessor) !bool {
        while (true) {
            const seq = self.arena.beginRead();
            const p = try self.plane();
            const val = p.last_build_status == 0;
            if (self.arena.endRead(seq)) return val;
        }
    }

    pub fn updateBudget(self: MemoryPlaneAccessor, amount: f64) !void {
        _ = self.arena.beginWrite();
        defer self.arena.endWrite();
        const p = try self.planeMut();
        p.budget_remaining = amount;
    }

    pub fn updateTokens(self: MemoryPlaneAccessor, tokens: u64) !void {
        _ = self.arena.beginWrite();
        defer self.arena.endWrite();
        const p = try self.planeMut();
        p.total_tokens = tokens;
    }

    pub fn updateBuildResult(self: MemoryPlaneAccessor, passed: bool, errors: []const u8) !void {
        _ = self.arena.beginWrite();
        defer self.arena.endWrite();
        const p = try self.planeMut();
        p.last_build_status = if (passed) @as(u8, 0) else @as(u8, 1);
        @memcpy(p.last_build_errors[0..@min(errors.len, 511)], errors);
    }
};

// Import for MemoryPlane type resolution.
const layer_collapse = @import("layer_collapse.zig");

// ═══════════════════════════════════════════════════════════════════════════════
// Internal helpers
// ═══════════════════════════════════════════════════════════════════════════════

/// Extend a file to `size` bytes by writing zeros sequentially.
/// Uses only write(2) — stack-allocated zero page, no heap alloc.
/// This is O(n) but correct and seccomp-safe.
fn extendFile(fd: i32, size: u32) !void {
    const ZERO_PAGE: [4096]u8 = [_]u8{0} ** 4096;
    var written: u32 = 0;
    while (written < size) {
        const chunk: u32 = @intCast(@min(size - written, 4096));
        const n = linux.write(fd, @ptrCast(&ZERO_PAGE), chunk);
        if (n < 0) return error.FileWriteFailed;
        written += @intCast(n);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Compile-time layout checks
// ═══════════════════════════════════════════════════════════════════════════════

comptime {
    if (@sizeOf(Handle) != 8) @compileError("Handle must be exactly 8 bytes (packed u64)");
    if (HEADER_SIZE % 64 != 0) @compileError("HEADER_SIZE must be cache-line-aligned");
    if (HANDLE_ENTRY_SIZE != 16) @compileError("HANDLE_ENTRY_SIZE must be 16 bytes");
}

// ═══════════════════════════════════════════════════════════════════════════════
// Inline tests (structural, no mmap needed)
// ═══════════════════════════════════════════════════════════════════════════════

test "Handle size and layout" {
    try std.testing.expectEqual(8, @sizeOf(Handle));
    const h = Handle{ .index = 42, .generation = 7 };
    try std.testing.expectEqual(@as(u32, 42), h.index);
    try std.testing.expectEqual(@as(u32, 7), h.generation);
    try std.testing.expect(!h.isInvalid());
    try std.testing.expect(Handle.invalid().isInvalid());
}

test "Header size" {
    try std.testing.expectEqual(64, @sizeOf(Header));
}

test "HandleEntry size" {
    try std.testing.expectEqual(16, @sizeOf(HandleEntry));
}

test "Kind enum values" {
    try std.testing.expectEqual(@as(u8, 0), @intFromEnum(Kind.free));
    try std.testing.expectEqual(@as(u8, 1), @intFromEnum(Kind.control_block));
    try std.testing.expectEqual(@as(u8, 2), @intFromEnum(Kind.generic));
}
