"""qcall — Quick call shortcuts for common OpenRouter patterns.

Usage from Python scripts:
    from tools.openrouter.qcall import ask, code, review, budget
    
    result = ask("What is the meaning of life?")
    zig_code = code("Write a Zig function that...")
    feedback = review("Review this code: ...")
    budget()  # → "$5.80"
"""
import subprocess, sys, json
from pathlib import Path

ORCLI = Path(__file__).parent / "cli.py"


def ask(prompt: str, model: str = "deepseek", max_tokens: int = 500) -> str:
    """Quick question — cheap, fast."""
    r = subprocess.run(
        [sys.executable, str(ORCLI), "-m", model, "-t", str(max_tokens), prompt],
        capture_output=True, text=True, timeout=120,
    )
    return r.stdout.strip()


def code(prompt: str, model: str = "claude", max_tokens: int = 2000) -> str:
    """Generate code — Claude Opus, high quality."""
    r = subprocess.run(
        [sys.executable, str(ORCLI), "-m", model, "-t", str(max_tokens),
         "-s", "You are a Zig systems programmer. Write production code. No explanations, only code.",
         prompt],
        capture_output=True, text=True, timeout=120,
    )
    return r.stdout.strip()


def review(prompt: str, model: str = "claude", max_tokens: int = 600) -> str:
    """Review code or ideas — critical, concise."""
    r = subprocess.run(
        [sys.executable, str(ORCLI), "-m", model, "-t", str(max_tokens),
         "-s", "Critical reviewer. 3-5 specific suggestions. Be direct.",
         prompt],
        capture_output=True, text=True, timeout=120,
    )
    return r.stdout.strip()


def budget() -> str:
    """Get remaining OpenRouter budget."""
    r = subprocess.run(
        [sys.executable, str(ORCLI), "--status"],
        capture_output=True, text=True, timeout=10,
    )
    for line in r.stdout.split("\n"):
        if "Budget" in line:
            return line.split("$")[-1].strip()
    return "?"
