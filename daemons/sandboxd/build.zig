const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const exe_mod = b.createModule(.{
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });

    const exe = b.addExecutable(.{
        .name = "sandboxd",
        .root_module = exe_mod,
    });
    b.installArtifact(exe);

    const run = b.addRunArtifact(exe);
    if (b.args) |args| run.addArgs(args);
    const run_step = b.step("run", "Run sandboxd");
    run_step.dependOn(&run.step);

    const tests = b.addTest(.{
        .root_module = exe_mod,
    });
    const test_step = b.step("test", "Run tests");
    test_step.dependOn(&b.addRunArtifact(tests).step);

    // policy.zig + policy_test.zig: independent, negative-case policy parse tests.
    const policy_test_mod = b.createModule(.{
        .root_source_file = b.path("src/policy_test.zig"),
        .target = target,
        .optimize = optimize,
    });
    const policy_tests = b.addTest(.{
        .root_module = policy_test_mod,
    });
    test_step.dependOn(&b.addRunArtifact(policy_tests).step);
}
