# `llmproxy.crabcc.app` — LiteLLM gateway (setup proposal / scaffold)

> **Status: proposal scaffold — not yet deployed.** Design rationale lives in
> [`docs/agents/llmproxy-proposal.md`](../../docs/agents/llmproxy-proposal.md). This
> directory is the *runnable* setup: a `docker compose` stack you can stand up on the
> `vakedos` host (or a small VPS) and put behind a Cloudflare Tunnel.

A single self-hosted **LiteLLM** proxy in front of OpenRouter: one control plane for
routing, fallbacks, budgets, caching, and Langfuse tracing — **default model stays
`deepseek/deepseek-v4-flash`**. Public DNS (`llmproxy.crabcc.app`), non-public
consumption (virtual keys + Cloudflare).

## Stack
- **litellm** — the OpenAI-compatible proxy (`/v1/...`).
- **postgres** — virtual keys, budgets, spend ledger.
- **redis** — response cache (the extra cache layer above OpenRouter's prefix cache).
- **cloudflared** (optional) — outbound-only tunnel; no inbound port exposed.

## Quick start (on the host)
```bash
cd deploy/llmproxy
cp .env.example .env          # fill in OPENROUTER_API_KEY, LITELLM_MASTER_KEY, LANGFUSE_*
docker compose up -d
# smoke test (master key)
curl -s http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"deepseek/deepseek-v4-flash","messages":[{"role":"user","content":"ping"}]}' | jq .
```

## Mint a per-agent virtual key
```bash
curl -s http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
  -d '{"key_alias":"pr-review","models":["deepseek/deepseek-v4-flash"],"max_budget":25,"budget_duration":"30d"}'
```

## Point the agents at it (config-only — no agent code change)
The pr-review agent already honours `OPENROUTER_BASE_URL` + `PR_REVIEW_API_KEY`; ralph
honours `RALPH_BASE_URL` + `RALPH_API_KEY`. In the `ci` environment:
```yaml
PR_REVIEW_API_KEY:   ${{ secrets.LLMPROXY_VIRTUAL_KEY }}
OPENROUTER_BASE_URL: https://llmproxy.crabcc.app/v1
# PR_REVIEW_MODEL stays deepseek/deepseek-v4-flash
```
`OPENROUTER_API_KEY` then lives **only** on this host, never in `ci`.

> Compatibility: the agent sends OpenRouter-specific params (`provider` pin,
> `usage.include`, `prompt_cache_key`). Start in **pass-through** mode (forward them
> unchanged); later move provider routing/caching into `config.yaml` and unset the
> agent-side pin with `PR_REVIEW_PROVIDER_ORDER=""`.

## "Public-facing but non-public"
- Cloudflare Tunnel → no inbound port; TLS at the edge.
- LiteLLM **virtual keys** (per-agent, budgeted) — no key ⇒ 401.
- Cloudflare WAF rate-limit + optional **Cloudflare Access** service tokens / IP allow-list.
- Master key never leaves the host; rotate virtual keys per agent.
