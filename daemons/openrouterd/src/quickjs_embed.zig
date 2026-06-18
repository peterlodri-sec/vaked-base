const std = @import("std");
const JSRuntime = opaque {};
const JSContext = opaque {};
const JSValue = extern struct { tag: i32, u: extern union { int32: i32, float64: f64, ptr: ?*anyopaque } };
extern "c" fn JS_NewRuntime() ?*JSRuntime;
extern "c" fn JS_NewContext(rt: ?*JSRuntime) ?*JSContext;
extern "c" fn JS_Eval(ctx: ?*JSContext, input: [*:0]const u8, len: usize, filename: [*:0]const u8, flags: i32) JSValue;
extern "c" fn JS_FreeContext(ctx: ?*JSContext) void;
extern "c" fn JS_FreeRuntime(rt: ?*JSRuntime) void;
extern "c" fn JS_ToCString(ctx: ?*JSContext, val: JSValue) ?[*:0]const u8;
extern "c" fn JS_FreeCString(ctx: ?*JSContext, ptr: [*:0]const u8) void;
const QJS = struct {
    rt: ?*JSRuntime,
    ctx: ?*JSContext,
    pub fn init() !QJS {
        const rt = JS_NewRuntime() orelse return error.QuickJSError;
        const ctx = JS_NewContext(rt) orelse {
            JS_FreeRuntime(rt);
            return error.QuickJSError;
        };
        return QJS{ .rt = rt, .ctx = ctx };
    }
    pub fn deinit(self: *QJS) void {
        JS_FreeContext(self.ctx);
        JS_FreeRuntime(self.rt);
    }
    pub fn eval(self: *QJS, allocator: std.mem.Allocator, code: []const u8) ![]const u8 {
        const c_code = try allocator.dupeZ(u8, code);
        defer allocator.free(c_code);
        const result = JS_Eval(self.ctx, c_code, code.len, "agent.js", 0);
        const c_str = JS_ToCString(self.ctx, result) orelse return error.EvalError;
        defer JS_FreeCString(self.ctx, c_str);
        return allocator.dupe(u8, std.mem.span(c_str));
    }
};
pub const LogicSandbox = struct {
    qjs: QJS,
    allocator: std.mem.Allocator,
    pub fn init(allocator: std.mem.Allocator) !LogicSandbox {
        return LogicSandbox{ .qjs = try QJS.init(), .allocator = allocator };
    }
    pub fn deinit(self: *LogicSandbox) void {
        self.qjs.deinit();
    }
    pub fn execute(self: *LogicSandbox, js_code: []const u8) ![]const u8 {
        return self.qjs.eval(self.allocator, js_code);
    }
};
test "quickjs init" {
    var qjs = try QJS.init();
    defer qjs.deinit();
}
test "quickjs eval" {
    var qjs = try QJS.init();
    defer qjs.deinit();
    const result = try qjs.eval(std.testing.allocator, "1 + 1");
    defer std.testing.allocator.free(result);
    try std.testing.expect(std.mem.eql(u8, std.mem.trim(u8, result, " \n"), "2"));
}