const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const core_mod = b.addModule("gocc-core", .{
        .root_source_file = b.path("src/arp/types.zig"),
        .target = target,
        .optimize = optimize,
    });

    const wire_mod = b.addModule("wire", .{
        .root_source_file = b.path("src/wire/frame.zig"),
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

    // shared lib (libgocc.so / libgocc.dylib) for LD_PRELOAD / DYLD_INSERT_LIBRARIES hook
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
    // macOS: include the C translation unit that provides the __DATA,__interpose
    // table.  This is the reliable write()-interpose mechanism on macOS 14+ and
    // requires a C file because Zig 0.16 cannot express runtime function
    // addresses in comptime-required linksection variable initialisers.
    // In Zig 0.16, C sources are added on the module, not the Compile step.
    if (target.result.os.tag == .macos) {
        hook_lib.root_module.addCSourceFile(.{
            .file = b.path("src/security/hook_interpose.c"),
            .flags = &.{},
        });
    }
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

    // tests — ZetaTensor frame + uring logger tests
    const uring_test_mod = b.createModule(.{
        .root_source_file = b.path("src/security/uring.zig"),
        .target = target,
        .optimize = optimize,
    });
    uring_test_mod.addImport("wire", wire_mod);
    const uring_tests = b.addTest(.{ .root_module = uring_test_mod });
    test_step.dependOn(&b.addRunArtifact(uring_tests).step);

    // tests — vault.zig (secret scanning + PoL hash + in-memory vault)
    const vault_tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/security/vault.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    test_step.dependOn(&b.addRunArtifact(vault_tests).step);

    // tests — ebpf/loader.zig (platform-conditional eBPF guard)
    const loader_tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/security/ebpf/loader.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    test_step.dependOn(&b.addRunArtifact(loader_tests).step);

    // tests — tpm.zig (TPM/SEP key sealing scaffold)
    const tpm_tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/security/tpm.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    test_step.dependOn(&b.addRunArtifact(tpm_tests).step);

    // tests — dragonfly.zig (RESP2 client + DragonflyDB state bus)
    const dragonfly_tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/state/dragonfly.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    test_step.dependOn(&b.addRunArtifact(dragonfly_tests).step);
}
