const std = @import("std");

// ---- ralphloop-cache --------------------------------------------------------
//
// Cache layout:
//   <dir>/objects/<hex_sha256>        — raw AST JSON bytes
//   <dir>/parse.index.jsonl           — append-only, hash-chained JSONL
//
// Each index entry (one JSON object per line):
//   {"seq":N,"prev":"<hex_prev>","key":"<hex_source_sha256>","artifact":"parse_v0.1.0",
//    "ref":"<hex_ast_sha256>","ts_iso":"<ISO8601>","hash":"<sha256_of_entry_without_hash>"}
//
// The "prev" of the first entry is the string "genesis".
// The "hash" field is SHA-256 of the canonical JSON of all other fields concatenated
// in the order: seq, prev, key, artifact, ref, ts_iso (no hash field).

const Sha256 = std.crypto.hash.sha2.Sha256;

pub const Cache = struct {
    dir_path: []const u8,
    alloc: std.mem.Allocator,

    pub fn init(alloc: std.mem.Allocator, dir_path: []const u8) Cache {
        return .{ .dir_path = dir_path, .alloc = alloc };
    }

    pub fn deinit(self: *Cache) void {
        _ = self;
    }

    // get: check cache for source_hash, return AST bytes on hit (caller frees),
    // null on miss.
    pub fn get(self: *Cache, source_hash: [32]u8) !?[]u8 {
        const source_hex = std.fmt.bytesToHex(source_hash, .lower);
        const index_path = try std.mem.concat(self.alloc, u8, &.{ self.dir_path, "/parse.index.jsonl" });
        defer self.alloc.free(index_path);

        // Read index file; return null on not-found.
        const index_data = std.fs.cwd().readFileAlloc(self.alloc, index_path, 256 * 1024 * 1024) catch |err| {
            if (err == error.FileNotFound) return null;
            return err;
        };
        defer self.alloc.free(index_data);

        // Scan lines from END to START (newest first) to find the newest hit.
        // best_ref_owned is an allocated copy so it survives after index_data is freed.
        var best_ref_owned: ?[]u8 = null;
        {
            var line_list = std.ArrayList([]const u8).init(self.alloc);
            defer line_list.deinit();
            var lines = std.mem.splitScalar(u8, index_data, '\n');
            while (lines.next()) |line| {
                const trimmed = std.mem.trim(u8, line, " \t\r");
                if (trimmed.len == 0) continue;
                try line_list.append(trimmed);
            }
            var i: usize = line_list.items.len;
            while (i > 0) {
                i -= 1;
                const line = line_list.items[i];
                const key_val = jsonFieldStr(line, "key") orelse continue;
                if (!std.mem.eql(u8, key_val, &source_hex)) continue;
                const ref_val = jsonFieldStr(line, "ref") orelse continue;
                // dupe while index_data is still valid (defer above keeps it alive here)
                best_ref_owned = try self.alloc.dupe(u8, ref_val);
                break;
            }
        }
        // Note: index_data is freed by the defer above when this function returns.
        // best_ref_owned is a separate allocation that is valid after index_data is freed.

        if (best_ref_owned == null) return null;
        defer self.alloc.free(best_ref_owned.?);

        // Read object from objects store.
        const obj_path = try std.mem.concat(self.alloc, u8, &.{
            self.dir_path, "/objects/", best_ref_owned.?,
        });
        defer self.alloc.free(obj_path);
        const data = std.fs.cwd().readFileAlloc(self.alloc, obj_path, 256 * 1024 * 1024) catch |err| {
            if (err == error.FileNotFound) return null;
            return err;
        };
        return data;
    }

    // put: write AST bytes to objects store, append index entry.
    pub fn put(self: *Cache, source_hash: [32]u8, ast_bytes: []const u8) !void {
        // 1. Compute ref hash = SHA-256 of ast_bytes.
        var ast_h = Sha256.init(.{});
        ast_h.update(ast_bytes);
        var ast_digest: [32]u8 = undefined;
        ast_h.final(&ast_digest);
        const ref_hex = std.fmt.bytesToHex(ast_digest, .lower);
        const source_hex = std.fmt.bytesToHex(source_hash, .lower);

        // 2. Ensure objects dir exists and write the object.
        const objects_dir = try std.mem.concat(self.alloc, u8, &.{ self.dir_path, "/objects" });
        defer self.alloc.free(objects_dir);
        try std.fs.cwd().makePath(objects_dir);

        const obj_path = try std.mem.concat(self.alloc, u8, &.{ objects_dir, "/", &ref_hex });
        defer self.alloc.free(obj_path);
        // Write object file (overwrite if exists — same content).
        {
            const obj_file = try std.fs.cwd().createFile(obj_path, .{ .truncate = true });
            defer obj_file.close();
            try obj_file.writeAll(ast_bytes);
        }

        // 3. Read existing index to find prev hash and seq.
        const index_path = try std.mem.concat(self.alloc, u8, &.{ self.dir_path, "/parse.index.jsonl" });
        defer self.alloc.free(index_path);

        var seq: u64 = 1;
        var prev: []const u8 = "genesis";
        var prev_buf: [64]u8 = undefined;

        const existing_maybe: ?[]u8 = std.fs.cwd().readFileAlloc(self.alloc, index_path, 256 * 1024 * 1024) catch |err| blk: {
            if (err == error.FileNotFound) break :blk null;
            return err;
        };
        defer if (existing_maybe) |em| self.alloc.free(em);
        const existing: []const u8 = if (existing_maybe) |em| em else "";

        if (existing.len > 0) {
            // Count lines (non-empty) and find last entry's hash.
            var count: u64 = 0;
            var lines = std.mem.splitScalar(u8, existing, '\n');
            var last_hash: ?[]const u8 = null;
            while (lines.next()) |line| {
                const trimmed = std.mem.trim(u8, line, " \t\r");
                if (trimmed.len == 0) continue;
                count += 1;
                last_hash = jsonFieldStr(trimmed, "hash");
            }
            seq = count + 1;
            if (last_hash) |lh| {
                const copy_len = @min(lh.len, prev_buf.len);
                @memcpy(prev_buf[0..copy_len], lh[0..copy_len]);
                prev = prev_buf[0..copy_len];
            }
        }

        // 4. Build ISO timestamp.
        var ts_buf: [32]u8 = undefined;
        const ts: []const u8 = blk: {
            const s = isoTimestamp(self.alloc) catch {
                break :blk "1970-01-01T00:00:00Z";
            };
            defer self.alloc.free(s);
            const len = @min(s.len, ts_buf.len);
            @memcpy(ts_buf[0..len], s[0..len]);
            break :blk ts_buf[0..len];
        };

        // 5. Build the entry JSON WITHOUT the "hash" field (for hashing).
        // Format: {"seq":N,"prev":"...","key":"...","artifact":"parse_v0.1.0","ref":"...","ts_iso":"..."}
        var entry_no_hash = std.ArrayList(u8).init(self.alloc);
        defer entry_no_hash.deinit();
        const w = entry_no_hash.writer();
        try w.print(
            "{{\"seq\":{d},\"prev\":\"{s}\",\"key\":\"{s}\",\"artifact\":\"parse_v0.1.0\",\"ref\":\"{s}\",\"ts_iso\":\"{s}\"}}",
            .{ seq, prev, &source_hex, &ref_hex, ts },
        );

        // 6. Compute entry hash.
        var entry_h = Sha256.init(.{});
        entry_h.update(entry_no_hash.items);
        var entry_digest: [32]u8 = undefined;
        entry_h.final(&entry_digest);
        const entry_hex = std.fmt.bytesToHex(entry_digest, .lower);

        // 7. Build full entry JSON with "hash" field.
        var full_entry = std.ArrayList(u8).init(self.alloc);
        defer full_entry.deinit();
        const fw = full_entry.writer();
        try fw.print(
            "{{\"seq\":{d},\"prev\":\"{s}\",\"key\":\"{s}\",\"artifact\":\"parse_v0.1.0\",\"ref\":\"{s}\",\"ts_iso\":\"{s}\",\"hash\":\"{s}\"}}",
            .{ seq, prev, &source_hex, &ref_hex, ts, &entry_hex },
        );
        try full_entry.append('\n');

        // 8. Append to index file.
        try std.fs.cwd().makePath(self.dir_path);
        const idx_file = try std.fs.cwd().createFile(index_path, .{
            .truncate = false,
        });
        defer idx_file.close();
        try idx_file.seekFromEnd(0);
        try idx_file.writeAll(full_entry.items);
    }
};

