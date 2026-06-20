# ultrawhale — vaked-base module

DeepSeek-native terminal coding agent, built for EPYC-Rome on NixOS. Fork of [ultrawhale](https://github.com/peterlodri-sec/ultrawhale) with aggressive performance tuning, AG-UI theming, repo map, native Go tools, async hooks, and 5 MCP servers.

## Quick Start

```sh
ssh dev-cx53
cd /home/dev/vaked-base
ultrawhale --model deepseek-v4-flash -w
```

Or with full DeepSeek optimizations:

```sh
ultrawhale --model deepseek-v4-flash --effort high -w
```

## Install

### Prerequisites
- NixOS host with Zig 0.16, Go 1.26 (via `nix develop`)
- DeepSeek API key in `~/.whale/credentials.json`
- 16+ cores recommended (EPYC-Rome or equivalent)

### Build from source

```sh
# Clone whale, build against vaked-base nix shell
git clone https://github.com/peterlodri-sec/ultrawhale.git /home/dev/whale
cd /home/dev/vaked-base
nix develop .# --command bash -c "
  cd /home/dev/whale
  export CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v3 GOMAXPROCS=16
  go build -trimpath -ldflags=\"-s -w\" -o bin/ultrawhale ./cmd/whale
"
cp /home/dev/whale/bin/ultrawhale ~/.local/bin/ultrawhale
```

### Rebuild after changes

```sh
cd /home/dev/vaked-base && nix develop .# --command bash -c "
  export CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v3 GOMAXPROCS=16
  cd /home/dev/whale
  go build -trimpath -ldflags=\"-s -w\" -o bin/ultrawhale ./cmd/whale
"
cp /home/dev/whale/bin/ultrawhale ~/.local/bin/ultrawhale
```

## What's Inside

### Binary
- **29MB static** — zero dynamic deps, `CGO_ENABLED=0`
- **GOAMD64=v3** — AVX2, BMI2, FMA for EPYC-Rome
- **1.0s build time** — Go internal linker, 16 cores

### DeepSeek Optimizations
- `reasoning_effort = "high"` — deep thought for complex tasks
- `deepseek_prefix_completion = true` — ~98% prompt cache hit
- `thinking_enabled = true` — chain-of-thought reasoning
- 1M token context window (V4 Flash)

### Plugins (4 enabled)
| Plugin | Status | What |
|--------|--------|------|
| **memory** | ✅ active | Durable session memory |
| **repomap** | ✅ active | SIMD repo map (348 MB/s, 8.7ms full scan) |
| **nats-eventbus** | ⏳ | NATS JetStream event streaming |
| **langfuse-telemetry** | ⏳ | LLM observability at langfuse.crabcc.app |

### MCP Servers (6 configured)
```
vaked-docs     — documentation search (port 9845)
vaked-rag      — semantic search (port 9876)
vaked-memory   — event-sourced memory (port 8420)
vaked-fleet    — GitHub MCP (issues, PRs, actions)
nix            — mcp-nixos (130K+ packages, 23K+ options)
vaked-daemon   — health check (port 9090)
```

### AG-UI Themes
`Ctrl+Shift+T` cycles through:
- **Dense Matrix Green** — neon green on black (#00e660)
- **Clean Graph Cyberpunk** — cyan on deep blue (#00d4ff)
- **Tactical Graveyard** — steel on dark gray (#b0b0b0)

### Workflows (5 JS scripts)
| Workflow | Command | What |
|----------|---------|------|
| pr-review | `/workflow pr-review pr=362` | Auto PR diff → security/bug/perf review |
| swe-af-fix | `/workflow swe-af-fix issue=331` | Issue → plan → implement → test → PR |
| bench-compare | `/workflow bench-compare` | Branch vs main benchmark regression check |
| release-check | `/workflow release-check version=v5.8.0` | Pre-release build/test/docs/git gate |
| repomap-rebuild | `/workflow repomap-rebuild` | Full workspace scan → symbol report |

### Agent Performance
- **128 max tool calls** per agent turn
- **64 max iterations** per agent
- **8 concurrent** workflow agents
- **Async hooks** — PostToolUse + Stop never block TUI
- **30s hook timeout** (was 600s)
- **Queued prompts capped at 32**

### tool/vack
```sh
tools/vack/vack 362    # verify PR is open, signed, no conflicts
alias vack=tools/vack/vack
```

## Files

```
vaked-base/
├── tools/vack/vack              # PR verification + sign-off tool
├── .whale/
│   ├── config                   # Build target: dev-cx53
│   ├── config.toml              # DeepSeek config + MCP permissions
│   ├── mcp.json                 # MCP server commands
│   └── workflows/               # 5 JavaScript workflow scripts
├── bin/
│   ├── vaked-build              # SSH dispatch to dev-cx53
│   ├── whale-build-ultra-v2.sh  # Production build script
│   └── whale-bench.sh           # Comparative benchmarks
├── docs/
│   └── whale-ultra-bench.html   # Self-contained benchmark report
└── repomap/                     # SIMD-accelerated repo map (8 files)
```

## Changes from upstream Whale

| Feature | Upstream | ultrawhale |
|---------|----------|------------|
| Binary size | 39MB (debug, unstripped) | 29MB (stripped, static) |
| ISA target | GOAMD64=v1 | GOAMD64=v3 (AVX2+BMI2+FMA) |
| FMA instructions | 10 | 93 (9.3x more) |
| BMI2 instructions | 659 | 1,588 (2.4x more) |
| Build time | 15.6s | 1.0s |
| Plugins | 1 (memory) | 4 (memory + repomap + nats + langfuse) |
| MCP servers | 1 | 6 |
| Workflows | 1 (deep-research) | 6 (deep-research + 5 custom) |
| Hook timeout | 600s | 30s |
| Workflow concurrency | 3 | 8 |
| Max tool calls | 30 | 128 |
| Themes | 1 (default) | 4 (default + 3 AG-UI) |
| Footer | 4-line | 1-line HUD statusline |
| API | DeepSeek only | DeepSeek + OpenRouter |

## Fork

ultrawhale is maintained as a fork of [ultrawhale](https://github.com/peterlodri-sec/ultrawhale):

```
https://github.com/peterlodri-sec/ultrawhale — vaked-base fork (v5.8.0)

---

## Blocks Engine — Content-Addressed File Primitives

Every file write in ultrawhale flows through `internal/blocks/`. Content-addressed (sha256), journaled for rollback, logged to ring buffer, dispatched through 3-tier hash engine.

### Architecture

```
blocks.Write(content)
  ├─ Tier 1: Pure Go crypto/sha256 (always available)
  ├─ Tier 2: Assembly AVX2+SHA-NI / ARMv8 NEON (auto-detected)
  ├─ Tier 3: GPU Metal / CUDA (batch >64 files)
  ├─ Journal: 16-version rollback stack per file
  └─ Logger: 4096-event ring buffer → ToastSink
```

### API

| Function | Description |
|----------|-------------|
| `Read(path)` | Ref-verified read → `*Block` |
| `Write(path, content)` | Journaled atomic write → `*Block` |
| `WriteAsync(path, content, cb)` | Non-blocking fire-and-forget |
| `Rollback(path)` | Restore previous journaled version |
| `Batch([]BatchOp)` | All-or-nothing multi-file write |

### E2E Benchmarks (16-core EPYC-Rome)

| Benchmark | Result |
|-----------|--------|
| Hash 64KB | **1,524 MB/s** |
| Write 64KB | 596 MB/s (I/O bound) |
| Batch-64 files | 3.8ms |
| Batch-256 files | 13.9ms |
| Lifecycle (write→rollback→read) | 547µs |
| Concurrent writes | 32 workers × 100 = 3,200 writes @ 0 errors |
| Race detector | `go test -race` — clean |

### Files

```
internal/blocks/     — 14 files, ~800 lines
├── block.go         — Read/Write/WriteAsync/Rollback/Batch
├── journal.go       — 16-version rollback stack
├── log.go           — Ring buffer (4096) + LogSink + ToastSink
├── hash.go          — 3-tier dispatcher
├── blocks_test.go   — 5 unit + 7 benchmarks
├── asm/             — Assembly kernels (92 lines)
│   ├── hash_amd64.s — AVX2 + SHA-NI (36 lines asm)
│   ├── hash_arm64.s — ARMv8 NEON (18 lines asm)
│   ├── hash_amd64.go
│   ├── hash_arm64.go
│   └── hash_generic.go
└── gpu/             — GPU stubs
    ├── gpu.go
    ├── metal.go
    └── gpu_stub.go
```


### Sed — SIMD Find-and-Replace

| Function | Method | Performance |
|----------|--------|-------------|
| `Sed()` | `bytes.Index` (AVX2/NEON) | Single replace |
| `SedAll()` | `bytes.Count` + SIMD loop | 257 MB/s (1KB) |
| `SedFile()` | Read→Sed→Write (journaled) | 7.25µs per file |
| `SedBatch()` | Concurrent dispatch | 98.8µs (10 files) |

Usage: `/sed find replace` — in-TUI SIMD find-and-replace. All operations journaled.

### Integration

- `file_mutation.go`: all user writes journaled via `blocks.Write()`
- ToastSink: every file operation renders as compact HUD message
- Rollback: PostToolUse hook can undo any failed write

---

## POV — Context Primitive

A `POV` (Point of View) represents the current execution context: where the agent is running, what command it is executing, and what session it belongs to.

```go
type POV struct {
    Agent    string // "ultrawhale"
    Version  string // "v5.8.0"
    Machine  string // "M1-Max" | "dev-cx53" | "hetzner-ccx33"
    Arch     string // "arm64" | "amd64"
    Tier     string // "go" | "asm" | "gpu"
    Command  string // "/reload theme cyberpunk"
    Session  string // "ultrawhale-v5.8.0-session-a1b2c3d4"
    CWD      string
    Branch   string
    Mode     string // "agent" | "ask" | "plan"
}
```

### Usage

- **LogSink**: every LogEvent carries a POV — trace which machine ran what
- **Langfuse**: POV set as trace metadata — filter by machine/arch/tier
- **HUD**: right section shows `M1·asm` or `cx53·gpu`
- **Subagents**: inherit parent POV with `Subagent: true` flag

### Plan: AG-UI Native Block Renderer

Wire `agui.RenderBlock()` into the TUI chat pipeline. Currently block rendering passes through `chat_view.go`. The plan:

1. `ChatBlock` type — wraps AG-UI `BlockType` with content + metadata
2. `chat_view.go` detects `ChatBlock` → calls `agui.RenderBlock()`
3. Block types: thinking, tool-call, tool-result, code-diff, plan-card, file-tree
4. Each block rendered with AG-UI theme colors + left accent border
5. Ctrl+Shift+T cycles theme → all rendered blocks update
```

Build from the fork:

```sh
git clone https://github.com/peterlodri-sec/ultrawhale.git /home/dev/whale
cd /home/dev/vaked-base
nix develop .# --command bash -c "
  cd /home/dev/whale
  export CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v3 GOMAXPROCS=16
  go build -trimpath -ldflags=\"-s -w\" -o bin/ultrawhale ./cmd/whale
"
```
