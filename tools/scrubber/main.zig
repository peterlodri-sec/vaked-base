const std = @import("std");
const linux = std.os.linux;
const REDACTED = "[REDACTED]";
const PII = [_][]const u8{ "SECRET_KEY","CONFIDENTIAL","API_KEY","PASSWORD","TOKEN","CREDENTIAL","sk-or-v1-","sk-lf-","ctx7sk-","pk-lf-","gho_","ssh-","-----BEGIN","-----END" };
fn isPII(line: []const u8) bool { for (PII) |p| { if (std.mem.indexOf(u8,line,p)!=null) return true; } return false; }
fn scrub(a: std.mem.Allocator, input: []const u8) ![]u8 {
    var out: std.ArrayListUnmanaged(u8) = .{.items=&.{},.capacity=0};
    errdefer out.deinit(a);
    var it = std.mem.splitScalar(u8,input,'\n');
    while(it.next()) |line| {
        if(isPII(line)) { try out.appendSlice(a,REDACTED); } else { try out.appendSlice(a,line); }
        try out.append(a,'\n');
    }
    return out.toOwnedSlice(a);
}
pub fn main() !void {
    var ar = std.heap.ArenaAllocator.init(std.heap.page_allocator); defer ar.deinit();
    const a = ar.allocator();
    var in: std.ArrayListUnmanaged(u8) = .{.items=&.{},.capacity=0}; defer in.deinit(a);
    var buf: [8192]u8 = undefined;
    while(true) { const n = linux.read(0,&buf,buf.len); if(n<=0) break; try in.appendSlice(a,buf[0..@intCast(n)]); }
    const cl = try scrub(a,in.items);
    _ = linux.write(1,@ptrCast(cl.ptr),cl.len);
}