// ---- Minimal JSON field extractor -------------------------------------------
// Extracts the string value of a field by name from a flat JSON object.
// Returns a slice into the original string (not allocated).
fn jsonFieldStr(json: []const u8, field: []const u8) ?[]const u8 {
    // Look for "field":"value"
    // Build the search key: "field":"
    var key_buf: [128]u8 = undefined;
    const key = std.fmt.bufPrint(&key_buf, "\"{s}\":\"", .{field}) catch return null;
    const start_idx = std.mem.indexOf(u8, json, key) orelse return null;
    const val_start = start_idx + key.len;
    // Find closing quote (handling \" escapes)
    var j = val_start;
    while (j < json.len) {
        if (json[j] == '\\') { j += 2; continue; }
        if (json[j] == '"') break;
        j += 1;
    }
    if (j >= json.len) return null;
    return json[val_start..j];
}

// ---- ISO timestamp ----------------------------------------------------------
// Computes an ISO 8601 UTC timestamp from Unix epoch seconds.
// Uses manual Gregorian calendar arithmetic — no stdlib epoch API dependency.
fn isoTimestamp(alloc: std.mem.Allocator) ![]u8 {
    const epoch_secs = std.time.timestamp();
    if (epoch_secs < 0) {
        return std.fmt.allocPrint(alloc, "1970-01-01T00:00:00Z", .{});
    }
    const ts: u64 = @intCast(epoch_secs);
    const secs_per_day: u64 = 86400;
    const days = ts / secs_per_day;
    const time_of_day = ts % secs_per_day;

    const hour = time_of_day / 3600;
    const minute = (time_of_day % 3600) / 60;
    const second = time_of_day % 60;

    // Gregorian calendar: days since 1970-01-01 → year/month/day.
    // Algorithm from https://howardhinnant.github.io/date_algorithms.html
    const z = days + 719468;
    const era = z / 146097;
    const doe = z - era * 146097;
    const yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const y = yoe + era * 400;
    const doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const mp = (5 * doy + 2) / 153;
    const d = doy - (153 * mp + 2) / 5 + 1;
    const m = if (mp < 10) mp + 3 else mp - 9;
    const year = if (m <= 2) y + 1 else y;

    return std.fmt.allocPrint(alloc, "{d:0>4}-{d:0>2}-{d:0>2}T{d:0>2}:{d:0>2}:{d:0>2}Z", .{
        year, m, d, hour, minute, second,
    });
}
