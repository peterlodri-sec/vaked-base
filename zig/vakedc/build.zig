const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const version = b.option([]const u8, "version", "Override version string") orelse "0.1.0";
    const do_strip = b.option(bool, "strip", "Strip debug symbols") orelse false;

    const options = b.addOptions();
    options.addOption([]const u8, "version", version);

    // Zig 0.16: target/optimize/root_source_file belong to the Module, not the artifact.
    const exe_mod = b.createModule(.{
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });
    exe_mod.strip = do_strip;
    exe_mod.addOptions("build_options", options);

    const exe = b.addExecutable(.{
        .name = "vakedc-zig",
        .root_module = exe_mod,
    });
    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);
    run_cmd.step.dependOn(b.getInstallStep());
    if (b.args) |args| run_cmd.addArgs(args);
    const run_step = b.step("run", "Run vakedc-zig");
    run_step.dependOn(&run_cmd.step);

    // Separate module for tests so strip doesn't affect test binaries.
    const test_mod = b.createModule(.{
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });
    test_mod.addOptions("build_options", options);

    const unit_tests = b.addTest(.{
        .root_module = test_mod,
    });

    const run_unit_tests = b.addRunArtifact(unit_tests);
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&run_unit_tests.step);
}
