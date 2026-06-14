/*
 * hook_interpose.c — macOS dyld __DATA,__interpose section
 *
 * This thin C translation unit declares the dyld interpose table that redirects
 * calls to libSystem's write() → the Zig hook (_gocc_write_hook) exported by
 * hook.zig.
 *
 * Why a separate C file?  Zig's `export var` with linksection requires a
 * comptime-known initializer.  Function addresses are not comptime-known in
 * Zig 0.16, so the interpose struct can't be declared directly in Zig.
 * A C file has no such restriction — the linker resolves both symbols at
 * link time and the table ends up in the final dylib correctly.
 *
 * Usage (from build.zig):
 *   hook_lib.addCSourceFile(.{ .file = b.path("src/security/hook_interpose.c"), .flags = &.{} });
 */

#ifdef __APPLE__
#include <sys/types.h>
#include <unistd.h>

/* Forward-declare the Zig hook — exported as _gocc_write_hook from hook.zig */
extern ssize_t _gocc_write_hook(int fd, const void *buf, size_t count);

/* dyld interpose table entry type */
typedef struct {
    const void *replacement;
    const void *replacee;
} DyldInterposeEntry;

/*
 * Place the interpose table in __DATA,__interpose.
 * dyld reads this section before binding and redirects every call to the
 * replacee symbol → the replacement symbol, across all images in the process.
 * This is the Apple-documented mechanism (TN2085 / dyld source).
 */
__attribute__((used, section("__DATA,__interpose")))
static const DyldInterposeEntry interpose_write = {
    .replacement = (const void *)&_gocc_write_hook,
    .replacee    = (const void *)&write,
};

#endif /* __APPLE__ */
