const std = @import("std");
pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const tests = b.addTest(.{ .root_module = b.createModule(.{ .root_source_file = b.path("protocol.zig"), .target = target, .optimize = optimize }) });
    const run = b.addRunArtifact(tests);
    b.step("test", "Run synapsed tests").dependOn(&run.step);
}
