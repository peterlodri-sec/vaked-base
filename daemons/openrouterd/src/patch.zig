//! patch.zig — Atomic Patch Editor for the WIRED seccomp 22-list.
//!
//! Line-granular search/find/replace engine that edits a target file.
//! Streams in bounded chunks during the find pass to avoid loading the
//! entire file into memory when avoidable.
//!
//! ## API
//!
//!   findBlock(allocator, dir, sub_path, anchor_lines) → FindResult
//!       Locate the exact contiguous old-line block. Returns the byte
//!       range and line numbers of the unique match. Fails with NoMatch
//!       (0 matches) or MultipleMatches (>1 match).
//!
//!   applyBlock(allocator, dir, sub_path, anchor_old, new_lines) → void
//!       Find the unique match, replace it with new_lines, and write the
//!       result back to sub_path under dir. Fails with the same errors
//!       as findBlock plus I/O errors.
//!
//! ## Syscall budget
//!
//! Targets the openrouterd seccomp 22-list. Confirmed present:
//!   read(0)  write(1)  close(3)  mmap(9)  munmap(11)  openat(257)
//!
//! Confirmed absent:
//!   lseek(8)  rename(82)  ftruncate(77)  unlink(87)  stat(4)  fstat(5)
//!
//! This module uses ONLY read, write, close, and openat. No mmap, no lseek,
//! no fstat. File size is determined by reading to EOF.
//!
//! ## Atomicity (HONESTY NOTE — read before using in production)
//!
//! True atomic file replacement uses temp-file + rename(82).
//! **rename(82) is NOT in the 22-list.** This module uses an in-place
//! two-pass strategy:
//!
//!   Pass 1 (findBlock):  stream-read file in 8 KiB chunks; locate the
//!                         exact contiguous old-line block. Fail if 0 or
//!                         >1 matches. Track byte offsets and trailing
//!                         newline status.
//!
//!   Pass 2 (applyBlock): Re-open the file, stream-read it from byte 0:
//!                         copy the prefix (bytes before the match) into
//!                         an output buffer, skip over the old block,
//!                         copy the suffix (bytes after the match).
//!                         Construct the replacement from new_lines.
//!                         Open the target with O_TRUNC (a single openat
//!                         syscall; O_TRUNC is an openat flag, not a
//!                         separate ftruncate syscall) and write the
//!                         assembled output.
//!
//! **Crash safety:** a crash *before* the O_TRUNC write leaves the
//! original file intact (the find pass is read-only). A crash *during*
//! the O_TRUNC write leaves a partial or empty file. This is NOT atomic
//! in the ACID sense.
//!
//! **TOCTOU:** the file may change between Pass 1 and Pass 2. Without
//! rename-based atomic swap this race is inherent.
//!
//! ## Alternatives for production atomicity
//!
//!   (A) In-place rewrite (this module) — crash-unsafe during write.
//!   (B) Temp-file + rename — needs rename(82). Run pre-seccomp or
//!       outside the sandbox.
//!   (C) Extend the seccomp filter to include rename(82) and ftruncate(77).
//!
//! ## Assumptions
//!
//!   - Target is a regular UTF-8 text file with LF ('\n') line endings.
//!   - Lines in anchor_lines and new_lines do NOT include the '\n'.
//!   - The allocator is explicit; all allocations are freed before return.
//!   - zig test only; no build/compile/run on developer machine per CLAUDE.md.

const std = @import("std");

// ---------------------------------------------------------------------------
// Error set
// ---------------------------------------------------------------------------

pub const PatchError = error{
    /// The anchor block was not found anywhere in the file.
    NoMatch,
    /// The anchor block was found at more than one location.
    MultipleMatches,
    /// anchor_lines is empty (nothing to search for).
    InvalidAnchor,
};

// ---------------------------------------------------------------------------
// FindResult
// ---------------------------------------------------------------------------

pub const FindResult = struct {
    /// 0-indexed line number of the first matching line.
    line_start: usize,
    /// 0-indexed line number after the last matching line (= line_start + anchor_len).
    line_end: usize,
    /// Byte offset from the start of the file to the first byte of the match.
    byte_offset: usize,
    /// Total byte length of the matched block, including inter-line '\n'
    /// separators and, if present, the trailing '\n'.
    byte_len: usize,
    /// True if the matched block's last line was '\n'-terminated. False if
    /// the block ends at EOF without a trailing newline.
    trailing_newline: bool,
};

