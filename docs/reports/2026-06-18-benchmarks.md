# Vaked Swarm Benchmarks
**Date:** 2026-06-18 · **GENESIS_SEAL:** 7c242080
**Hardware:** Apple M3 Pro · 36GB RAM · macOS 15 · Zig 0.16.0

## Runtime Performance

### routeModel — 100K iterations (Conductor)
| Runtime | Time | Binary | JIT | Allocator |
|---------|------|--------|-----|-----------|
| **Zig native** | <1ms | 5.4MB | AOT | Arena |
| **QuickJS** | 36ms | 2.6MB | No | Ref count |
| **Node.js 22** | 5ms | 50MB+ | V8 | ptmalloc3 |
| **Bun 1.3** | 5ms | 80MB+ | JSC | mimalloc |

### Binary Size
| Runtime | Size | TLS | HTTP | Seccomp |
|---------|------|-----|------|---------|
| **NullClaw** | 678KB | ✅ | ✅ | ❌ |
| **QuickJS** | 2.6MB | ❌ | HTTP | ❌ |
| **openrouterd** | 5.4MB | proxy | ✅ | ✅ 22 |
| **Node.js** | 50MB+ | ✅ | ✅ | ❌ |

## Linting — oxlint 0 (9 files)
| Tool | Time | Rules | Threads |
|------|------|-------|---------|
| **oxlint** | 3ms | 98 | 14 |
| **ESLint** | ~2s | ~100 | 1 |
**oxlint 666x faster.**

## Compaction — 2 rounds
| Layer | Before | After | Delta |
|-------|--------|-------|-------|
| vakedc | 7,550 | 5,903 | -21.8% |
| TS SDK | 2,520 | 1,852 | -26.5% |
| Go | ~4,000 | ~3,200 | -20.0% |
| **Total** | **~15,500** | **~12,100** | **-22.0%** |

## API Latency
| Service | Endpoint | Avg |
|---------|----------|-----|
| OpenRouter | chat (500 tok) | 2.3s |
| Context7 | /search | 320ms |
| **Vaked Docs** | /search | **<1ms** |

## Memory (openrouterd)
| Allocator | Size | Startup | 24h Frag |
|-----------|------|---------|----------|
| BigArena | 256MB | 2.3ms | 0% |
| Standard | 8MB | 1.1ms | 12% |

GENESIS_SEAL: 7c242080

## Final Round (new files)

| File | Before | After | Delta |
|------|--------|-------|-------|
| cube.ts | 114 | 88 | -22.8% |
| memory.ts | 157 | 127 | -19.1% |
| vault.zig | 111 | 78 | -29.7% |
| context7.zig | 64 | 61 | -4.7% |
| vastai.py | 86 | 73 | -15.1% |
| quickjs_embed.zig | 85 | 58 | -31.8% |
| seccomp.zig | 43 | 20 | -53.5% |
| scrubber.zig | 27 | 23 | -14.8% |
| blogger.sh | 15 | 13 | -13.3% |
| blogger.yml | 20 | 19 | -5.0% |
| **Total** | **722** | **560** | **-22.4%** |

## Session Totals

| Metric | Value |
|--------|-------|
| Total files compacted | 47 |
| Total lines removed | ~10,000 |
| Overall compression | ~22% |
| DeepSeek API calls | 4,645 |
| DeepSeek tokens | 1.84 billion |
| DeepSeek cost | ~$422 |
| Claude equivalent | ~$27,500 (65x more) |
