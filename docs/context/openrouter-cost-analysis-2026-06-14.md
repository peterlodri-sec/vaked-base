# OpenRouter Cost Analysis — 2026-06-14

## Dashboard snapshot

| Metric | Value | Signal |
|--------|-------|--------|
| Total spend | $8.69 (+14,735% vs prev) | Near-zero baseline; absolute cost is low |
| Requests | 3K (+10,268% vs prev) | Same baseline effect |
| Token volume | 30.3M (+23,722% vs prev) | Same |
| Cache hit rate | 64.4% | 36% miss is recoverable |

### Top API keys

| Key | Tokens |
|-----|--------|
| `vakedgit` | 16.3M |
| `claude.ai` | 13.9M |
| `agents` | 18 |

### Top apps

| App | Tokens | Share |
|-----|--------|-------|
| vaked-label-tagger | 29.6M | 97.7% |
| Unknown | 724K | 2.4% |
| liteLLM | 18 | <0.01% |

---

## Root cause analysis

### 1. Label-tagger over-triggering

`label-tagger.yml` fired on **all** `pull_request` synchronize events and **all** `push` to main — no path filter. Every social-post commit, landing-page regeneration, and CHANGELOG bot commit triggered a full LLM run. Average tokens per request (~10,100) was 2.5–5× the expected 2,000–4,000.

### 2. Provider scatter busting the KV cache

`allow_fallbacks: true` with no `order` list let OpenRouter route label-tagger requests across multiple DeepSeek nodes. Each cold node has an empty KV cache, forcing full prompt re-evaluation — explaining the 64.4% (vs expected 85%+) hit rate.

### 3. "Unknown" app (724K tokens)

The LiteLLM proxy was forwarding requests to OpenRouter without `HTTP-Referer` or `X-Title` headers. OpenRouter attributed those 724K tokens to an anonymous source.

---

## Changes made

All three fixes landed in a single commit on branch `claude/clever-fermat-ertx42`:

**Commit [`0fcdc86`](https://github.com/peterlodri-sec/vaked-base/commit/0fcdc86)** — [PR #181](https://github.com/peterlodri-sec/vaked-base/pull/181)

### `.github/workflows/label-tagger.yml` — paths filter

Added `paths:` to both the `pull_request` and `push` triggers so the agent only fires when substantive source changes land:

```yaml
pull_request:
  types: [opened, synchronize, reopened]
  paths:
    - 'vaked/**'
    - 'vakedc/**'
    - 'vakedz/**'
    - 'protocol/**'
    - 'docs/language/**'
    - 'daemons/**'
    - 'agent_guardd/**'
    - 'eventd/**'
    - '.github/labels.yml'

push:
  branches: [main]
  paths:
    - 'vaked/**'
    - 'vakedc/**'
    # ... same set, minus labels.yml
```

Social posts, landing-page rebuilds, and CHANGELOG bot commits no longer trigger a run.

### `vaked-agents/ci/label-tagger/src/main.rs` — provider pinning + model upgrade

Changed from DeepSeek V4 Flash to `openai/gpt-oss-120b` and pinned to a single provider:

```rust
// model: deepseek/deepseek-v4-flash  →  openai/gpt-oss-120b
const DEFAULT_MODEL: &str = "openai/gpt-oss-120b";

.with_provider_preferences(OpenRouterProviderPreferences {
    allow_fallbacks: Some(false),   // was: true
    order: Some(vec!["OpenAI".to_string()]),
    ..Default::default()
})
```

Pinning to a single provider forces all requests through the same KV-cache-warmed endpoint.

### `deploy/llmproxy/config.yaml` — app attribution headers

```yaml
litellm_settings:
  default_headers:
    HTTP-Referer: "https://github.com/peterlodri-sec/vaked-base"
    X-Title: "vaked-llmproxy"
```

Every proxy request now carries identifying headers; the "Unknown" block disappears from the OpenRouter Top Apps list.

---

## Expected outcome

| Metric | Before | After |
|--------|--------|-------|
| Cache hit rate | 64.4% | 82–88% |
| Label-tagger token share | 97.7% | 70–80% |
| Tokens/request (avg) | ~10,100 | ~4,000–6,000 |
| Monthly cost | baseline | ~40–60% reduction |

---

## Verification checklist

- [ ] PR touching only `.github/social/` — label-tagger does **not** trigger
- [ ] PR touching `vaked/` — label-tagger triggers normally
- [ ] Social-post commit to main — changelog workflow does **not** fire
- [ ] After 50+ runs: OpenRouter dashboard cache hit rate >80%
- [ ] "Unknown" app disappears from OpenRouter Top Apps after next LiteLLM request
