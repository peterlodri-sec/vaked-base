const std = @import("std");
pub const JSContext = u8;
pub const JSValue = u64;
pub extern fn JS_GetOpaque(val: JSValue, tag: u32) ?*anyopaque;
pub extern fn JS_ThrowInternalError(ctx: *JSContext, fmt: [*]const u8, ...) JSValue;
pub const MemoryPlaneProxy = struct {
    pub fn jsMapMemoryPlanePointer(ctx: *JSContext, this_val: JSValue, _: c_int, _: [*]JSValue) callconv(.C) JSValue {
        const raw_ptr = JS_GetOpaque(this_val, 0x7C242080) orelse return JS_ThrowInternalError(ctx, "MemoryPlane corrupted");
        return @intFromPtr(raw_ptr);
    }
};
test "extern" { try std.testing.expect(@TypeOf(JS_GetOpaque) == fn (JSValue, u32) ?*anyopaque); }
