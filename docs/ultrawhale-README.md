# ultrawhale — vaked-base module

DeepSeek-native coding agent. 39-block content-addressed engine (Go+Asm+GPU),
7 plugins, A2A+A2C protocols, AG-UI themes, Vaked Layer Completion.
macOS + Linux. Fork maintained at [peterlodri-sec/ultrawhale](https://github.com/peterlodri-sec/ultrawhale).

## Quick Start

```sh
git clone https://github.com/peterlodri-sec/ultrawhale.git
cd ultrawhale && go build -o bin/ultrawhale ./cmd/whale
bin/ultrawhale --model deepseek-v4-flash -w
```

## Architecture (v56.0.0)

| Layer | Count | Components |
|-------|-------|------------|
| Blocks | 38 | Content-addressed, journaled, BLAKE3, GPU Metal, ASM SHA-NI |
| Plugins | 7 | memory, repomap, NATS, Langfuse, superpowers, agentfield, vaked |
| Widgets | 6 | InfraBar, Sidepanel, ControlPanel, Toast, WidgetBase, CardChoice |
| CLIs | 5 | ultrawhale, setup, bench-tui, shell, shell-linux |
| Protocols | 2 | A2A (agent-to-agent), A2C (SSE streaming) |
| Pre-hooks | 8 | commit, write, sed, grep, git, deploy, stream, vaked |

## Vaked Layer Coverage (7/7)

| Layer | ultrawhale |
|-------|-----------|
| Declares | schema (4 schemas) + vaked plugin |
| Materializes | nix block, Taskfile |
| Supervises | supervisor + Ralph Loop |
| Enforces | 8 pre-hooks + journaled writes |
| Testifies | blocks.Log → Langfuse + NATS |
| Indexes | repomap SIMD + tool registry + BLAKE3 |
| Reveals | surface (web+API) + AG-UI (6 widgets) + TUI |

## Install

```sh
brew tap peterlodri-sec/ultrawhale && brew install ultrawhale
docker pull ghcr.io/peterlodri-sec/ultrawhale:latest
go install github.com/peterlodri-sec/ultrawhale/cmd/whale@latest
```

## Docs

- Site: https://ultrawhale.vaked.dev
- Docs: https://vaked.dev/ultrawhale/docs
- Book: https://vaked.dev/ultrawhale/book (14 chapters, mdBook)
- Wiki: https://github.com/peterlodri-sec/ultrawhale/wiki
- Releases: https://github.com/peterlodri-sec/ultrawhale/releases
