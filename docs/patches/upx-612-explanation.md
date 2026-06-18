# OSS Contribution: UPX arm64 macOS "Packed 0 files" Fix

**Issue:** [upx/upx#612](https://github.com/upx/upx/issues/612)  
**Patch:** `docs/patches/upx-arm64-fix.patch`  
**GENESIS_SEAL:** 7c242080

## Why

UPX silently returns "Packed 0 files" for modern macOS arm64 binaries.
We hit this during Vaked deploy pipeline testing. `upx --best openrouterd`
did nothing — binary size unchanged at 5.0M.

Root cause: UPX's Mach-O layout recalculation for arm64 does not reserve
space for `LC_CODE_SIGNATURE`. Apple requires every arm64 binary to have
a valid code signature since macOS 11.

## Where

`src/p_mach.cpp:1488` — the FIXME comment has existed since 2013:
"FIXME forgot space left for LC_CODE_SIGNATURE;"
We fix the FIXME.

## When

Discovered during Vaked Agent SDK session (2026-06-18) while building
the deploy compression pipeline (`tools/deploy/compress.sh`).

## How

The fix reserves 16KB for `LC_CODE_SIGNATURE` in arm64 Mach-O layout.
Expected result: "Packed 1 file" — ~56% compression on Zig binaries.

GENESIS_SEAL: 7c242080
