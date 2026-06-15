/* observe_preload.c — L1 ADVISORY evidence observer via LD_PRELOAD (Linux/glibc).
 *
 * Interposes the glibc file entry points that create/truncate or delete files and
 * appends each write-intent open / delete to $DOGFOOD_OBSERVE_LOG. A post-pass
 * (observe_preload.py) turns that log into the observed_effects record the dogfood
 * kernel's declared-vs-observed gate consumes.
 *
 * THIS IS NOT ENFORCEMENT. LD_PRELOAD is attacker-controlled user space — a static
 * binary, a direct syscall(), or a fresh execve bypass it (carcerd-defense-sandbox
 * -sprint.md). The real boundary is L2 (eBPF/seccomp), owned by the daemon track.
 * This shim only makes declared-vs-observed *checkable*.
 *
 * Build (on dev-cx53, the sanctioned Linux build target):
 *   clang -shared -fPIC -O2 -o observe_preload.so observe_preload.c -ldl
 * Use:
 *   LD_PRELOAD=$PWD/observe_preload.so DOGFOOD_OBSERVE_LOG=/tmp/obs.log <cmd>
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>

static int (*real_open)(const char *, int, ...);
static int (*real_open64)(const char *, int, ...);
static int (*real_openat)(int, const char *, int, ...);
static int (*real_creat)(const char *, mode_t);
static int (*real_unlink)(const char *);
static int (*real_unlinkat)(int, const char *, int);
static ssize_t (*real_write)(int, const void *, size_t);

static int log_fd = -2;             /* -2 = unopened, -1 = disabled */
static __thread int guard = 0;      /* per-thread recursion guard */

__attribute__((constructor))
static void init(void) {
    real_open     = dlsym(RTLD_NEXT, "open");
    real_open64   = dlsym(RTLD_NEXT, "open64");
    real_openat   = dlsym(RTLD_NEXT, "openat");
    real_creat    = dlsym(RTLD_NEXT, "creat");
    real_unlink   = dlsym(RTLD_NEXT, "unlink");
    real_unlinkat = dlsym(RTLD_NEXT, "unlinkat");
    real_write    = dlsym(RTLD_NEXT, "write");
}

static void ensure_log(void) {
    if (log_fd != -2) return;
    const char *lp = getenv("DOGFOOD_OBSERVE_LOG");
    log_fd = (lp && real_open) ? real_open(lp, O_WRONLY | O_CREAT | O_APPEND, 0644)
                               : -1;
}

/* record one event: 'W' (write-intent open) or 'D' (delete), tab, path, newline */
static void rec(char kind, const char *path) {
    if (guard || !path) return;
    guard = 1;
    ensure_log();
    if (log_fd >= 0 && real_write) {
        char buf[4352];
        int n = snprintf(buf, sizeof buf, "%c\t%s\n", kind, path);
        if (n > 0) { ssize_t w = real_write(log_fd, buf, (size_t)n); (void)w; }
    }
    guard = 0;
}

#define WR_FLAGS (O_WRONLY | O_RDWR | O_CREAT | O_TRUNC | O_APPEND)

int open(const char *path, int flags, ...) {
    mode_t m = 0;
    if (flags & O_CREAT) { va_list a; va_start(a, flags); m = va_arg(a, int); va_end(a); }
    if (flags & WR_FLAGS) rec('W', path);
    return real_open(path, flags, m);
}

int open64(const char *path, int flags, ...) {
    mode_t m = 0;
    if (flags & O_CREAT) { va_list a; va_start(a, flags); m = va_arg(a, int); va_end(a); }
    if (flags & WR_FLAGS) rec('W', path);
    return (real_open64 ? real_open64 : real_open)(path, flags, m);
}

int openat(int dfd, const char *path, int flags, ...) {
    mode_t m = 0;
    if (flags & O_CREAT) { va_list a; va_start(a, flags); m = va_arg(a, int); va_end(a); }
    if (flags & WR_FLAGS) rec('W', path);
    return real_openat(dfd, path, flags, m);
}

int creat(const char *path, mode_t m) { rec('W', path); return real_creat(path, m); }
int unlink(const char *path) { rec('D', path); return real_unlink(path); }
int unlinkat(int dfd, const char *path, int flags) {
    rec('D', path);
    return real_unlinkat(dfd, path, flags);
}
