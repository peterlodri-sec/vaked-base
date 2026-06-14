# vaked-mlir — Stage-1 MLIR Compiler for Vaked Topology

Stage-1 MLIR implementation of the Vaked multi-agent topology compilation pipeline.

## Overview

This directory contains the MLIR dialect definitions and compiler passes for compiling Vaked agent topologies ahead-of-time.

**Stage 0** (vakedc, Python): LPG passes that implement topology analysis, WAL injection, and AOT index generation — already done.

**Stage 1** (vaked-mlir, C++): Real MLIR dialects and passes that reproduce Stage-0 semantics for agent binary compilation.

## Structure

```
vaked-mlir/
├── include/vaked/
│   ├── VakedDialect.h          # C++ dialect header
│   ├── VakedDialect.td         # TableGen dialect definition
│   ├── VakedOps.h.inc          # (generated) Operation definitions
│   ├── VakedOps.td             # TableGen operation specs
│   ├── VakedTypes.h.inc        # (generated) Type definitions
│   └── VakedTypes.td           # TableGen type specs
├── lib/
│   └── VakedDialect.cpp        # C++ dialect implementation
├── test/                        # (future) unit tests
├── tools/                       # (future) compiler tools
├── CMakeLists.txt              # Build configuration
└── README.md                   # (this file)
```

## Building

### Prerequisites

- LLVM/MLIR 17 or later
- CMake 3.20+
- C++17 compiler

### Build Steps

```bash
# From the repo root:
mkdir -p build
cd build

# Configure with MLIR
cmake -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_DIR=<path-to-llvm-build>/lib/cmake/llvm \
  -DMLIR_DIR=<path-to-llvm-build>/lib/cmake/mlir \
  ..

# Build
ninja
```

Alternatively, if LLVM/MLIR are installed system-wide:

```bash
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release ..
ninja
```

## Design & Specification

- **0013:** MLIR umbrella, terminology, staged adoption, pipeline overview
- **0019:** vaked dialect specification (ops, types, verifier rules)
- **0020:** hcp dialect specification (WAL/registration, RFC 0004 coherent)
- **0021:** Pass 1 — topology analysis, critical-path, cycle detection
- **0022:** Pass 2 — WAL injection, structural lowering
- **0023:** Pass 3 — AOT supervisor index generation
- **0024:** Lowering contract, staged adoption, reference semantics

All specs: `/docs/language/001[3-4,9-4].md`

## Reference Implementation (Stage 0)

Stage-0 reference semantics are the normative ground truth:
- **vakedc/check.py:1670-1778** — topology analysis (Pass 1)
- **vakedc/lower.py** — WAL injection (Pass 2) and index generation (Pass 3)

Stage-1 must produce identical results on the same topologies.

## Status

**In Progress:**
- [ ] Vaked dialect TableGen (ops, types, verifier rules) — **DONE**
- [ ] Vaked dialect C++ skeleton — **DONE**
- [ ] Verifier implementation — TODO
- [ ] Pass 1 (topology analysis) — TODO
- [ ] Pass 2 (WAL injection) — TODO
- [ ] Pass 3 (AOT index generation) — TODO
- [ ] HCP dialect TableGen — TODO
- [ ] LLVM lowering — TODO
- [ ] Unit tests — TODO
- [ ] Integration tests (round-trip Stage-0 vs Stage-1) — TODO

## Testing

(When test infrastructure is in place)

```bash
# Run all tests
ctest

# Run specific test suite
ctest -R vaked-dialect-tests

# Build and run tests
ninja test
```

## Documentation

See `/docs/language/` for the full specification series:
- Grammar, type system, lowering in existing docs (0011–0018)
- MLIR topology spec in 0013–0024

## Notes

- Per project rules: **Do not build on the developer machine** (M1 MacBook). Use `dev-cx53` or CI.
- Use the 3-gate verify-confirm protocol before building on any remote target.
- All code must follow vaked project conventions (see CLAUDE.md).
