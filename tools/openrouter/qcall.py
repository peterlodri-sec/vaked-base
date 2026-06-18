"""qcall — direct OpenRouter calls, no python3 subprocesses.
No more "Python quit unexpectedly" from recursive subprocess spawning.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Direct import — no subprocess
from tools.openrouter import cli as orcli


def ask(prompt: str, model: str = "deepseek", max_tokens: int = 500) -> str:
    """Quick question — cheap, fast. Direct function call, no subprocess."""
    result = orcli.call(model, "You are a helpful assistant.", prompt, max_tokens)
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")


def code(prompt: str, model: str = "claude", max_tokens: int = 2000) -> str:
    """Generate code — direct call, no subprocess."""
    result = orcli.call(
        orcli.MODELS.get(model, model),
        "Zig 0.16 systems programmer. Write production code. No explanations, only code.",
        prompt,
        max_tokens,
    )
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")


def review(prompt: str, model: str = "claude", max_tokens: int = 600) -> str:
    """Review code — direct call, no subprocess."""
    result = orcli.call(
        orcli.MODELS.get(model, model),
        "Critical reviewer. 3-5 specific suggestions. Be direct.",
        prompt,
        max_tokens,
    )
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")


def budget() -> str:
    """Get remaining budget from local file — no API call."""
    try:
        with open(os.path.expanduser("~/.orcli_budget")) as f:
            return f"${float(f.read().strip()):.2f}"
    except:
        return "$?"
