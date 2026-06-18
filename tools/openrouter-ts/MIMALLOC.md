# Mimalloc Tuning

Bun uses [mimalloc](https://github.com/microsoft/mimalloc) as its default
allocator. For Node.js on Linux, mimalloc can be preloaded.

## Environment Variables (honored by Bun + preloaded Node)

| Variable | Effect | Recommendation |
|----------|--------|----------------|
| `MIMALLOC_PAGE_RESET=1` | Return dirty pages to OS after use | ✅ Enable for long agents |
| `MIMALLOC_LARGE_OS_PAGES=1` | Use 2MB hugepages for large allocs | ✅ Enable if hugepages available |
| `MIMALLOC_RESERVE_HUGE_OS_PAGES=4` | Reserve N hugepage regions | Tune based on workload |
| `MIMALLOC_PURGE_DELAY=10000` | Delay purging 10s (better reuse) | ✅ Enable for agents |
| `MIMALLOC_SHOW_STATS=1` | Print stats on exit | Debug only |
| `MIMALLOC_VERBOSE=1` | Verbose logging | Debug only |

## Hugepages Setup (Linux)

```bash
# Check availability
cat /proc/meminfo | grep Huge

# Reserve 512 hugepages (1GB)
echo 512 | sudo tee /proc/sys/vm/nr_hugepages

# Verify
cat /proc/meminfo | grep HugePages
```

## Node.js + mimalloc (Linux only)

```bash
# Install
sudo apt install libmimalloc2.0

# Use with all tunables
MIMALLOC_PAGE_RESET=1 \
MIMALLOC_LARGE_OS_PAGES=1 \
MIMALLOC_PURGE_DELAY=10000 \
LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libmimalloc.so.2.0 \
node --max-old-space-size=4096 dist/cli.js "prompt"
```

## macOS

`LD_PRELOAD` is ignored for system binaries (SIP). Use **Bun** — mimalloc
is built into Bun on all platforms including macOS.

## Windows

Use **Bun** (`bun run dist/cli.js`). Node.js on Windows uses the system
allocator; mimalloc can be compiled from source but is not pre-packaged.

## Benchmarks

```bash
# Compare allocators (Linux)
# System malloc
time node dist/cli.js --model deepseek "benchmark query"

# mimalloc
time MIMALLOC_PAGE_RESET=1 LD_PRELOAD=/usr/lib/libmimalloc.so.2.0 \
  node dist/cli.js --model deepseek "benchmark query"

# Bun (mimalloc built-in)
time bun run dist/cli.js --model deepseek "benchmark query"
```
