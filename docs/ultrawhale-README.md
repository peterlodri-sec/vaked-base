# ultrawhale — vaked-base module

DeepSeek-native terminal coding agent, built for EPYC-Rome on NixOS. Fork of [DeepSeek Code Whale](https://github.com/usewhale/DeepSeek-Code-Whale) with aggressive performance tuning, AG-UI theming, repo map, native Go tools, async hooks, and 5 MCP servers.

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
git clone https://github.com/usewhale/DeepSeek-Code-Whale.git /home/dev/whale
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
| release-check | `/workflow release-check version=v0.2.0` | Pre-release build/test/docs/git gate |
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
