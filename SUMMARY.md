# Migration Summary: `migrate-to-openrouter-agent`

> **Branch:** `migrate-to-openrouter-agent`  
> **Date:** 2026-06-18  
> **Genesis Seal:** `7c242080`  
> **Goal:** Replace hand-rolled Python `urllib.request` OpenRouter HTTP calls with the type-safe `@openrouter/agent` TypeScript SDK across the Vaked monorepo.

---

## Pre-Migration State

- **Zero** `@openrouter/sdk` or `@openrouter/agent` packages anywhere in the monorepo
- 6 OpenRouter consumers, all via raw HTTP:
  - `tools/openrouter/cli.py` — `urllib.request` with `ssl.CERT_NONE`
  - `tools/openrouter/qcall.py` — wraps `cli.py`
  - `tools/openrouter/deliberate.py` — 20-model panel, `urllib.request`
  - `tools/ralph/ralph.py` — decision loop, `urllib.request`
  - `vaked-agents/ci/pr-review/` — `adk-rust` (Rust, already has proper SDK)
  - `vaked-agents/ci/provost/` — `adk-rust` (Rust, already has proper SDK)
- Only npm project: `ide/vaked-ide/` using `@anthropic-ai/sdk` ^0.30.0

---

## Changes

### Track A: New `tools/openrouter-ts/` Package

**7 new files** — a type-safe TypeScript SDK toolkit replacing the Python `tools/openrouter/`:

| File | Purpose |
|------|---------|
| `package.json` | `@vaked/openrouter-ts` — depends on `@openrouter/agent` ^0.7.2, `zod` ^3.24 |
| `tsconfig.json` | ESM, NodeNext, ES2022, strict |
| `src/index.ts` | SDK wrapper: `ask()`, `code()`, `review()`, `chat()`, `streamChat()`, `sweLoop()`, `budget()` |
| `src/types.ts` | Model catalog (6 models), deliberation panel (20 models), cost tables |
| `src/budget.ts` | `~/.orcli_budget` file-based tracking — identical logic to Python |
| `src/deliberate.ts` | 20-model deliberation panel with judge synthesis — port of `deliberate.py` |
| `src/cli.ts` | `orcli` CLI — `--stream`, `--deliberate`, `--list`, `--status`, `--model`, `--file` |

**API differences from Python:**
- `callModel()` via `new OpenRouter({ apiKey })` client (not raw HTTP)
- Type-safe tools with Zod schemas
- Built-in streaming via `getTextStream()` / `getResponse()` / `getText()`
- Stop conditions: `stepCountIs()`, `maxCost()`, `maxTokensUsed()`, `finishReasonIs()`
- Usage: `inputTokens` / `outputTokens` (not `promptTokens` / `completionTokens`)
- `maxOutputTokens` (camelCase, not `max_tokens`)

**Build:** ✅ Clean TypeScript compile

---

### Track B: IDE Migration (`ide/vaked-ide/`)

**5 files changed** — replacing `@anthropic-ai/sdk` with `@openrouter/agent`:

| File | Change |
|------|--------|
| `package.json` | `@anthropic-ai/sdk` ^0.30.0 → `@openrouter/agent` ^0.7.2; added `zod` ^3.24 |
| `src/lib/anthropic.ts` → `src/lib/openrouter.ts` | Renamed; preserved `graphContextString()` and `parseSuggestedEdit()`; added OpenRouter type re-exports, model catalog, and agent-model role mapping |
| `src/types/session.ts` | `AgentRole` extended: `"claude"` → `"openrouter"` as default; added `"deepseek"`, `"gemini"`, `"claude"` as optional roles; updated labels and colors |
| `src/store/sessionStore.ts` | Default `activeAgents`: `["user", "claude"]` → `["user", "openrouter"]` |
| `src/hooks/useSession.ts` | Import path: `@/lib/anthropic` → `@/lib/openrouter` |

**Agent roles after migration:**

| Role | Model | Color |
|------|-------|-------|
| `openrouter` (default) | DeepSeek V4 Pro | `#f97316` |
| `deepseek` | DeepSeek V4 Pro | `#10b981` |
| `claude` | Claude Opus 4.8 | `#f97316` |
| `gemini` | Gemini 2.5 Flash | `#3b82f6` |
| `schema-advisor` | Claude Opus 4.8 | `#14b8a6` |
| `capability-expert` | DeepSeek V4 Pro | `#a855f7` |
| `lowering-guide` | Claude Opus 4.8 | `#22c55e` |
| `a2a-peer` | — | `#3b82f6` |

**Build:** ✅ No migration-related errors (pre-existing XYFlow `RFNodeData`/`RFEdgeData` type issues only)

---

## What Was NOT Changed

- Python `tools/openrouter/` — **preserved as fallback** (stdlib-only, zero deps)
- `tools/ralph/ralph.py` — still uses raw HTTP (Python stdlib is intentional for cron loops)
- `vaked-agents/ci/pr-review/` — Rust `adk-rust` already has proper OpenRouter SDK
- `vaked-agents/ci/provost/` — same
- `tools/optitron/` — Go/Eino already uses OpenRouter SDK component
- Tauri Rust backend — still needs OpenRouter wiring (future work)

---

## File Tree

```
tools/openrouter-ts/
├── package.json
├── tsconfig.json
└── src/
    ├── index.ts          # Main SDK wrapper + exports
    ├── types.ts          # Model catalog, deliberation panel, types
    ├── budget.ts         # File-based budget tracking
    ├── deliberate.ts     # 20-model deliberation panel
    └── cli.ts            # orcli CLI entry point

ide/vaked-ide/
├── package.json          # @anthropic-ai/sdk → @openrouter/agent
└── src/
    ├── lib/
    │   ├── openrouter.ts # Renamed from anthropic.ts; added SDK types
    │   └── anthropic.ts  # REMOVED
    ├── types/
    │   └── session.ts    # AgentRole: openrouter default, +deepseek, +gemini
    ├── store/
    │   └── sessionStore.ts  # activeAgents default: openrouter
    └── hooks/
        └── useSession.ts    # Import: openrouter
```
