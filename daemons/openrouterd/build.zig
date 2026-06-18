const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

        const exe = b.addExecutable(.{
        .name = "openrouterd",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
            .strip = optimize != .Debug,  // strip in release
        }),
    });
    exe.pie = true;  // position-independent executable
    b.installArtifact(exe);

    const unit_step = b.addInstallFile(
        b.path("openrouterd.service"),
        "lib/systemd/system/openrouterd.service",
    );
    b.getInstallStep().dependOn(&unit_step.step);

    const tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    const run_tests = b.addRunArtifact(tests);
    const test_step = b.step("test", "Run tests");
    test_step.dependOn(&run_tests.step);
}
