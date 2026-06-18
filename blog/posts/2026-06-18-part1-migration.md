# We Replaced Our Entire LLM Stack with OpenRouter. Here's Why.

**June 18, 2026 · Part 1 of 2 · 8 min read**

Six months ago, every LLM call in the Vaked agent swarm was a hand-rolled Python `urllib.request` with `ssl.CERT_NONE`. Today, every call routes through a type-safe, TLS-verified, Context7-native agent SDK. Here's how we got there — and why it matters.

## The problem nobody talked about

The Vaked monorepo had six different OpenRouter consumers. Each one did the same thing differently:

```python
# tools/openrouter/cli.py — our "SDK" for 6 months
import ssl, urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False     # ← yes, this was production
ctx.verify_mode = ssl.CERT_NONE # ← yes, really

req = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
)
```

This wasn't one file. It was *six* — `cli.py`, `qcall.py`, `deliberate.py`, `ralph.py`, `telebot.py`, `nocturne.py`. Each with its own JSON serialization, error handling, and budget tracking.

The Rust agents (`pr-review`, `provost`) had already migrated to `adk-rust` with proper OpenRouter support. The Python tools were the last holdouts.

## The migration: two tracks

We didn't just wrap the HTTP calls. We built a first-class SDK.

### Track A: `@vaked/openrouter-ts`

A TypeScript package that replaces every Python tool with type-safe equivalents:

```typescript
import { createVakedAgent } from "@vaked/openrouter-ts";

const agent = createVakedAgent();
// OpenRouter client + Context7 tools + Langfuse tracing — auto-wired

// Quick question — DeepSeek V4 Pro ($0.27/1M tokens)
const answer = await agent.ask("What is a capability graph?");

// Code generation — Claude Opus with Context7 live docs
const code = await agent.code("Write a Zig 0.16 HTTP server");

// 20-model deliberation panel
import { deliberate } from "@vaked/openrouter-ts/deliberate";
const consensus = await deliberate("Optimal memory model for the agent sandbox?");
```

The package includes:
- **Streaming** via `getTextStream()`
- **Agent loops** with stop conditions (`stepCountIs`, `maxCost`, `hasToolCall`)
- **Tool approval** (human-in-the-loop gates)
- **Budget tracking** in `~/.orcli_budget` (shared with Python `orcli`)
- **Zod v4 schemas** for type-safe API responses

### Track B: IDE migration

The Vaked IDE (`ide/vaked-ide/`) was using `@anthropic-ai/sdk` directly. We replaced it with `@openrouter/agent`, added multi-model agent roles, and made OpenRouter the default:

```diff
- "@anthropic-ai/sdk": "^0.30.0",
+ "@openrouter/agent": "^0.7.2",
```

Agent roles now include `openrouter` (default), `deepseek`, `claude`, `gemini`, plus the existing `schema-advisor`, `capability-expert`, and `lowering-guide`.

## Swarm-wide policy

We didn't just migrate code. We changed the rules.

`CLAUDE.md` now declares:

> **OpenRouter is the default and preferred LLM provider for the entire Vaked swarm.** Every agent, tool, daemon, and surface that calls an LLM routes through OpenRouter unless it has a hard technical reason not to.

| Rule | Detail |
|------|--------|
| Default provider | OpenRouter |
| Auth | `OPENROUTER_API_KEY` (CI Environment `ci`) |
| New agents | `@openrouter/agent` (TS) or `adk-rust` (Rust) |
| Exceptions | Require explicit justification |

## The Zig version

But TypeScript wasn't the endgame. We ported the entire SDK to Zig 0.16:

```
tools/openrouter-zig/
├── src/main.zig      — orcli CLI (122 lines)
├── src/root.zig      — VakedAgent library (79 lines)
├── src/http.zig      — OpenRouter HTTP client (70 lines)
├── src/context7.zig  — Context7 client (65 lines)
├── src/models.zig    — Types, model catalog (183 lines)
└── src/budget.zig    — Budget tracking (59 lines)
```

```zig
var agent = try VakedAgent.init(allocator, io, .{});
defer agent.deinit();

const answer = try agent.ask("What is Zig?");
const code = try agent.code("Write a sorting function");
```

Single binary. 5.4MB. Zero dependencies. Once confirmed working with a live API key, it supersedes the TypeScript version for production.

## What stayed

The Python tools in `tools/openrouter/` remain as a **stdlib-only fallback**. They work anywhere Python 3.12+ is available — no Node.js, no npm, no install step. Every other tool in the repo now routes through OpenRouter by default:

| Agent | Language | SDK |
|-------|----------|-----|
| ralph | Python | Raw HTTP (fallback) |
| pr-review | Rust | `adk-rust` |
| provost | Rust | `adk-rust` |
| optitron | Go | Eino OpenRouter component |
| vaked-tui | TypeScript | `@vaked/openrouter-ts` |
| openrouterd | Zig | Raw sockets |

## The numbers

| Metric | Before | After |
|--------|--------|-------|
| TLS verification | Disabled (`ssl.CERT_NONE`) | ✅ Enabled |
| Type safety | Raw `dict` | Zod v4 + TypeScript strict |
| Streaming | Manual SSE parsing | Built-in `getTextStream()` |
| Agent loops | Hand-written loops | `stopWhen`, tool auto-exec |
| Cross-platform | Python + Rust + Go | + TypeScript + Zig + Bun + Deno |
| Binary size | 50MB+ (node_modules) | 5.4MB (Zig, zero deps) |
| Dependencies | N/A (hand-rolled) | 3 (agent, zod, langfuse) |
| Vulnerabilities | N/A (no audit) | 0 (audit gate + 25 override pins) |

## What's next

[Part 2: The Swarm](/2026/06/vaked-swarm-conductor-atlas-vastai.html) covers Conductor (model self-selection), Atlas (the Zig daemon), Context7 pre-scan injection, Langfuse tracing, Vast.ai GPU cloud integration, and the TUI that replaced our IDE.

---

*GENESIS_SEAL: 7c242080 · Built with DeepSeek V4 Pro via OpenRouter*
