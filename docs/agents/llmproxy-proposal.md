# Proposal — `llmproxy.crabcc.app`: a self-hosted LiteLLM gateway for the agent fleet

> Status: **proposal** · Owner: cabotage · Depends on: nothing (agents already
> support `OPENROUTER_BASE_URL` / `*_API_KEY` overrides) · Default model stays
> `deepseek/deepseek-v4-flash` via OpenRouter.

## Why

Today every agent (pr-review, `@vaked-ci`, ralph, mastodon writer) calls OpenRouter
**directly**, each embedding its own routing, key, retry, and cache config. That
scatters control and means cache locality, budgets, and observability are
per-agent. A single **self-hosted [LiteLLM] proxy** in front of OpenRouter gives us
one chokepoint to:

- **Reduce + control the pipeline** — model routing, fallbacks, retries, timeouts,
  per-key budgets and rate limits live in **one `config.yaml`**, not in N agents.
  Agents just ask for a logical model name; the proxy decides where it lands.
- **Raise cache-hit** — a proxy-level **Redis cache** (exact + optional semantic)
  sits *above* OpenRouter, so identical/near-identical requests across agents and
  re-runs short-circuit before egress. It complements (doesn't replace) DeepSeek's
  provider-side prefix cache the pr-review agent already pins for.
- **Centralize tracing** — LiteLLM has a native **Langfuse callback**; pairing it
  with the OTEL work means every call is traced once, at the gateway, with cost +
  cache metadata, regardless of which agent made it.
- **Govern spend + access** — virtual keys with budgets/expiry, spend dashboards,
  and per-key model allow-lists.

**Defaults are unchanged:** the proxy's default route is
`deepseek/deepseek-v4-flash` through OpenRouter. OpenRouter + DeepSeek remain the
primary path; the proxy is a control plane, not a model swap.

## "Public-facing but non-public consumption"

`llmproxy.crabcc.app` is reachable from GitHub-hosted runners (so CI agents can use
it) yet **closed to the public**:

- **TLS + edge** — fronted by Cloudflare (crabcc.app is already on Cloudflare),
  terminating TLS; origin via a Cloudflare Tunnel so no inbound port is exposed.
- **Auth = virtual keys** — LiteLLM **`virtual_key`** per consumer (pr-review,
  ralph, IDE), each scoped to allowed models + a monthly budget. The master key
  never leaves the host. No key ⇒ 401.
- **Defense in depth** — Cloudflare WAF + rate-limit rules, optional
  **Cloudflare Access** (service tokens) or an IP allow-list, and LiteLLM's own
  per-key RPM/TPM caps. Public DNS, non-public consumption. 😉

## How it slots in (config-only for the agents)

The pr-review agent already accepts `OPENROUTER_BASE_URL` (+ `PR_REVIEW_API_KEY`
taking precedence over `OPENROUTER_API_KEY`), and ralph accepts `RALPH_BASE_URL` /
`RALPH_API_KEY`. So adoption is **secret/env only** — no code change:

```yaml
# .github/workflows/pr-review.yml (ci env) — point the agent at the proxy
PR_REVIEW_API_KEY:    ${{ secrets.LLMPROXY_VIRTUAL_KEY }}   # LiteLLM virtual key
OPENROUTER_BASE_URL:  https://llmproxy.crabcc.app/v1        # OpenAI-compatible
# PR_REVIEW_MODEL stays deepseek/deepseek-v4-flash
```

LiteLLM exposes an **OpenAI-compatible** `/v1`, and the agent's OpenRouter client
already runs in `ChatCompletions` mode, so the wire shape matches.

### One compatibility caveat (worth getting right)

The pr-review agent sends OpenRouter-specific knobs the proxy must **forward**, not
swallow: `provider` preferences (the DeepSeek pin), `usage: {include:true}`, and
`prompt_cache_key`. Two clean options:

1. **Pass-through** — set LiteLLM `litellm_settings.allowed_openai_params` /
   `forward_openai_org_id`-style passthrough (or `extra_body` forwarding) so those
   fields reach OpenRouter unchanged. Simplest; keeps the agent the source of truth.
2. **Move routing into the proxy** — drop the agent-side provider pin and let
   LiteLLM's **router** own provider order, fallbacks, and caching. Cleaner
   long-term (the whole point of the gateway), but means the agent stops setting
   `provider.order` for deepseek/* (gate it behind a `PR_REVIEW_PROVIDER_ORDER=""`
   override, which the agent already supports).

Recommend **(1) first** (zero-risk pass-through), migrate to **(2)** once the proxy
is proven.

## Deployment sketch

Self-hosted on the `vakedos` host (or a small VPS), `docker compose`:

```yaml
# litellm + postgres (keys/spend) + redis (cache)
services:
  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    command: ["--config", "/app/config.yaml"]
    environment:
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}   # the ONE real upstream key
      LITELLM_MASTER_KEY:  ${LITELLM_MASTER_KEY}
      DATABASE_URL:        ${DATABASE_URL}
      REDIS_URL:           ${REDIS_URL}
      LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY: …       # gateway-level tracing
    # behind a Cloudflare Tunnel → llmproxy.crabcc.app
```

```yaml
# config.yaml (essence)
model_list:
  - model_name: deepseek/deepseek-v4-flash          # the default the fleet asks for
    litellm_params: { model: openrouter/deepseek/deepseek-v4-flash }
router_settings:
  routing_strategy: latency-based-routing
  fallbacks: [{ "deepseek/deepseek-v4-flash": ["openrouter/z-ai/glm-5"] }]
  cooldown_time: 30
litellm_settings:
  cache: true
  cache_params: { type: redis }
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
```

## Rollout

1. Stand up the proxy + Cloudflare Tunnel; smoke-test `/v1/chat/completions` with a
   virtual key.
2. Point **ralph** at it first (lowest blast radius), watch Langfuse + spend.
3. Point **pr-review** / **@vaked-ci** at it via the `ci` env (pass-through mode).
4. Once stable, migrate provider routing/caching into the proxy and simplify the
   agent (option 2). Keep **direct-OpenRouter as the documented fallback** (unset
   `OPENROUTER_BASE_URL`) for incident recovery.

## New `ci` secrets this introduces

| Secret | Purpose |
|--------|---------|
| `LLMPROXY_VIRTUAL_KEY` | per-agent LiteLLM virtual key (replaces direct `OPENROUTER_API_KEY` in agents that move behind the proxy) |
| `LLMPROXY_BASE_URL` | `https://llmproxy.crabcc.app/v1` (or hard-code in the workflow env) |

`OPENROUTER_API_KEY` then lives **only** on the proxy host, not in `ci`.

---

## Complementary self-hostable stack (5 picks)

Actively-maintained, self-hostable services that pair well with this gateway and
would make the research infra stand out — see chat thread for the rationale:

1. **vLLM** — OpenAI-compatible local inference; a LiteLLM fallback route to a
   local DeepSeek-distill / Qwen for offline + zero-marginal-cost runs.
2. **Qdrant** — Rust vector DB for semantic RAG over Vaked docs/RFCs, layered on
   the crabcc symbol index.
3. **OpenBao** (Vault fork) — real secrets management; directly prevents the
   `LANGFUSE_*` secret-name drift that silently disabled tracing.
4. **Temporal** — durable execution for the ralph loop + agent pipelines
   (retries/timeouts/replay as first-class), research-grade reliability.
5. **Authentik** — SSO / forward-auth to make `llmproxy.crabcc.app`, Langfuse, and
   future dashboards "public-facing but non-public" uniformly.

[LiteLLM]: https://github.com/BerriAI/litellm
