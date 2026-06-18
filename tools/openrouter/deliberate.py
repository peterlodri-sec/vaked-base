#!/usr/bin/env python3
"""deliberate — 20-model autonomous deliberation panel.

Broadcasts a single prompt to 20 models, synthesizes consensus via a Judge.
Budget-capped at $10/session. All costs logged.

GENESIS_SEAL: 7c242080
"""
import json, os, ssl, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
BUDGET_CAP = 10.00

# ── 20-model spectrum: frontier → efficiency ──────────────────────────
PANEL = [
    # Frontier (most expensive, highest quality)
    ("anthropic/claude-opus-4.8-fast", "Claude Opus 4.8"),
    ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("anthropic/claude-sonnet-4.6", "Claude Sonnet 4.6"),
    ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
    # Strong reasoners
    ("deepseek/deepseek-v4-pro", "DeepSeek V4"),
    ("qwen/qwen3-235b-a22b-thinking", "Qwen3 235B"),
    ("meta-llama/llama-4-maverick", "Llama 4 Maverick"),
    ("anthropic/claude-opus-4.7-fast", "Claude Opus 4.7"),
    # Mid-tier
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5"),
    ("google/gemini-2.0-flash", "Gemini 2.0 Flash"),
    ("mistralai/mistral-large", "Mistral Large"),
    ("cohere/command-r-plus", "Command R+"),
    # Efficiency (cheapest, fastest)
    ("deepseek/deepseek-chat", "DeepSeek Chat"),
    ("google/gemma-3-27b", "Gemma 3 27B"),
    ("meta-llama/llama-4-scout", "Llama 4 Scout"),
    ("qwen/qwen-2.5-72b", "Qwen 2.5 72B"),
    ("mistralai/mistral-small", "Mistral Small"),
    ("anthropic/claude-haiku-3.5", "Claude Haiku 3.5"),
    ("openai/gpt-4.1-mini", "GPT-4.1 Mini"),
    ("google/gemini-flash-1.5", "Gemini Flash 1.5"),
]

JUDGE_MODEL = "anthropic/claude-opus-4.8-fast"

PRICES = {
    "anthropic/claude-opus-4.8-fast": (15, 75),
    "google/gemini-2.5-pro": (1.25, 5),
    "anthropic/claude-sonnet-4.6": (3, 15),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "deepseek/deepseek-v4-pro": (0.27, 0.27),
    "qwen/qwen3-235b-a22b-thinking": (2.5, 5),
    "meta-llama/llama-4-maverick": (0.2, 0.6),
    "anthropic/claude-opus-4.7-fast": (15, 75),
    "anthropic/claude-haiku-4.5": (0.25, 1.25),
    "google/gemini-2.0-flash": (0.15, 0.60),
    "mistralai/mistral-large": (2, 6),
    "cohere/command-r-plus": (2.5, 10),
    "deepseek/deepseek-chat": (0.14, 0.28),
    "google/gemma-3-27b": (0.15, 0.15),
    "meta-llama/llama-4-scout": (0.1, 0.3),
    "qwen/qwen-2.5-72b": (0.35, 0.40),
    "mistralai/mistral-small": (1, 3),
    "anthropic/claude-haiku-3.5": (0.8, 4),
    "openai/gpt-4.1-mini": (0.15, 0.60),
    "google/gemini-flash-1.5": (0.075, 0.30),
}


def call_model(model: str, prompt: str, max_tokens: int = 300) -> dict:
    """Call a single model via OpenRouter."""
    if not OR_KEY:
        return {"model": model, "output": "", "error": "no API key", "cost": 0}

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            prompt_tok = usage.get("prompt_tokens", 0)
            comp_tok = usage.get("completion_tokens", 0)
            prices = PRICES.get(model, (0, 0))
            cost = (prompt_tok * prices[0] + comp_tok * prices[1]) / 1_000_000
            return {
                "model": model,
                "output": content,
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "cost": cost,
                "latency_ms": 0,
            }
    except Exception as e:
        return {"model": model, "output": "", "error": str(e), "cost": 0}


def synthesize(prompt: str, responses: list[dict]) -> str:
    """Judge model synthesizes consensus from all responses."""
    summaries = "\n\n---\n\n".join(
        f"[{r['model'].split('/')[-1][:15]}]: {r['output'][:300]}"
        for r in responses if r.get('output')
    )
    
    judge_prompt = f"""You are the Judge. Synthesize consensus from a 20-model deliberation panel.

ORIGINAL QUESTION: {prompt}

MODEL RESPONSES:
{summaries}

Synthesize a single, concise answer that:
1. Identifies areas of strong consensus (>70% agreement)
2. Highlights unique insights from any dissenting models
3. Gives the final answer with confidence level (HIGH/MEDIUM/LOW)
4. Lists the top 3 models that contributed most to the consensus

Format as a clear, structured response. Be direct. No filler."""

    result = call_model(JUDGE_MODEL, judge_prompt, max_tokens=800)
    return result.get("output", "Synthesis failed")


def deliberate(prompt: str, budget_cap: float = BUDGET_CAP) -> dict:
    """Run the 20-model deliberation panel."""
    print(f"Deliberation: {len(PANEL)} models · Budget cap: ${budget_cap:.2f}")
    print(f"Question: {prompt[:100]}...")
    print()
    
    total_cost = 0.0
    responses = []
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(call_model, model, prompt): (model, name)
            for model, name in PANEL
        }
        
        for future in as_completed(futures):
            model, name = futures[future]
            try:
                result = future.result()
                responses.append(result)
                total_cost += result.get("cost", 0)
                status = "✅" if result.get("output") else "❌"
                print(f"  {status} {name:25s} ${result.get('cost', 0):.4f}  {result.get('output', '')[:60]}...")
                
                if total_cost > budget_cap:
                    print(f"  ⚠️ Budget cap reached (${total_cost:.2f}). Cancelling remaining...")
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break
            except Exception as e:
                print(f"  ❌ {name:25s} {e}")
    
    print(f"\nTotal cost: ${total_cost:.4f}")
    
    # Synthesize
    print("Synthesizing consensus via Judge...")
    consensus = synthesize(prompt, responses)
    
    return {
        "prompt": prompt,
        "models_queried": len(responses),
        "total_cost": total_cost,
        "consensus": consensus,
        "responses": [{"model": r["model"], "cost": r["cost"], "preview": (r.get("output") or "")[:100]} for r in responses],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 deliberate.py 'your question here'")
        print("       python3 deliberate.py --file question.txt")
        sys.exit(1)
    
    if sys.argv[1] == "--file":
        with open(sys.argv[2]) as f:
            prompt = f.read().strip()
    else:
        prompt = " ".join(sys.argv[1:])
    
    result = deliberate(prompt)
    print("\n" + "="*60)
    print("JUDGE CONSENSUS:")
    print("="*60)
    print(result["consensus"])