// ---------------------------------------------------------------------------
// Sliding-window line ring used by findBlock
// ---------------------------------------------------------------------------

/// One entry in the sliding window. Stores the line text (without '\n'),
/// its byte position in the file, its length including the '\n' (if any),
/// and its 0-indexed line number.
const RingEntry = struct {
    text: std.ArrayListUnmanaged(u8) = .{},
    byte_offset: usize = 0,
    byte_len: usize = 0, // includes '\n' when present
    line_number: usize = 0,
    has_newline: bool = false,

    fn deinit(entry: *RingEntry, allocator: std.mem.Allocator) void {
        entry.text.deinit(allocator);
    }

    /// Overwrite this entry with a new line, reusing its backing allocation.
    fn replace(entry: *RingEntry, allocator: std.mem.Allocator, line: []const u8, offset: usize, len: usize, lnum: usize, newline: bool) !void {
        entry.text.clearRetainingCapacity();
        try entry.text.appendSlice(allocator, line);
        entry.byte_offset = offset;
        entry.byte_len = len;
        entry.line_number = lnum;
        entry.has_newline = newline;
    }
};

/// Fixed-capacity ring buffer of RingEntry values.  When full, each
/// push overwrites the oldest entry so the window slides forward.
const LineRing = struct {
    entries: []RingEntry,
    pos: usize = 0, // next write position; when full, also the oldest entry
    fill: usize = 0,

    fn init(allocator: std.mem.Allocator, cap: usize) !LineRing {
        const entries = try allocator.alloc(RingEntry, cap);
        @memset(entries, RingEntry{});
        return .{ .entries = entries };
    }

    fn deinit(ring: *LineRing, allocator: std.mem.Allocator) void {
        for (ring.entries) |*e| e.deinit(allocator);
        allocator.free(ring.entries);
    }

    fn capacity(ring: *const LineRing) usize {
        return ring.entries.len;
    }

    fn isFull(ring: *const LineRing) bool {
        return ring.fill >= ring.capacity();
    }

    /// Push a new line into the ring. If the ring is full, the oldest entry
    /// is recycled (its text ArrayList is cleared and reused).
    fn push(ring: *LineRing, allocator: std.mem.Allocator, line: []const u8, byte_offset: usize, byte_len: usize, line_number: usize, has_newline: bool) !void {
        try ring.entries[ring.pos].replace(allocator, line, byte_offset, byte_len, line_number, has_newline);
        ring.pos = (ring.pos + 1) % ring.capacity();
        if (ring.fill < ring.capacity()) ring.fill += 1;
    }

    /// When the ring is full, returns the RingEntry pointers in
    /// chronological order (oldest → newest) for comparison against
    /// anchor_lines.
    fn ordered(ring: *const LineRing) []const RingEntry {
        std.debug.assert(ring.isFull());
        // The oldest entry is at `pos` (next to be overwritten).
        // We return a slice in ring order: ring[pos], ring[pos+1], …, ring[pos+N-1].
        // Since the caller only needs const access and the ring isn't mutated
        // during comparison, we can index directly.
        return ring.entries; // caller will index with (pos + i) % N
    }

    /// Return the RingEntry at chronological index i (0 = oldest).
    fn at(ring: *const LineRing, i: usize) *const RingEntry {
        std.debug.assert(ring.isFull());
        const idx = (ring.pos + i) % ring.capacity();
        return &ring.entries[idx];
    }
};

// ---------------------------------------------------------------------------
// findBlock
// ---------------------------------------------------------------------------

