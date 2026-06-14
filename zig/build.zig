const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    // vaked-core: the shared library module (the Zig enforcement daemons import
    // this later — it holds the LPG data model, canonical JSON writer, and the
    // diagnostics types).
    const core_mod = b.addModule("vaked-core", .{
        .root_source_file = b.path("src/core/root.zig"),
        .target = target,
        .optimize = optimize,
    });

    // vaked-lex: the lexer module (Phase 1). Separate module so its files stay
    // within their own subtree (Zig 0.16 module boundaries). Depends on
    // vaked-core (the lexer test reuses the canonical-JSON string escaper).
    const lex_mod = b.addModule("vaked-lex", .{
        .root_source_file = b.path("src/lex/root.zig"),
        .target = target,
        .optimize = optimize,
    });
    lex_mod.addImport("vaked-core", core_mod);

    // vakedc CLI executable. NOTE: libc + sqlite linking is added in Phase 2
    // (when `parse --sqlite` lands), together with the nix linker-path fix —
    // not at scaffold time, so the scaffold builds with zero system deps.
    const exe = b.addExecutable(.{
        .name = "vakedc",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    exe.root_module.addImport("vaked-core", core_mod);
    exe.root_module.addImport("vaked-lex", lex_mod);
    b.installArtifact(exe);

    // `zig build run -- <args>`
    const run = b.addRunArtifact(exe);
    if (b.args) |args| run.addArgs(args);
    const run_step = b.step("run", "Run vakedc");
    run_step.dependOn(&run.step);

    // `zig build test` — unit tests in every module reachable from core + lex
    // + cli.
    const core_tests = b.addTest(.{ .root_module = core_mod });
    const lex_tests = b.addTest(.{ .root_module = lex_mod });
    const cli_tests = b.addTest(.{ .root_module = exe.root_module });
    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&b.addRunArtifact(core_tests).step);
    test_step.dependOn(&b.addRunArtifact(lex_tests).step);
    test_step.dependOn(&b.addRunArtifact(cli_tests).step);
}
