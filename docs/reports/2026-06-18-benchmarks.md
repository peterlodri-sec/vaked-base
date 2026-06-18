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

## Linting — oxlint 0.15 (9 files)
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
