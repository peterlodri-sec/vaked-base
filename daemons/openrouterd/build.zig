const std = @import("std");
pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const exe = b.addExecutable(.{ .name = "openrouterd", .root_module = b.createModule(.{ .root_source_file = b.path("src/main.zig"), .target = target, .optimize = optimize }) });
    b.installArtifact(exe);
    const tests = b.addTest(.{ .root_module = b.createModule(.{ .root_source_file = b.path("src/main.zig"), .target = target, .optimize = optimize }) });
    const ouroboros_tests = b.addTest(.{ .root_module = b.createModule(.{ .root_source_file = b.path("src/ouroboros.zig"), .target = target, .optimize = optimize }) });
    const matrix_tests = b.addTest(.{ .root_module = b.createModule(.{ .root_source_file = b.path("src/matrix.zig"), .target = target, .optimize = optimize }) });
    const run = b.addRunArtifact(tests);
    const run_o = b.addRunArtifact(ouroboros_tests);
    const run_m = b.addRunArtifact(matrix_tests);
    const step = b.step("test", "Run all tests");
    step.dependOn(&run.step);
    step.dependOn(&run_o.step);
    step.dependOn(&run_m.step);
}
