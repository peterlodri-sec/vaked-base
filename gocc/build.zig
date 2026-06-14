const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const core_mod = b.addModule("gocc-core", .{
        .root_source_file = b.path("src/arp/types.zig"),
        .target = target,
        .optimize = optimize,
    });

    const exe = b.addExecutable(.{
        .name = "gocc",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    exe.root_module.addImport("gocc-core", core_mod);
    b.installArtifact(exe);

    // shared lib (libgocc.so) for LD_PRELOAD hook
    const hook_lib = b.addLibrary(.{
        .name = "gocc",
        .linkage = .dynamic,
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/security/hook.zig"),
            .target = target,
            .optimize = optimize,
            .link_libc = true,
        }),
    });
    b.installArtifact(hook_lib);

    // tests — grammar.zig tests
    const test_step = b.step("test", "Run unit tests");

    const grammar_test_mod = b.createModule(.{
        .root_source_file = b.path("src/parser/grammar.zig"),
        .target = target,
        .optimize = optimize,
    });
    grammar_test_mod.addImport("gocc-core", core_mod);
    const grammar_tests = b.addTest(.{ .root_module = grammar_test_mod });
    test_step.dependOn(&b.addRunArtifact(grammar_tests).step);

    // tests — scheduler.zig tests
    const scheduler_test_mod = b.createModule(.{
        .root_source_file = b.path("src/dispatch/scheduler.zig"),
        .target = target,
        .optimize = optimize,
    });
    scheduler_test_mod.addImport("gocc-core", core_mod);
    const scheduler_tests = b.addTest(.{ .root_module = scheduler_test_mod });
    test_step.dependOn(&b.addRunArtifact(scheduler_tests).step);
}
