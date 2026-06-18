# vaked — the Vaked TUI agent

Cross-platform, battle-tested terminal agent. Uses `@vaked/openrouter-ts`
under the hood. Zero GUI deps — works over SSH, in tmux, on any terminal.

```
┌─ vaked ──────────────────────────────────────────────┐
│ deepseek/deepseek-v4-pro · $5.87 · ctx7·stream      │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ── How do I use std.Build in Zig 0.16?              │
│                                                       │
│  const std = @import("std");                          │
│  pub fn build(b: *std.Build) void { ... }             │
│                                                       │
│  > _                                                  │
│                                                       │
├──────────────────────────────────────────────────────┤
│ /help · /model · /file · /context7 · /budget         │
└──────────────────────────────────────────────────────┘
```

## Install

```bash
cd tools/vaked-tui && npm install && npm run build
npm link  # → `vaked` in PATH
```

## Usage

```bash
# Interactive TUI
vaked

# CI mode — pipe in, pipe out
echo "Write a Zig 0.16 HTTP server" | vaked --ci --model claude

# One-shot
vaked --oneshot "Explain capability-based security"

# With file context
vaked --file src/main.zig --oneshot "What does this do?"

# Stream output
vaked --ci --stream "Tell me a story"

# JSON output (CI)
vaked --ci --json < prompt.txt

# List models / budget
vaked --list
vaked --status
```

## Slash Commands (TUI)

| Command | Action |
|---------|--------|
| `/help` | Show commands |
| `/model <name>` | Switch model (deepseek, claude, gemini, etc.) |
| `/file <path>` | Add file as context |
| `/context7` | Toggle Context7 live docs |
| `/budget` | Show remaining budget |
| `/clear` | Reset session |
| `/history` | Show message history |
| `/stream` | Toggle streaming |
| `/quit` | Exit |

## CI Mode

```bash
# Pipe code for review
cat src/main.zig | vaked --ci --prompt "Code review for bugs" --model claude

# Batch processing
for f in src/*.zig; do
  echo "=== $f ==="
  cat "$f" | vaked --ci --prompt "Summarize this file in one line" --json
done
```

## Architecture

```
vaked-tui/
├── src/main.ts    — single file, ~400 lines
│   ├── parseArgs()   — arg parsing
│   ├── ciMode()      — stdin→stdout, --json, --stream
│   ├── tuiMode()     — readline TUI, slash commands
│   └── main()        — router
├── package.json   — depends on @vaked/openrouter-ts (local)
└── tsconfig.json  — strict, types: [node]
```

Zero external TUI deps. Uses Node.js built-in `readline` — the most
battle-tested TUI in existence. Works on every platform Node.js runs on.
