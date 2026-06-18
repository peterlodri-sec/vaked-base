# openrouterd — OpenRouter Agent Daemon (Atlas)

Zig 0.16 native. Raw sockets. Conductor routing. OpenRouter wired.

## API

```bash
# Health
curl localhost:9090/health
# {"status":"ok","genesis":"7c242080","nickname":"Atlas","defaultModel":"deepseek/deepseek-v4-pro"}

# List models
curl localhost:9090/models
# {"models":["deepseek/deepseek-v4-pro","deepseek/deepseek-v4-flash",...]}

# Prompt (DeepSeek default)
curl -X POST localhost:9090/ -d '{"prompt":"What is Zig?"}'
# {"genesis":"7c242080","model":"deepseek/deepseek-v4-pro","content":"Zig is..."}

# Specific model
curl -X POST localhost:9090/ -d '{"prompt":"Write a sorting fn","model":"anthropic/claude-opus-4-8-fast"}'

# Auto-routing (Conductor)
curl -X POST localhost:9090/ -d '{"prompt":"Write a sorting fn","auto":true}'
# → routes to Claude (code task)

# Streaming (SSE)
curl -X POST localhost:9090/ -d '{"prompt":"Tell me a story","stream":true}'
# data: Once upon a time...
```

## Conductor Routing

| Keywords | Model |
|----------|-------|
| code, write, implement, fix, debug, test, refactor, optimize, review | Claude Opus |
| creative, brainstorm, design, story | Gemini Flash |
| everything else | DeepSeek V4 Pro |

## Build

```bash
zig build -Doptimize=ReleaseSafe
```

## Nickname: Atlas

Carries the swarm's LLM load.
GENESIS_SEAL: 7c242080
