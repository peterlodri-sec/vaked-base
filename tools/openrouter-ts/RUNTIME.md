# Runtime Guide — Node.js · Bun · Deno

`@vaked/openrouter-ts` targets Node.js ≥20, Bun ≥1.1, and Deno ≥2.0.

## Quick Start

```bash
# Node.js (default)
npm run build && npm run orcli "your prompt"

# Bun (faster startup, mimalloc by default)
bun run dist/cli.js "your prompt"

# Deno
deno run --allow-env --allow-net --allow-read dist/cli.js "your prompt"
```

## Allocator

| Runtime | Allocator | Notes |
|---------|-----------|-------|
| **Bun** | **mimalloc** | Built-in. No config needed. Best choice for long-running agents. |
| **Node.js** | ptmalloc3 (macOS) / glibc malloc (Linux) | Use `--max-old-space-size` to tune. For mimalloc on Linux: `LD_PRELOAD=/usr/lib/libmimalloc.so` |
| **Deno** | jemalloc (Linux) / system (macOS) | Generally better than Node default. No config needed. |

**Recommendation:** Use **Bun** for production agents — mimalloc reduces fragmentation during long agent loops with many allocations.

## Node.js Tuning

### Heap

```bash
# 4GB heap (default in npm scripts)
node --max-old-space-size=4096 dist/cli.js

# 8GB for large-context models (Claude 200k)
node --max-old-space-size=8192 dist/cli.js

# Conservative (512MB) for cheap/fast queries
node --max-old-space-size=512 dist/cli.js --model deepseek "quick question"
```

### GC

```bash
# Expose GC for manual control (benchmarking)
node --expose-gc dist/cli.js

# Aggressive GC for memory-constrained environments
node --max-semi-space-size=16 --max-old-space-size=512 dist/cli.js
```

### Other useful flags

```bash
# Source maps for debugging
NODE_OPTIONS="--enable-source-maps"

# Optimize for throughput (default)
NODE_OPTIONS="--optimize-for-size"    # prefer memory over speed

# Experimental VM modules (rarely needed)
NODE_OPTIONS="--experimental-vm-modules"
```

### Environment

```bash
export NODE_OPTIONS="--max-old-space-size=4096 --enable-source-maps"
npm run orcli "prompt"
```

## Bun Tuning

```bash
# Smol mode — optimize for memory (good for background agents)
bun run --smol dist/cli.js

# High memory ceiling (Bun defaults to half of system RAM)
bun run --max-old-space-size=8192 dist/cli.js
```

Bun uses mimalloc internally — **no `LD_PRELOAD` needed.**

## Deno Tuning

```bash
# Permissions (minimum needed)
deno run \
  --allow-env=OPENROUTER_API_KEY,CONTEXT7_API_KEY,HOME \
  --allow-net=openrouter.ai,context7.com \
  --allow-read=$HOME/.orcli_budget,$HOME/.deepseek_cache.json \
  dist/cli.js "prompt"
```

## Linux mimalloc (Node.js only)

For Node.js on Linux, mimalloc can be preloaded:

```bash
# Install
sudo apt install libmimalloc2.0    # Debian/Ubuntu
# or build from source: https://github.com/microsoft/mimalloc

# Use
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libmimalloc.so.2.0 \
node --max-old-space-size=4096 dist/cli.js "prompt"

# With env var
MIMALLOC_LARGE_OS_PAGES=1 \
LD_PRELOAD=/usr/lib/libmimalloc.so \
node dist/cli.js
```

Note: On macOS, `LD_PRELOAD` is ignored for system binaries (SIP). Use Bun for mimalloc on macOS.

## Benchmarking

```bash
# Node.js
npm run bench "Write a Zig 0.16 HTTP server" -- --model claude

# Bun (fastest startup)
npm run bench:bun "Write a Zig 0.16 HTTP server" -- --model claude

# With GC exposure
node --expose-gc --max-old-space-size=4096 dist/cli.js "prompt"
```

## Genesis

```
GENESIS_SEAL: 7c242080
```
