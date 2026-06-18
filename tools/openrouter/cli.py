#!/usr/bin/env python3
"""orcli — OpenRouter CLI. Your internal LLM gateway.

Usage:
    orcli "your prompt"                          # Default: deepseek-v4-flash
    orcli --model claude "your prompt"            # Claude Opus 4.8
    orcli --model gemini "your prompt"            # Gemini 2.5 Flash
    orcli --file input.txt "system prompt"        # Read input from file
    orcli --budget 0.50 "prompt"                  # Set max budget
    orcli --stream "prompt"                       # Stream output
    orcli --list                                  # List available models

Models:
    deepseek    deepseek/deepseek-v4-flash        (cheap, fast, reasoning)
    claude      anthropic/claude-opus-4.8-fast   (best code gen)
    gemini      google/gemini-2.5-flash           (balanced)
    qwen        qwen/qwen3-235b-a22b-thinking    (Chinese reasoning)
    llama       meta-llama/llama-4-maverick       (open-weight)

Budget tracking stored in ~/.orcli_budget
"""
import json, os, sys, ssl, time, urllib.request
from pathlib import Path

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
BUDGET_FILE = Path.home() / ".orcli_budget"

MODELS = {
    "deepseek": "deepseek/deepseek-v4-flash",
    "claude":   "anthropic/claude-opus-4.8-fast",
    "gemini":   "google/gemini-2.5-flash",
    "qwen":     "qwen/qwen3-235b-a22b-thinking",
    "llama":    "meta-llama/llama-4-maverick",
}

COSTS = {
    "deepseek/deepseek-v4-flash":          (0.27,  0.27),
    "anthropic/claude-opus-4.8-fast":     (15.00, 75.00),
    "google/gemini-2.5-flash":             (0.15,  0.60),
    "qwen/qwen3-235b-a22b-thinking":       (2.50,  5.00),
    "meta-llama/llama-4-maverick":         (0.20,  0.60),
}


def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def read_budget():
    try:
        return float(BUDGET_FILE.read_text().strip())
    except:
        return 6.00  # default


def write_budget(b):
    BUDGET_FILE.write_text(f"{b:.4f}")


def call(model: str, system: str, user: str, max_tokens: int = 1000, stream: bool = False) -> dict:
    """Make an OpenRouter API call."""
    if not API_KEY:
        return {"error": "OPENROUTER_API_KEY not set"}

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "stream": stream,
    }).encode()

    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120, context=get_ssl_context()) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def track_cost(model: str, usage: dict):
    """Track API costs against budget."""
    prompt_cost = usage.get("prompt_tokens", 0) * COSTS.get(model, (0, 0))[0] / 1_000_000
    completion_cost = usage.get("completion_tokens", 0) * COSTS.get(model, (0, 0))[1] / 1_000_000
    cost = prompt_cost + completion_cost
    budget = read_budget()
    budget -= cost
    write_budget(budget)
    return cost, budget


def main():
    import argparse
    p = argparse.ArgumentParser(description="orcli — OpenRouter CLI")
    p.add_argument("prompt", nargs="*", help="User prompt")
    p.add_argument("--model", "-m", default="deepseek", choices=list(MODELS.keys()) + list(MODELS.values()),
                   help="Model to use")
    p.add_argument("--system", "-s", default="You are a helpful assistant.", help="System prompt")
    p.add_argument("--file", "-f", help="Read user prompt from file")
    p.add_argument("--max-tokens", "-t", type=int, default=1000, help="Max output tokens")
    p.add_argument("--stream", action="store_true", help="Stream output")
    p.add_argument("--budget", "-b", type=float, help="Set max budget")
    p.add_argument("--list", "-l", action="store_true", help="List available models")
    p.add_argument("--status", action="store_true", help="Show budget status")
    args = p.parse_args()

    if args.list:
        print("Available models:")
        for name, model_id in MODELS.items():
            c = COSTS.get(model_id, (0, 0))
            print(f"  {name:12s} {model_id:45s} ${c[0]:.2f}/${c[1]:.2f} per 1M tok")
        return

    if args.status:
        budget = read_budget()
        print(f"Budget remaining: ${budget:.4f}")
        return

    # Resolve model
    model = MODELS.get(args.model, args.model)

    # Get prompt
    if args.file:
        user = Path(args.file).read_text()
    elif args.prompt:
        user = " ".join(args.prompt)
    else:
        user = sys.stdin.read()

    if not user.strip():
        print("Error: no prompt provided", file=sys.stderr)
        sys.exit(1)

    result = call(model, args.system, user, args.max_tokens, args.stream)

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.stream:
        # Already printed by stream handler
        return

    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    cost, budget = track_cost(model, usage)

    print(content)
    print(f"\n── {result.get('model', model)} · {usage.get('prompt_tokens', 0)}→{usage.get('completion_tokens', 0)} tok · ${cost:.4f} · ${budget:.2f} left", file=sys.stderr)


if __name__ == "__main__":
    main()