/// Locate the unique contiguous block of `anchor_lines` in the file at
/// `sub_path` under `dir`.
///
/// Reads the file in 8 KiB chunks. Maintains a sliding window of
/// `anchor_lines.len` completed lines.  When the window fills, each
/// incoming line slides the window forward and checks for a match.
///
/// Returns FindResult on exactly one match.  Returns error.NoMatch for
/// zero matches, error.MultipleMatches for >1 match, error.InvalidAnchor
/// when anchor_lines is empty.
pub fn findBlock(
    allocator: std.mem.Allocator,
    dir: std.fs.Dir,
    sub_path: []const u8,
    anchor_lines: []const []const u8,
) !FindResult {
    if (anchor_lines.len == 0) return error.InvalidAnchor;

    const file = try dir.openFile(sub_path, .{});
    defer file.close();

    var ring = try LineRing.init(allocator, anchor_lines.len);
    defer ring.deinit(allocator);

    var current_line = std.ArrayListUnmanaged(u8){};
    defer current_line.deinit(allocator);

    var line_count: usize = 0;
    var byte_cursor: usize = 0;
    var line_start_offset: usize = 0; // byte offset where current line started
    var matches = std.ArrayListUnmanaged(FindResult){};
    defer matches.deinit(allocator);

    var buf: [8192]u8 = undefined;

    while (true) {
        const n = try file.read(&buf);
        if (n == 0) break;

        var chunk = buf[0..n];
        while (chunk.len > 0) {
            if (std.mem.indexOfScalar(u8, chunk, '\n')) |nl_pos| {
                // Complete line: text is current_line + chunk[0..nl_pos]
                const prefix = current_line.items;
                const suffix = chunk[0..nl_pos];
                const full_line_len = prefix.len + suffix.len;

                // Build the complete line text
                var line_text = std.ArrayListUnmanaged(u8){};
                defer line_text.deinit(allocator);
                try line_text.appendSlice(allocator, prefix);
                try line_text.appendSlice(allocator, suffix);

                const byte_len = full_line_len + 1; // +1 for '\n'

                // Push to ring
                try ring.push(allocator, line_text.items, line_start_offset, byte_len, line_count, true);
                line_count += 1;

                // Check for match when ring is full
                if (ring.isFull()) {
                    if (checkRingMatch(&ring, anchor_lines)) |first_entry| {
                        const last_entry = ring.at(anchor_lines.len - 1);
                        const fr = FindResult{
                            .line_start = first_entry.line_number,
                            .line_end = first_entry.line_number + anchor_lines.len,
                            .byte_offset = first_entry.byte_offset,
                            .byte_len = last_entry.byte_offset + last_entry.byte_len - first_entry.byte_offset,
                            .trailing_newline = last_entry.has_newline,
                        };
                        if (matches.items.len == 1) return error.MultipleMatches;
                        try matches.append(allocator, fr);
                    }
                }

                // Advance cursor past the '\n'
                byte_cursor += byte_len;
                line_start_offset = byte_cursor;
                chunk = chunk[nl_pos + 1 ..];
                current_line.clearRetainingCapacity();
            } else {
                // No newline in this chunk; accumulate and continue to next chunk
                try current_line.appendSlice(allocator, chunk);
                byte_cursor += chunk.len;
                break; // exit inner while, read next chunk
            }
        }
    }

    // Handle last line if file doesn't end with '\n'
    if (current_line.items.len > 0) {
        const byte_len = current_line.items.len; // no trailing newline
        try ring.push(allocator, current_line.items, line_start_offset, byte_len, line_count, false);
        line_count += 1;

        if (ring.isFull()) {
            if (checkRingMatch(&ring, anchor_lines)) |first_entry| {
                const last_entry = ring.at(anchor_lines.len - 1);
                const fr = FindResult{
                    .line_start = first_entry.line_number,
                    .line_end = first_entry.line_number + anchor_lines.len,
                    .byte_offset = first_entry.byte_offset,
                    .byte_len = last_entry.byte_offset + last_entry.byte_len - first_entry.byte_offset,
                    .trailing_newline = last_entry.has_newline,
                };
                if (matches.items.len == 1) return error.MultipleMatches;
                try matches.append(allocator, fr);
            }
        }
    }

    if (matches.items.len == 0) return error.NoMatch;
    return matches.items[0];
}

/// Compare the ring's current window against anchor_lines. Returns the
/// first RingEntry of the match on success, null on mismatch.
fn checkRingMatch(ring: *const LineRing, anchor: []const []const u8) ?*const RingEntry {
    std.debug.assert(ring.isFull());
    for (0..ring.capacity()) |i| {
        const entry = ring.at(i);
        if (!std.mem.eql(u8, entry.text.items, anchor[i])) return null;
    }
    return ring.at(0);
}

