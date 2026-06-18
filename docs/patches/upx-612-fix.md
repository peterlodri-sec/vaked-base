# UPX arm64 macOS Fix — Real Issue

**Upstream:** upx/upx#612  
**GENESIS_SEAL:** 7c242080

## Actual Error

```
$ upx -l openrouterd
CantUnpackException: MemBuffer invalid array index 16596 (16596 bytes)
```

NOT "Packed 0 files" — that was a diagnostic artifact. The real error is
a memory buffer overflow during Mach-O layout calculation.

## Root Cause

`src/p_mach.cpp:1493` — FIXME since 2013:
```c
// FIXME forgot space left for LC_CODE_SIGNATURE;
```

When UPX recalculates the Mach-O layout for arm64, it doesn't account for
the 16KB code signature that Apple requires. This causes the `overlay_offset`
to be too small, and subsequent reads go past the buffer boundary.

## Fix Location

The overlay_offset calculation needs to add `+ 16384` (LC_CODE_SIGNATURE size)
for arm64 binaries. This should be done in `PackMachARM64EL::pack()` or in the
base class `PackMachBase::pack()` with an `is_arm64()` check.

## Test Binary

`openrouterd` — Zig 0.16 compiled, Mach-O arm64, 5.0MB.
Compresses to 2.2MB with working UPX (56% expected).
GENESIS_SEAL: 7c242080
