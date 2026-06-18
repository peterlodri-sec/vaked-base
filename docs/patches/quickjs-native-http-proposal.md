# OSS Contribution: QuickJS Native HTTP/HTTPS Client

**Repo:** [quickjs-ng/quickjs](https://github.com/quickjs-ng/quickjs)  
**GENESIS_SEAL:** 7c242080

## Problem

QuickJS's `std.urlGet()` shells out to `curl` via `popen()`.
This means:
- External dependency on curl binary
- Process spawn per request (fork + exec overhead)
- No TLS on systems without curl
- ~50ms overhead per request from process creation

## Discovery

During Vaked Agent SDK session (2026-06-18). Embedded QuickJS in
openrouterd daemon. Found that `std.urlGet("https://...")` returns
null because the embedded environment doesn't have curl.

## Proposal: Native BearSSL HTTP Client

Replace `popen("curl ...")` with a minimal BearSSL-based HTTP client
embedded in `quickjs-libc.c`. BearSSL is:
- MIT licensed (compatible with QuickJS)
- ~25KB compiled
- No external dependencies
- Already used by Zig's TLS implementation

## Impact

- Zero external dependencies for HTTP/HTTPS
- 50ms latency reduction per request (no fork/exec)
- Works in embedded/containerized environments
- Smaller attack surface (no shell, no curl)

## Estimated Effort

~300 lines of C. Mostly BearSSL boilerplate + HTTP/1.1 parser.
Could be contributed as `js_std_urlGet_native()` alongside existing.