// ---------------------------------------------------------------------------
// applyBlock
// ---------------------------------------------------------------------------

/// Find the unique contiguous old-line block (anchor_old_lines) in the
/// file at sub_path under dir, replace it with new_lines, and write the
/// result back.
///
/// new_lines elements do NOT include '\n'. The replacement block is
/// joined with '\n'; a trailing '\n' is appended only when the original
/// block was '\n'-terminated (see FindResult.trailing_newline).
///
/// This is a two-pass operation:
///   1. findBlock to locate the match.
///   2. Re-read the file, copy prefix + new_block + suffix into an output
///      buffer, then write back with O_TRUNC (single openat call).
pub fn applyBlock(
    allocator: std.mem.Allocator,
    dir: std.fs.Dir,
    sub_path: []const u8,
    anchor_old_lines: []const []const u8,
    new_lines: []const []const u8,
) !void {
    const match = try findBlock(allocator, dir, sub_path, anchor_old_lines);

    // ---- Pass 2: re-read and assemble output ------------------------------
    const file = try dir.openFile(sub_path, .{});
    defer file.close();

    var output = std.ArrayListUnmanaged(u8){};
    defer output.deinit(allocator);

    // 2a. Copy prefix (bytes 0 .. match.byte_offset)
    if (match.byte_offset > 0) {
        try output.resize(allocator, match.byte_offset);
        try file.reader().readNoEof(output.items[0..match.byte_offset]);
    }

    // 2b. Skip old block (match.byte_len bytes)
    {
        var remaining: usize = match.byte_len;
        var discard_buf: [8192]u8 = undefined;
        while (remaining > 0) {
            const to_read: usize = if (remaining < discard_buf.len) remaining else discard_buf.len;
            const n = try file.reader().readAtLeast(discard_buf[0..to_read], to_read);
            remaining -= n;
        }
    }

    // 2c. Copy suffix (rest of file)
    {
        var suffix_buf: [8192]u8 = undefined;
        while (true) {
            const n = try file.read(&suffix_buf);
            if (n == 0) break;
            try output.appendSlice(allocator, suffix_buf[0..n]);
        }
    }

    // ---- Build new_block bytes --------------------------------------------
    // Join new_lines with '\n'; append trailing '\n' iff original had one.
    var new_block_len: usize = 0;
    for (new_lines) |nl| new_block_len += nl.len;
    if (new_lines.len > 0) {
        new_block_len += new_lines.len - 1; // inter-line '\n'
        if (match.trailing_newline) new_block_len += 1; // trailing '\n'
    }

    // We must insert new_block after the prefix, before the suffix.
    // Strategy: use insertSlice to place it into output.
    // output currently holds [prefix][suffix]. We insert at prefix end.
    const prefix_end = match.byte_offset;
    if (new_block_len > 0) {
        try output.ensureUnusedCapacity(allocator, new_block_len);
        // Make room: shift suffix right by new_block_len
        const suffix_start = prefix_end;
        const suffix_len = output.items.len - suffix_start;
        try output.resize(allocator, output.items.len + new_block_len);
        if (suffix_len > 0) {
            std.mem.copyBackwards(u8, output.items[suffix_start + new_block_len ..], output.items[suffix_start .. suffix_start + suffix_len]);
        }
        // Write new_block into the gap
        var pos: usize = suffix_start;
        for (new_lines, 0..) |nl, i| {
            @memcpy(output.items[pos..][0..nl.len], nl);
            pos += nl.len;
            if (i < new_lines.len - 1) {
                output.items[pos] = '\n';
                pos += 1;
            }
        }
        if (match.trailing_newline and new_lines.len > 0) {
            output.items[pos] = '\n';
            pos += 1;
        }
    }

    // ---- Write back with O_TRUNC (single openat call) ---------------------
    // Note: close the read handle first to avoid any locking issues.
    file.close();

    const out = try dir.createFile(sub_path, .{});
    defer out.close();
    try out.writeAll(output.items);
}

// (tests live in patch_test.zig — run via `zig test src/patch_test.zig`)
