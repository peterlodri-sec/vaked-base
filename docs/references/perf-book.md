# Performance Analysis and Tuning on Modern CPUs

**Author:** Denis Bakhvalov (and contributors)  
**License:** [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Public Domain)  
**Repository:** [github.com/dendibakh/perf-book](https://github.com/dendibakh/perf-book)  
**Second Edition:** December 3, 2024

## Why this matters to Vaked

Vaked's entire architecture is built on deterministic, high-performance systems. The Zig runtime, eBPF enforcement, shared-memory arenas, and kernel-level capability checks all depend on understanding:

- CPU microarchitecture (caches, branch prediction, instruction pipelining)
- Performance monitoring (PMU counters, TMA methodology)
- Memory hierarchy optimization (cache lines, prefetching, TLB)
- SIMD and vectorization (AVX-512 on the EPYC 32-core node)
- Compiler optimizations (Zig's ReleaseFast, LTO, PGO)

This book is the definitive reference for all of these topics.

## Key chapters relevant to Vaked

1. **CPU Microarchitecture** — understanding the hardware our Zig binaries run on
2. **Performance Measurement** — methodology for benchmarking the Big Bang migration
3. **Top-Down Microarchitecture Analysis (TMA)** — identifying bottlenecks in agentic loops
4. **Memory Hierarchy** — optimizing shared-memory arena layouts
5. **SIMD and Vectorization** — leveraging the EPYC 32-core node's full potential
6. **Compiler Optimizations** — understanding what `zig build-exe -O ReleaseFast` actually does

## License

This work is dedicated to the public domain under CC0-1.0. The original repository and author are credited above. Vaked includes this reference for educational purposes — helping the swarm understand the hardware it runs on.
