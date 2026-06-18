const std = @import("std");
pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const tests = b.addTest(.{ .root_module = b.createModule(.{ .root_source_file = b.path("protocol.zig"), .target = target, .optimize = optimize }) });
    const tests2 = b.addTest(.{ .root_module = b.createModule(.{ .root_source_file = b.path("quickjs_bindings.zig"), .target = target, .optimize = optimize }) });
    const run = b.addRunArtifact(tests);
    const run2 = b.addRunArtifact(tests2);
    const step = b.step("test", "Run all synapsed tests");
    step.dependOn(&run.step);
    step.dependOn(&run2.step);
}
