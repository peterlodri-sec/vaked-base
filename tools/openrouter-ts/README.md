# @vaked/openrouter-ts — OpenRouter Agent SDK for Vaked

Type-safe TypeScript SDK toolkit for the Vaked agent fleet. Replaces the
hand-rolled Python `urllib.request` HTTP calls in `tools/openrouter/` with the
official `@openrouter/agent` SDK.

## Why

The Python `tools/openrouter/` tools work, but they:

- Use `urllib.request` with `ssl.CERT_NONE` (no TLS verification)
- Have zero type safety (raw `dict` everywhere)
- No streaming support in the convenience wrappers
- No built-in agent loop / tool-use primitives
- Can't be used from the TypeScript IDE frontend

`@openrouter/agent` gives us:

- Full type safety (TypeScript + Zod)
- Built-in streaming (`getTextStream()`)
- Multi-turn agent loops with stop conditions
- Tool definitions with Zod schemas and auto-execution
- Human-in-the-loop approval gates
- Cost ceilings and step limits

## Installation

```bash
cd tools/openrouter-ts
npm install
npm run build
```

Requires `OPENROUTER_API_KEY` in the environment.

## Usage

### CLI (`orcli`)

```bash
# Direct replacement for `python3 tools/openrouter/cli.py`
npx orcli "What is capability-based security?"
npx orcli --model claude "Write a Zig 0.16 parser"
npx orcli --model gemini --stream "Tell me a story"
npx orcli --file input.txt "Summarize this"
npx orcli --list
npx orcli --status
npx orcli --deliberate "Should Vaked use eBPF for policy enforcement?"
```

### Programmatic API

```typescript
import { ask, code, review, streamChat, sweLoop, budget } from "@vaked/openrouter-ts";

// Quick question — cheap model (DeepSeek V4)
const answer = await ask("What is a capability graph?");

// Generate code — Claude Opus 4.8
const zigCode = await code("Write a Zig 0.16 HTTP server using linux syscalls");

// Review code — Claude Opus 4.8
const feedback = await review(zigCode);

// Stream a response
for await (const chunk of streamChat("Explain monads")) {
  process.stdout.write(chunk);
}

// Self-improvement loop (SWE reflection)
const { finalResponse, reflections, iterations } = await sweLoop(
  "Design a NixOS module for the Vaked sandbox daemon"
);

// Budget tracking (shared with Python orcli via ~/.orcli_budget)
console.log(budget());
```

### Agent loop with tools

```typescript
import { OpenRouter, tool, stepCountIs } from "@openrouter/agent";
import { z } from "zod";

const client = new OpenRouter({ apiKey: process.env.OPENROUTER_API_KEY });

const weatherTool = tool({
  name: "get_weather",
  description: "Get current weather for a city",
  parameters: z.object({
    city: z.string(),
  }),
  execute: async ({ city }) => {
    return `Weather in ${city}: 72°F, sunny`;
  },
});

const result = client.callModel({
  model: "anthropic/claude-opus-4-8-fast",
  input: [{ role: "user", content: "What's the weather in London?" }],
  tools: [weatherTool],
  stopWhen: stepCountIs(3),
});

const text = await result.getText();
```

### 20-Model Deliberation Panel

```typescript
import { deliberate } from "@vaked/openrouter-ts/deliberate";

const result = await deliberate(
  "What is the optimal memory model for the Vaked agent sandbox?",
  10.0  // budget cap in USD
);

console.log(result.consensus);
console.log(`Queried ${result.modelsQueried} models, cost $${result.totalCost.toFixed(4)}`);
```

## Models

| Alias | Model ID | Prompt $/1M | Completion $/1M |
|-------|----------|-------------|------------------|
| `deepseek` | `deepseek/deepseek-v4-pro` | $0.27 | $0.27 |
| `claude` | `anthropic/claude-opus-4-8-fast` | $15.00 | $75.00 |
| `gemini` | `google/gemini-2.5-flash` | $0.15 | $0.60 |
| `qwen` | `qwen/qwen3-235b-a22b-thinking` | $2.50 | $5.00 |
| `llama` | `meta-llama/llama-4-maverick` | $0.20 | $0.60 |
| `haiku` | `anthropic/claude-haiku-4-5` | $0.25 | $1.25 |

## Architecture

