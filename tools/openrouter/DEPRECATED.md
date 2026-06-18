# Deprecation Notice

> **Status:** Legacy — superseded by `tools/openrouter-ts/`

The Python `tools/openrouter/` tools remain as a **stdlib-only fallback**
(zero dependencies, works anywhere Python 3.12+ is available). For new code,
use the TypeScript `@vaked/openrouter-ts` package instead.

## Migration Guide

| Python | TypeScript |
|--------|-----------|
| `python3 tools/openrouter/cli.py "prompt"` | `npx orcli "prompt"` |
| `from tools.openrouter.qcall import ask, code, review` | `import { ask, code, review } from "@vaked/openrouter-ts"` |
| `python3 tools/openrouter/deliberate.py "question"` | `npx orcli --deliberate "question"` |

## Why

The TypeScript package provides:

- **Type safety** — TypeScript + Zod schemas for all inputs/outputs
- **Streaming** — built-in `getTextStream()` support
- **Agent loops** — multi-turn tool-use with stop conditions, cost ceilings
- **TLS verification** — the Python tools disable TLS (`ssl.CERT_NONE`)
- **Shared budget** — same `~/.orcli_budget` file

The Python tools are **not being removed**. They remain the zero-dependency
fallback for environments where Node.js is unavailable.

## Genesis

```
GENESIS_SEAL: 7c242080
```
