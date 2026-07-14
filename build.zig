const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const lib_mod = b.createModule(.{
        .root_source_file = b.path("lib/src/root.zig"),
        .target = target,
        .optimize = optimize,
    });

    const vakedz_mod = b.createModule(.{
        .root_source_file = b.path("vakedz/src/main.zig"),
        .target = target,
        .optimize = optimize,
    });
    vakedz_mod.addImport("lib", lib_mod);

    const vakedz = b.addExecutable(.{
        .name = "vakedz",
        .root_module = vakedz_mod,
    });
    b.installArtifact(vakedz);

    const lib_tests = b.addTest(.{ .root_module = lib_mod });
    const vakedz_tests = b.addTest(.{ .root_module = vakedz_mod });

    const test_step = b.step("test", "Run all tests");
    test_step.dependOn(&b.addRunArtifact(lib_tests).step);
    test_step.dependOn(&b.addRunArtifact(vakedz_tests).step);

    const fmt_step = b.addFmt(.{});
    b.step("check", "Format check").dependOn(&fmt_step.step);
}