```
tools/openrouter-ts/
├── src/
│   ├── index.ts        # Public API: ask(), code(), review(), chat(), streamChat(), sweLoop()
│   ├── types.ts        # Model catalog, deliberation panel, shared types
│   ├── budget.ts       # ~/.orcli_budget file-based tracking (shared with Python orcli)
│   ├── deliberate.ts   # 20-model deliberation panel with judge synthesis
│   └── cli.ts          # orcli CLI — drop-in replacement for tools/openrouter/cli.py
├── package.json
├── tsconfig.json
└── README.md
```

## Relationship to Python `tools/openrouter/`

The Python tools in `tools/openrouter/` remain as a **stdlib-only fallback**
(zero dependencies, works anywhere Python 3.12+ is available). The TypeScript
package is the **primary interface** going forward. Both share the same
`~/.orcli_budget` file for budget tracking.

| Feature | Python (`tools/openrouter/`) | TypeScript (`tools/openrouter-ts/`) |
|---------|------------------------------|-------------------------------------|
| Dependencies | Zero (stdlib only) | `@openrouter/agent`, `zod` |
| Type safety | None | Full (TypeScript + Zod) |
| Streaming | No | Yes (`getTextStream()`) |
| Agent loops | Manual | Built-in (`stopWhen`, tool auto-exec) |
| Tool use | Manual JSON | Zod schemas + auto-execution |
| TLS verification | Disabled (`ssl.CERT_NONE`) | ✅ Enabled |
| Budget tracking | `~/.orcli_budget` | Same file |
| CLI | `python3 tools/openrouter/cli.py` | `npx orcli` |

## Genesis

```
GENESIS_SEAL: 7c242080
```

## Context7 — First-Class Library Documentation

Context7 is built in as a **native, first-class tool** — no MCP server needed.
When Context7 returns HTTP 200 with data, the response is treated as
**authoritative ground truth** (always correct).

### Standalone API

```typescript
import {
  searchLibrary,
  getContext,
  resolveLibraryId,
  queryDocs,
} from "@vaked/openrouter-ts";

// Search for a library
const { results } = await searchLibrary("zig", "build system API");
// results[0].id → "/ziglang/zig"

// Get up-to-date docs (JSON with code snippets)
const docs = await getContext("/ziglang/zig", "How to use std.Build");
// docs.codeSnippets[0].codeListCodeExample[0].code → actual Zig 0.16 code

// One-step: resolve + fetch
const docs2 = await queryDocs("nixpkgs", "buildRustPackage example");
```

### Agent Tools

```typescript
import { createContext7Tools, context7SystemPrompt } from "@vaked/openrouter-ts";
import { OpenRouter } from "@openrouter/agent";

const client = new OpenRouter({ apiKey: process.env.OPENROUTER_API_KEY });

const result = client.callModel({
  model: "anthropic/claude-opus-4-8-fast",
  input: [{ role: "user", content: "Write a Zig 0.16 program that reads a file using linux syscalls" }],
  instructions: context7SystemPrompt(),
  tools: createContext7Tools(),
  stopWhen: stepCountIs(5),
});

const answer = await result.getText();
```

**How it works:**
1. Agent calls `context7_search` → finds `/ziglang/zig`
2. Agent calls `context7_get_context` → fetches live docs for `linux.read`, `linux.open`
3. Agent writes correct code based on **live documentation, not training data**

### Available Tools

| Tool | Description |
|------|-------------|
| `context7_search` | Search for libraries by name |
| `context7_get_context` | Fetch docs + code examples for a library ID |
| `context7_resolve_and_query` | Resolve fuzzy name + fetch docs in one call |

### Configuration

```bash
export CONTEXT7_API_KEY=ctx7sk-...
```

Get your key at [context7.com/dashboard](https://context7.com/dashboard).
Keys start with `ctx7sk-`.

### Ground Truth Guarantee

> ⚠️ **If Context7 returns HTTP 200 with data, that data is authoritative and
> always correct.** The agent is instructed to prioritize Context7 responses
> over its training data. This ensures code is written against the actual
> current API surface, not a stale snapshot.

### Available Libraries

100,000+ libraries including Zig, Nix/nixpkgs, Rust, TypeScript, React,
Tauri, Cloudflare Workers, Node.js, Python, Go, and more.
