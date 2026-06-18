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

## Final Round — Top 5 Untouched

| File | Before | After | Delta |
|------|--------|-------|-------|
| ralph.py | 2,310 | 1,897 | -17.9% |
| check.zig (vakedz) | 1,783 | 1,558 | -12.6% |
| 0003-litany-wire.md | 1,722 | 1,295 | -24.8% |
| swe-af/main.rs | 1,361 | 1,020 | -25.1% |
| test_vakedc_check.py | 1,371 | 973 | -29.0% |
| **Total** | **8,547** | **6,743** | **-21.1%** |

All builds pass: zig ✅ python ✅ rust ✅

## Grand Session Total

| Metric | Value |
|--------|-------|
| Total files compressed | 52 |
| Total lines removed | ~11,900 |
| Overall compression | ~22% |
| DeepSeek tokens | 1.84B |
| Session cost | ~$422 |
| PRs merged | 5 |
| Builds passing | 5/5 |


## Subagent Performance (DYAD Session)

| Subagent | Steps | Tools Used | Duration | Model |
|----------|-------|------------|----------|-------|
| **Kernel Engineer** | 27 | list_dir, search_files, read_file, shell_run | 72.8s | deepseek-v4-flash |
| **Security Auditor** | 46 | read_file, shell_run, search_files | 106.7s | deepseek-v4-flash |
| **Combined** | 73 | 6 tool types | 179.5s | — |

### Per-Step Latency

| Metric | Kernel Engineer | Security Auditor |
|--------|----------------|-----------------|
| Avg step time | 2.7s | 2.3s |
| Tool calls | 25 | 38 |
| Files read | 23 | 28 |
| Shell commands | 2 | 18 |

### Tool Breakdown

| Tool | Kernel | Security | Total |
|------|--------|----------|-------|
| read_file | 17 | 18 | 35 |
| list_dir | 4 | 3 | 7 |
| search_files | 4 | 2 | 6 |
| shell_run | 2 | 15 | 17 |
| shell_wait | 0 | 3 | 3 |
| grep | 0 | 5 | 5 |

### Cost

| Subagent | Tokens | Estimated Cost |
|----------|--------|----------------|
| Kernel Engineer | ~40K | ~$0.01 |
| Security Auditor | ~151K | ~$0.04 |
| **Total** | **~191K** | **~$0.05** |

Two professional-grade code reviews for $0.05. DeepSeek V4 Flash.
