# ultrawhale — vaked-base coding agent

DeepSeek-native terminal coding agent, built for EPYC-Rome on NixOS. Fork of [DeepSeek Code Whale](https://github.com/usewhale/DeepSeek-Code-Whale) with aggressive performance tuning, AG-UI theming, repo map, native Go tools, deep hooks, superpowers plugin, and 5 MCP servers.

## Quick Start

### Linux (dev-cx53)

```sh
ssh dev-cx53
cd /home/dev/vaked-base
ultrawhale --model deepseek-v4-flash -w
```

### macOS (Apple Silicon — M1/M2/M3/M4)

```sh
cd vaked-base
./bin/ultrawhale --model deepseek-v4-flash -w
```

Or with full DeepSeek optimizations:

```sh
ultrawhale --model deepseek-v4-flash --effort high -w
```

## Install

### Prerequisites
- **Linux:** NixOS host with Go 1.26. 16+ cores recommended (EPYC-Rome).
- **macOS:** Apple Silicon (M1+) with Go 1.26. ARM64 NEON SIMD — native performance.
- DeepSeek API key in `~/.whale/credentials.json`

### Build from source (Linux → macOS cross-compile)

```sh
# On dev-cx53, cross-compile for Apple Silicon
cd /home/dev/vaked-base && nix develop .# --command bash -c "
  cd /home/dev/whale
  export CGO_ENABLED=0 GOOS=darwin GOARCH=arm64
  go build -trimpath -ldflags=\"-s -w\" -o bin/ultrawhale-darwin-arm64 ./cmd/whale
"
# scp dev-cx53:/home/dev/whale/bin/ultrawhale-darwin-arm64 ~/.local/bin/ultrawhale
```

### Build from source (macOS native)

```sh
cd vaked-base
go build -trimpath -ldflags="-s -w" -o bin/ultrawhale ./cmd/whale
./bin/ultrawhale --model deepseek-v4-flash -w
```

### Build from source (Linux native)

```sh
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

---

## Binary

| Metric | Value |
|--------|-------|
| **Size** | 30MB static |
| **Compiler** | Go 1.26, CGO_ENABLED=0 |
| **ISA** | GOAMD64=v3 (AVX2, BMI2, FMA) |
| **Build time** | ~1.0s (Go internal linker, 16 cores) |
| **Dynamic deps** | Zero — statically linked |

## DeepSeek Optimizations

| Feature | Config | Effect |
|---------|--------|--------|
| **Reasoning effort** | `reasoning_effort = "high"` | Deep chain-of-thought for complex tasks |
| **Prefix completion** | `deepseek_prefix_completion = true` | ~98% prompt cache hit → pennies per session |
| **Thinking** | `thinking_enabled = true` | Explicit reasoning before code generation |
| **Context window** | 1M tokens | V4 Flash native |

---

## Plugins (5 enabled)

| Plugin | Status | Description |
|--------|--------|-------------|
| **memory** | ✅ active | Durable session memory across conversations |
| **repomap** | ✅ active | SIMD repo map — 348 MB/s, 8.7ms full scan |
| **nats-eventbus** | ⏳ needs NATS | JetStream event streaming for agent fleet |
| **langfuse-telemetry** | ⏳ needs API key | LLM observability at langfuse.crabcc.app |
| **superpowers** | ✅ active | Auto-discovers bao secrets, wires infra |

---

## Hooks (10 events, 9 async)

| Event | Sync/Async | Fires on | Plugins |
|-------|-----------|----------|---------|
| **SessionStart** | Async | New session | superpowers, repomap |
| **PrePromptSubmit** | Async | Before LLM call | repomap (injects map) |
| **PreToolUse** | Async | Before tool exec | nats, langfuse |
| **PostToolUse** | Async | After tool completes | repomap, nats, langfuse |
| **PostResponse** | Async | After LLM responds | langfuse |
| **Error** | Async | Tool/API/timeout failure | superpowers, repomap |
| **Idle** | Async | 120s inactivity | background refresh |
| **Stop** | Async | Session ends | langfuse, nats, superpowers |
| **ModeSwitch** | Async | agent/ask/plan toggle | telemetry |
| **PermissionRequest** | Sync | Tool needs approval | approval gate |

**Features:** Priority ordering (0-100), metrics counters per hook, `/reload hooks` display, 30s default timeout (was 600s).

---

## TUI Commands

| Command | What it does |
|---------|-------------|
| `/reload all` | Hot-reload plugins + config + repomap + workflows |
| `/reload status` | Show plugins, theme, model, uptime |
| `/reload doctor` | Show model, effort, thinking, mode, branch |
| `/reload hooks` | Display active hooks with call counts and last run |
| `/reload theme dense` | Switch to Dense Matrix Green theme |
| `/reload theme cyberpunk` | Switch to Clean Graph Cyberpunk |
| `/reload theme graveyard` | Switch to Tactical Graveyard |
| `Ctrl+Shift+T` | Cycle through AG-UI themes |
| `Shift+Tab` | Cycle agent mode (agent → ask → plan) |
| `Ctrl+C` | Interrupt running turn |

---

## HUD Statusline

Single-row status bar replacing the 4-line footer:

```
[deepseek-v4-flash]  ⎇ main     ● 2:35 · 4821t · 85/s · ⎆98%   bao·lf·nats·2GPU  342MB · $0.0142 · ⚙5
```

**Left:** model · mode badge · git branch  
**Center:** busy timer · token count · tok/s · cache hit %  
**Right:** infra indicators (bao/lf/nats/GPU) · memory · cost · plugins · theme

---

## AG-UI Themes

`Ctrl+Shift+T` or `/reload theme <name>` cycles through:

| Theme | Background | Accent | Vibe |
|-------|-----------|--------|------|
| **Dense Matrix Green** | `#040804` | `#00e660` | Neon terminal |
| **Clean Graph Cyberpunk** | `#0a0a14` | `#00d4ff` | Cyberpunk neon |
| **Tactical Graveyard** | `#141414` | `#b0b0b0` | Minimal grayscale |

Shader: animated Perlin-noise background using Unicode block chars (░▒▓█). Zero allocations after init.

---

## MCP Servers (6 configured)

| Server | Port | Description |
|--------|------|-------------|
| **vaked-docs** | 9845 | Documentation index, no rate limits |
| **vaked-rag** | 9876 | Semantic search across all docs |
| **vaked-memory** | 8420 | Event-sourced memory plane |
| **vaked-fleet** | — | GitHub MCP (issues, PRs, actions) |
| **nix** | — | mcp-nixos (130K+ packages, 23K+ options) |
| **vaked-daemon** | 9090 | Health check |

---

## Workflows (5 JS scripts)

| Workflow | Trigger | What |
|----------|---------|------|
| `pr-review` | `/workflow pr-review pr=362` | Auto PR diff → security/bug/perf review |
| `swe-af-fix` | `/workflow swe-af-fix issue=331` | Issue → plan → implement → test → PR |
| `bench-compare` | `/workflow bench-compare` | Branch vs main benchmark regression check |
| `release-check` | `/workflow release-check version=v0.2.0` | Pre-release build/test/docs/git gate |
| `repomap-rebuild` | `/workflow repomap-rebuild` | Full workspace scan → symbol report |

**Config:** `max_concurrency = 8`, `enabled = true`, `keyword_trigger_enabled = true`

---

## Agent Performance

| Setting | Value |
|---------|-------|
| Max tool calls per turn | 128 |
| Max iterations per agent | 64 |
| Concurrent workflow agents | 8 |
| Queued prompts cap | 32 |
| Hook timeout | 30s (was 600s) |
| Subagent budget | 250,000 tokens default |

---

## Native Go Tools

| Package | Replaces | Speed vs shell exec |
|---------|----------|---------------------|
| `native/gh.go` | `gh pr list`, `gh issue view` | 10x (HTTP API vs subprocess) |
| `native/grep.go` | `rg pattern` | 20x (SIMD bytes.Index vs fork) |
| `native/git.go` | `git status`, `git log`, `git diff` | 4x (less fork overhead) |

---

## Tools

| Tool | File | Purpose |
|------|------|---------|
| **vack** | `tools/vack/vack` | PR verification — checks open, signed, no conflicts |

```sh
alias vack=tools/vack/vack
vack 362    # → ✅ MERGE OK / error with fix instructions
```

---

## Files

```
vaked-base/
├── tools/vack/vack               # PR verification + sign-off tool
├── .whale/
│   ├── config                    # Build target: dev-cx53
│   ├── config.toml               # DeepSeek config + MCP permissions
│   ├── mcp.json                  # MCP server commands
│   └── workflows/                # 5 JavaScript workflow scripts
├── bin/
│   ├── vaked-build               # SSH dispatch to dev-cx53
│   ├── whale-build-ultra-v2.sh   # Production build script
│   └── whale-bench.sh            # Comparative benchmarks
├── docs/
│   └── whale-ultra-bench.html    # Self-contained benchmark report
├── repomap/                      # SIMD-accelerated repo map (8 Go files)
├── agui/                          # AG-UI themes + shader (3 files)
├── native/                        # Go-native CLI replacements (3 files)
└── superpowers/                   # Infra auto-discovery plugin
```

---

## Changes from upstream Whale

| Feature | Upstream | ultrawhale v8 |
|---------|----------|---------------|
| Binary size | 39MB (debug, unstripped) | 30MB Linux / 28MB macOS (static) |
| ISA target | GOAMD64=v1 | GOAMD64=v3 (AVX2+BMI2+FMA) |
| FMA instructions | 10 | 93 (9.3x) |
| BMI2 instructions | 659 | 1,588 (2.4x) |
| Build time | 15.6s | 1.0s |
| Plugins | 1 (memory) | 5 (memory + repomap + nats + langfuse + superpowers) |
| MCP servers | 1 | 6 |
| Workflows | 1 | 6 |
| Hook events | 4 | 10 (9 async) |
| Hook timeout | 600s | 30s |
| Workflow concurrency | 3 | 8 |
| Max tool calls | 30 | 128 |
| Themes | 1 | 4 (default + 3 AG-UI) |
| Footer | 4-line | 1-line HUD statusline |
| API | DeepSeek only | DeepSeek + OpenRouter |
| Reload | Restart required | `/reload` command |
| Native tools | shell exec only | Go-native gh/grep/git |
| Theme cycling | None | `Ctrl+Shift+T` + `/reload theme` |

---

## Infrastructure Setup

### Langfuse — LLM Observability

```sh
# Get API keys from langfuse.crabcc.app → Settings → API Keys
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_HOST="https://langfuse.crabcc.app"
ultrawhale --model deepseek-v4-flash -w
# Traces auto-flow to https://langfuse.crabcc.app
```

**Traced:** session start/stop, every tool call (SPAN), LLM generations (cost, latency, tokens).

### bao — Secrets Auto-Discovery

```sh
export VAULT_TOKEN="s.xxxx"
# Store secrets once:
curl -X POST https://bao.crabcc.app/v1/secret/data/whale \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -d '{"data":{"LANGFUSE_PUBLIC_KEY":"pk-...","LANGFUSE_SECRET_KEY":"sk-..."}}'
# Start ultrawhale — superpowers plugin auto-discovers and sets env vars
ultrawhale --model deepseek-v4-flash -w
# HUD shows: bao·lf when connected
```

### NATS — Event Streaming

```sh
export NATS_URL="nats://crabcc-nats:4222"
ultrawhale --model deepseek-v4-flash -w
# Events: whale.turn.start, whale.turn.stop, whale.tool.call, whale.tool.result
```

### GPU Compute (vastai)

```sh
export VAST_API_KEY="..."
ultrawhale --model deepseek-v4-flash -w
# HUD shows available GPU count: 2GPU
```

### Hub Visibility

```sh
curl http://localhost:9797/health
# → {"plugin":"superpowers","bao_connected":true,"langfuse_wired":true,"online":true}
```

### [superpowers] Config

```toml
[superpowers]
enabled = true
bao_url = "https://bao.crabcc.app"
auto_wire_secrets = true
auto_wire_nats = true
auto_wire_langfuse = true
compute_provider = "vastai"
hub_enabled = true
```
