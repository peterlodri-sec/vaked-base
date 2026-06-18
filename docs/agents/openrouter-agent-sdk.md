# OpenRouter Agent SDK — Vaked Integration

How the Vaked agent fleet uses the [OpenRouter Agent SDK](https://openrouter.ai/sdk)
(`@openrouter/agent` for TypeScript, `adk-rust` for Rust) as its default LLM
provider. Every agent, tool, daemon, and surface routes through OpenRouter unless
it has a hard technical reason not to.

> **Policy:** `CLAUDE.md` → "LLM Provider — OpenRouter (swarm default)"  
> **Fleet index:** `VAKED_AGENTS.md` → SDK matrix per language  
> **Toolkit:** `tools/openrouter-ts/` — `@vaked/openrouter-ts` package

## Why OpenRouter

| Reason | Detail |
|--------|--------|
| **Single API surface** | 400+ models across all providers, one key, one endpoint |
| **Type-safe agents** | `@openrouter/agent` (TS) provides Zod-typed tools, streaming, agent loops, stop conditions, tool approval |
| **Cost control** | Per-request budget caps, model fallback, cost tracking |
| **Context7 native** | `@vaked/openrouter-ts` auto-wires Context7 for live library docs — HTTP 200 → authoritative ground truth |
| **No TLS hacks** | The TS/Rust SDKs use proper TLS. Python fallback tools previously used `ssl.CERT_NONE` |
| **Multi-runtime** | Node.js, Bun (mimalloc), Deno (jemalloc) — tuned for each |

## SDK per Language

### TypeScript — `@openrouter/agent` (primary)

```typescript
import { createVakedAgent } from "@vaked/openrouter-ts";

const agent = createVakedAgent();
// OpenRouter client + Context7 tools + ground-truth prompt — auto-wired

// Quick question — Context7 auto-available for library docs
const answer = await agent.ask("How do I use std.Build in Zig 0.16?");
// → Agent calls context7_search → context7_get_context → writes correct code

// Code generation — Claude Opus + Context7
const code = await agent.code("Write a Nix flake for a Zig project");

// Streaming with Context7
for await (const chunk of agent.streamChat("Explain capability-based security")) {
  process.stdout.write(chunk);
}

// Full agent loop with tools
const result = agent.callModel({
  model: "anthropic/claude-opus-4-8-fast",
  input: [{ role: "user", content: "Design a NixOS module for the Vaked sandbox daemon" }],
  stopWhen: [stepCountIs(10), maxCost(0.50)],
});
```

**Package:** `tools/openrouter-ts/` (`@vaked/openrouter-ts`)  
**Entry:** `createVakedAgent()` — zero-config, Context7 auto-wired  
**CLI:** `npx orcli "prompt"` — drop-in for `python3 tools/openrouter/cli.py`

### Rust — `adk-rust` (CI agents)

```rust
use adk_rust::prelude::*;

let model = build_or_model(api_key, "anthropic/claude-opus-4-8-fast", &base_url)?;
let agent = LlmAgentBuilder::new("vaked-ci-reviewer")
    .model(model)
    .instruction(system_prompt)
    .tools(tools)
    .build()?;
```

**Used by:** `pr-review`, `provost`, `label-tagger`, `swe-af`  
**Crate:** `adk-rust` v1.0.0 with `openrouter` feature  
**Location:** `vaked-agents/ci/{pr-review,provost,label-tagger,swe-af}/`

### Python — stdlib HTTP (fallback)

```python
import urllib.request
# Raw HTTP to https://openrouter.ai/api/v1/chat/completions
# OPENROUTER_API_KEY, stdlib only, no deps
```

**Used by:** `ralph` (cron loop), `telebot` (Telegram), `nocturne` (GPU researcher)  
**Status:** Preserved as zero-dependency fallback. New Python agents should prefer the TypeScript toolkit.

### Go — Eino (crawler)

```go
import "github.com/cloudwego/eino"
// Eino's OpenRouter chat-model component
```

**Used by:** `optitron` (optimization crawler), `fleet-introspect`  
**Location:** `tools/optitron/`

## Context7 — First-Class Native Integration

Context7 is auto-wired into every `createVakedAgent()`. No MCP server needed.

| Tool | Description |
|------|-------------|
| `context7_search` | Search 100,000+ libraries by name |
| `context7_get_context` | Fetch live docs + code examples for a library ID |
| `context7_resolve_and_query` | Resolve fuzzy name + fetch docs in one call |

### Ground Truth Guarantee

> **HTTP 200 with data → authoritative, always correct.**  
> The agent is instructed to prioritize Context7 responses over training data.

```typescript
// Agent knows to check Context7 before writing code
// for any library where API surface may have changed
const agent = createVakedAgent();
// context7SystemPrompt() is baked into instructions
```

## Model Catalog

| Alias | Model ID | Prompt $/1M | Completion $/1M |
|-------|----------|-------------|------------------|
| `deepseek` | `deepseek/deepseek-v4-pro` | $0.27 | $0.27 |
| `claude` | `anthropic/claude-opus-4-8-fast` | $15.00 | $75.00 |
| `gemini` | `google/gemini-2.5-flash` | $0.15 | $0.60 |
| `qwen` | `qwen/qwen3-235b-a22b-thinking` | $2.50 | $5.00 |
| `llama` | `meta-llama/llama-4-maverick` | $0.20 | $0.60 |
| `haiku` | `anthropic/claude-haiku-4-5` | $0.25 | $1.25 |


## Langfuse Observability (GitHub CI Secrets)

All LLM calls through `@vaked/openrouter-ts` are automatically traced to
Langfuse. Credentials come from the **GitHub CI Environment `ci`**.

### Secrets (Settings → Environments → ci → Secrets)

| Secret | Required | Purpose |
|--------|----------|---------|
| `LANGFUSE_SECRET_KEY` | Yes (for tracing) | Langfuse secret key (`sk-lf-...`) |
| `LANGFUSE_PUBLIC_KEY` | Yes (for tracing) | Langfuse public key (`pk-lf-...`) |
| `LANGFUSE_HOST` | No | Langfuse host (default: `https://cloud.langfuse.com`) |

### Secret Names (exact CI environment match)

| Our code | CI Secret | Status |
|----------|-----------|--------|
| `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | ✅ Live |
| `LANGFUSE_SECRET_KEY` | `LANGFUSE_SECRET_KEY` | ✅ Live |
| `LANGFUSE_PUBLIC_KEY` | `LANGFUSE_PUBLIC_KEY` | ✅ Live |
| `LANGFUSE_HOST` | `LANGFUSE_HOST` (preferred) or `LANGFUSE_BASE_URL` (legacy) | ✅ Live |
| `CONTEXT7_API_KEY` | `CONTEXT7_API_KEY` | 🆕 Needs adding |

### Config Variables (non-secret, CI env vars)

| Variable | Value | Used by |
|----------|-------|---------|
| `PR_REVIEW_MODEL` | `deepseek/deepseek-v4-flash` | pr-review |
| `RALPH_WRITER_MODEL` | `deepseek/deepseek-v4-pro` | ralph |
| `PR_REVIEW_TRACE_PAYLOADS` | `true` | pr-review |
| `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` | `true` | GitHub Actions runtime |

**Swarm default model:** DeepSeek V4 (Pro for quality, Flash for speed/CI).
Our `@vaked/openrouter-ts` defaults to `deepseek-v4-pro` — aligned with ralph.

### Guard Pattern

Every Langfuse call is **guarded** — the agent no-ops cleanly when secrets
are unset. Tracing failure never blocks the agent, matching the Rust
`pr-review`/`provost` convention:

```typescript
// In createVakedAgent(), every ask()/code()/review()/callModel() call:
const startTime = Date.now();
const text = await result.getText();
const response = await result.getResponse();

// Guarded — no-op when LANGFUSE_SECRET_KEY is unset
traceCallModelResult({
  model: entry.id,
  input: prompt,
  output: text,
  promptTokens: response.usage?.inputTokens ?? 0,
  completionTokens: response.usage?.outputTokens ?? 0,
  latencyMs: Date.now() - startTime,
  agentName: "vaked-agent-ask",
});
```

### Manual Tracing

```typescript
import { traceLlmCall, flushLangfuse, isLangfuseEnabled } from "@vaked/openrouter-ts";

if (isLangfuseEnabled()) {
  traceLlmCall({
    model: "anthropic/claude-opus-4-8-fast",
    input: "Write a Zig 0.16 program",
    output: "const std = @import(\"std\"); ...",
    promptTokens: 150,
    completionTokens: 400,
    cost: 0.03,
    latencyMs: 1200,
    agentName: "my-agent",
  });
}

// Flush before exit (short-lived agents)
await flushLangfuse();
```

### What's Traced

| Field | Source |
|-------|--------|
| `model` | Model ID (e.g. `anthropic/claude-opus-4-8-fast`) |
| `input` | User/agent prompt |
| `output` | Model response |
| `promptTokens` | `response.usage.inputTokens` |
| `completionTokens` | `response.usage.outputTokens` |
| `cost` | Computed from token counts × model pricing |
| `latencyMs` | Wall-clock time of the API call |
| `agentName` | Agent identifier (e.g. `vaked-agent-code`) |
| `provider` | Always `openrouter` |
| `generationId` | OpenRouter generation ID for trace linking |


## Conductor — Model Self-Selection + Context7 Pre-Scan

Models choose their own per-task. Context7 auto-injects live docs when
APIs/libraries are mentioned. Zero configuration needed.

### Model Routing

```typescript
const agent = createVakedAgent({
  modelRouting: { strategy: "auto" },
});
// code → claude, explain → deepseek, creative → gemini
```

| Strategy | Behavior |
|----------|----------|
| `auto` | Keyword-based task routing (18 keywords) |
| `cost-optimized` | Always cheapest model |
| `quality` | Always best model |
| `fixed` | User-specified (legacy) |

### Context7 Pre-Scan

Every prompt is scanned for API/library mentions. When detected, up to
2K tokens of live Context7 docs are injected before the prompt reaches
the model. Verbose transparent logging:

```
[ctx7:prescan] detected: zig, nixpkgs → injected 1847 tokens (~7.4K)
```

**20 library patterns:** zig, nixpkgs, tauri, react, cloudflare, nodejs,
rust, ebpf, monaco, python, go, docker, kubernetes, typescript, git, sql,
vite, langchain + 2 more.

### Model Fallback Chain

```typescript
modelFallbackChain("anthropic/claude-opus-4-8-fast")
// → ["anthropic/claude-opus-4-8-fast", "deepseek/deepseek-v4-pro", "google/gemini-2.5-flash"]
```

Primary fails → next in chain. OpenRouter handles the fallback automatically.

## Budget Tracking


All OpenRouter costs are tracked in `~/.orcli_budget` (shared between
TypeScript and Python `orcli`). The file contains a single float — remaining
dollars. Default cap: $6.00.

```bash
npx orcli --status          # Budget remaining: $5.8723
npx orcli --budget 10.00    # Set cap to $10.00
```

```typescript
import { readBudget, formatBudget } from "@vaked/openrouter-ts";
console.log(formatBudget(readBudget()));
// $5.8723 remaining · $0.1277 spent · cap $6.00
```

## Streaming

All three consumption patterns supported:

```typescript
// 1. getText() — wait for full response
const text = await result.getText();

// 2. getResponse() — full response with usage
const response = await result.getResponse();
console.log(response.usage.inputTokens, response.usage.outputTokens);

// 3. getTextStream() — streaming deltas
for await (const delta of result.getTextStream()) {
  process.stdout.write(delta);
}
```

## Agent Loops

### Stop Conditions

```typescript
import { stepCountIs, maxCost, maxTokensUsed, hasToolCall } from "@openrouter/agent";

const result = client.callModel({
  model: "anthropic/claude-opus-4-8-fast",
  input: [{ role: "user", content: "Research and summarize..." }],
  tools: [searchTool, fetchTool],
  stopWhen: [
    stepCountIs(10),       // Max 10 turns
    maxCost(0.50),         // Max $0.50 spend
    hasToolCall("finalize"), // Stop when finalize tool is called
  ],
});
```

### Tool Approval (Human-in-the-Loop)

```typescript
const dangerousTool = tool({
  name: "deploy",
  description: "Deploy to production",
  inputSchema: z.object({ target: z.string() }),
  requireApproval: true,  // Human must approve
  execute: async ({ target }) => {
    // Only runs after approval
    return `Deployed to ${target}`;
  },
});
```

## 20-Model Deliberation Panel

Port of `tools/openrouter/deliberate.py`. 20 models queried in parallel,
judge-synthesized consensus. Budget-capped at $10/session.

```typescript
import { deliberate } from "@vaked/openrouter-ts/deliberate";

const result = await deliberate(
  "What is the optimal memory model for the Vaked agent sandbox?",
  10.0  // budget cap
);

console.log(result.consensus);
console.log(`${result.modelsQueried} models, $${result.totalCost.toFixed(4)}`);
```

## Runtime Tuning

| Resource | Purpose |
|----------|---------|
| `tools/openrouter-ts/RUNTIME.md` | Full per-runtime tuning guide |
| `tools/openrouter-ts/MIMALLOC.md` | Mimalloc allocator tuning (Bun built-in) |
| `tools/openrouter-ts/.env.example` | All 25+ supported env vars |
| `tools/openrouter-ts/.node-options` | Default Node.js V8 flags |

### Recommended: Bun for production

```
bun run dist/cli.js "prompt"
```

Bun uses mimalloc by default — no `LD_PRELOAD`, no config. Best choice for
long-running agent loops where allocation fragmentation matters.

## Migration from Python `tools/openrouter/`

| Python | TypeScript |
|--------|-----------|
| `python3 tools/openrouter/cli.py "prompt"` | `npx orcli "prompt"` |
| `from tools.openrouter.qcall import ask` | `import { ask } from "@vaked/openrouter-ts"` |
| `python3 tools/openrouter/deliberate.py "q"` | `npx orcli --deliberate "q"` |
| `urllib.request` + `ssl.CERT_NONE` | `createVakedAgent()` — TLS-verified |

The Python tools remain as **stdlib-only fallback** — see `tools/openrouter/DEPRECATED.md`.

## New Agent Checklist

When creating a new Vaked agent:

1. **Choose SDK:** TypeScript (`@vaked/openrouter-ts`) for new agents; Rust (`adk-rust`) for CI agents
2. **Default to OpenRouter:** `OPENROUTER_API_KEY` env var, no other provider keys
3. **Guard on secrets:** No-op cleanly when unset (advisory, never block)
4. **Wire Context7:** `createVakedAgent()` auto-wires it; for Rust, use the Context7 MCP server
5. **Budget track:** Use `~/.orcli_budget` for cost tracking
6. **Add to CI:** `environment: ci`, Telegram failure-notify, `concurrency` group
7. **Update index:** Add to `VAKED_AGENTS.md` agent table

## Genesis

```
GENESIS_SEAL: 7c242080
```
